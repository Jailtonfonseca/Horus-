import argparse
import datetime
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from typing import Dict, Any, Optional, Tuple
from urllib import request, error

# --- Constantes ---
GROQ_API_BASE_URL = os.environ.get("GROQ_API_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MODEL_NAME = "llama-3.1-70b-versatile"
HTTP_TIMEOUT = 60.0
SUBPROCESS_TIMEOUT = 120.0
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

# --- Prompt do Sistema para a IA ---
SYSTEM_PROMPT = """
Você é um agente de IA assistente de codificação. Sua tarefa é modificar um arquivo de código para cumprir um objetivo.
Responda APENAS com um único objeto JSON válido, sem nenhum texto ou explicação adicional.
O JSON deve seguir estritamente este esquema:
{
  "action": "replace_file" | "append" | "replace_block" | "noop",
  "target_path": "caminho/do/arquivo/alvo",
  "marker": "string_marcador_opcional_se_action_for_replace_block",
  "code": "string com o código ou conteúdo para escrever (use \\n para novas linhas)",
  "instructions": "texto legível para registrar o progresso (opcional)",
  "test_command": "comando shell para testar o arquivo alterado (opcional)"
}

- Se action for "replace_block", o campo "marker" é obrigatório. O código em "code" substituirá a região entre `# >>> BEGIN:{marker}` e `# >>> END:{marker}`.
- Se action for "noop", você pode usar "instructions" para explicar por que nenhuma ação foi tomada.
- O arquivo alvo principal é 'agente_subordinado.py'. Modifique-o para atingir a tarefa do usuário.
- Analise o código atual, o histórico de testes e a tarefa para decidir a melhor ação.
- Gere um comando de teste (`test_command`) para validar suas alterações. Se omitido, um teste de sintaxe será executado.
"""

def setup_logging(log_file: str):
    """Configura o logging para arquivo e console."""
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

def setup_workspace(workspace_path: str) -> None:
    """Cria o diretório de workspace e subdiretórios necessários."""
    try:
        os.makedirs(os.path.join(workspace_path, "backups"), exist_ok=True)
        logging.info(f"Workspace '{workspace_path}' configurado com sucesso.")
    except OSError as e:
        logging.error(f"Erro ao criar workspace em '{workspace_path}': {e}")
        sys.exit(1)

def get_file_content(path: str) -> Optional[str]:
    """Lê o conteúdo de um arquivo."""
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def create_backup(workspace: str, target_path: str) -> None:
    """Cria um backup versionado de um arquivo."""
    if not os.path.exists(target_path):
        return

    content = get_file_content(target_path)
    if content is None:
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:8]
    backup_dir = os.path.join(workspace, "backups")
    base_name = os.path.basename(target_path).replace('.', '_')
    backup_filename = f"{base_name}__{timestamp}__{content_hash}.bak"
    backup_path = os.path.join(backup_dir, backup_filename)

    try:
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logging.info(f"Backup de '{target_path}' criado em '{backup_path}'")
    except IOError as e:
        logging.warning(f"Não foi possível criar backup para '{target_path}': {e}")


def call_groq_api(context: str) -> Dict[str, Any]:
    """Envia o contexto para a API da Groq e retorna a resposta JSON."""
    if not GROQ_API_KEY:
        raise ValueError("A variável de ambiente GROQ_API_KEY não está definida.")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context}
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"}
    }

    req = request.Request(
        f"{GROQ_API_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method="POST"
    )

    try:
        with request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
            if response.status != 200:
                logging.error(f"Erro na API Groq: Status {response.status} - {response.read().decode()}")
                return {"error": "API request failed"}

            response_body = json.loads(response.read().decode('utf-8'))
            assistant_response_str = response_body['choices'][0]['message']['content']

            # Tenta analisar a string JSON da resposta do assistente
            return json.loads(assistant_response_str)

    except error.URLError as e:
        logging.error(f"Erro de conexão com a API: {e}")
        return {"error": f"Connection error: {e}"}
    except json.JSONDecodeError as e:
        logging.error(f"Erro ao decodificar JSON da resposta da API: {e}")
        logging.error(f"String recebida: {assistant_response_str}")
        return {"error": f"JSON decode error: {e}", "raw_response": assistant_response_str}
    except Exception as e:
        logging.error(f"Erro inesperado ao chamar a API: {e}")
        return {"error": f"Unexpected API error: {e}"}


def validate_response(response: Dict[str, Any]) -> bool:
    """Valida o schema do JSON recebido da API."""
    if "action" not in response or response["action"] not in ["replace_file", "append", "replace_block", "noop"]:
        logging.warning(f"Resposta da IA inválida: 'action' ausente ou inválido. Resposta: {response}")
        return False

    action = response["action"]
    if action in ["replace_file", "append", "replace_block"]:
        if "target_path" not in response or "code" not in response:
             logging.warning(f"Resposta da IA inválida: 'target_path' ou 'code' ausente para a ação '{action}'.")
             return False

    if action == "replace_block" and "marker" not in response:
        logging.warning("Resposta da IA inválida: 'marker' ausente para a ação 'replace_block'.")
        return False

    return True

def apply_changes(workspace: str, change: Dict[str, Any], dry_run: bool) -> bool:
    """Aplica as alterações de arquivo de forma atômica."""
    action = change["action"]
    if action == "noop":
        logging.info("Ação 'noop' recebida. Nenhuma alteração de arquivo será feita.")
        return True # Nenhuma alteração, mas a operação foi 'bem-sucedida'.

    target_path = os.path.join(workspace, change["target_path"])
    code_to_write = change["code"]

    # Validação de segurança simples
    if ".." in target_path or not target_path.startswith(os.path.abspath(workspace)):
        logging.error(f"Tentativa de escrita fora do workspace detectada: '{target_path}'. Ação bloqueada.")
        return False

    logging.info(f"Aplicando ação '{action}' em '{target_path}'.")
    if dry_run:
        logging.info("[DRY RUN] Nenhuma alteração será escrita no disco.")
        return True

    create_backup(workspace, target_path)

    try:
        # Escrita atômica
        temp_fd, temp_path = tempfile.mkstemp(dir=workspace)

        if action == "replace_file":
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as temp_f:
                temp_f.write(code_to_write)

        elif action == "append":
            original_content = get_file_content(target_path) or ""
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as temp_f:
                temp_f.write(original_content)
                temp_f.write("\n" + code_to_write)

        elif action == "replace_block":
            marker = change["marker"]
            start_marker = f"# >>> BEGIN:{marker}"
            end_marker = f"# >>> END:{marker}"

            original_content = get_file_content(target_path)
            if not original_content or start_marker not in original_content or end_marker not in original_content:
                logging.error(f"Marcadores '{start_marker}'/'{end_marker}' não encontrados em '{target_path}'. Ação falhou.")
                os.close(temp_fd)
                os.remove(temp_path)
                return False

            pre_block = original_content.split(start_marker)[0]
            post_block = original_content.split(end_marker)[1]

            with os.fdopen(temp_fd, 'w', encoding='utf-8') as temp_f:
                temp_f.write(pre_block)
                temp_f.write(start_marker + "\n")
                temp_f.write(code_to_write)
                temp_f.write("\n" + end_marker)
                temp_f.write(post_block)

        os.replace(temp_path, target_path)
        logging.info(f"Alteração em '{target_path}' aplicada com sucesso.")
        return True

    except Exception as e:
        logging.error(f"Erro ao aplicar alterações em '{target_path}': {e}")
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        return False

def run_tests(workspace: str, test_command: Optional[str]) -> Tuple[int, str, str]:
    """Executa o comando de teste ou um teste de sintaxe padrão."""
    subordinate_agent_path = os.path.join(workspace, "agente_subordinado.py")

    if not test_command:
        test_command = f"{sys.executable} -m py_compile {subordinate_agent_path}"
        logging.info(f"Nenhum comando de teste fornecido. Usando teste de sintaxe padrão: '{test_command}'")

    logging.info(f"Executando comando de teste: '{test_command}'")

    try:
        result = subprocess.run(
            test_command,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            cwd=workspace,
            timeout=SUBPROCESS_TIMEOUT
        )
        logging.info(f"Teste finalizado com código de saída: {result.returncode}")
        if result.stdout:
            logging.info(f"stdout:\n{result.stdout}")
        if result.stderr:
            logging.warning(f"stderr:\n{result.stderr}")

        return result.returncode, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        logging.error(f"Comando de teste excedeu o tempo limite de {SUBPROCESS_TIMEOUT}s.")
        return -1, "", "Timeout Expirado"
    except Exception as e:
        logging.error(f"Erro ao executar comando de teste: {e}")
        return -1, "", str(e)

def update_instructions_file(path: str, message: str):
    """Adiciona uma mensagem ao arquivo de instruções."""
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(f"\n--- {datetime.datetime.now().isoformat()} ---\n")
            f.write(message + "\n")
    except IOError as e:
        logging.warning(f"Não foi possível atualizar o arquivo de instruções '{path}': {e}")

def main():
    """Função principal do agente orquestrador."""
    parser = argparse.ArgumentParser(description="Agente orquestrador que ajusta um agente subordinado.")
    parser.add_argument("--tarefa", type=str, required=True, help="Descrição da tarefa para o agente.")
    parser.add_argument("--workspace", type=str, default="./workspace", help="Pasta de trabalho.")
    parser.add_argument("--max_ciclos", type=int, default=50, help="Número máximo de ciclos de iteração.")
    parser.add_argument("--intervalo", type=float, default=5.0, help="Intervalo em segundos entre os ciclos.")
    parser.add_argument("--dry-run", action="store_true", help="Executa a lógica sem aplicar alterações nos arquivos.")
    args = parser.parse_args()

    workspace = os.path.abspath(args.workspace)
    setup_workspace(workspace)

    log_file_path = os.path.join(workspace, "agente.log")
    setup_logging(log_file_path)

    if not GROQ_API_KEY:
        logging.error("A variável de ambiente GROQ_API_KEY é obrigatória. Encerrando.")
        sys.exit(1)

    logging.info(f"Iniciando orquestração com a tarefa: '{args.tarefa}'")
    if args.dry_run:
        logging.info("MODO DRY-RUN ATIVADO. Nenhuma alteração será escrita.")

    # Caminhos dos arquivos
    subordinate_agent_path = os.path.join(workspace, "agente_subordinado.py")
    instructions_path = os.path.join(workspace, "instrucoes.txt")

    # Inicializa arquivos se não existirem
    if not os.path.exists(subordinate_agent_path):
        with open(subordinate_agent_path, 'w', encoding='utf-8') as f:
            f.write("# Arquivo inicial do agente subordinado.\npass\n")

    if not os.path.exists(instructions_path):
        with open(instructions_path, 'w', encoding='utf-8') as f:
            f.write("Histórico de execução do agente.\n")

    last_test_output = ""
    last_code_hash = ""
    no_change_cycles = 0

    for ciclo in range(1, args.max_ciclos + 1):
        logging.info(f"--- Iniciando Ciclo {ciclo}/{args.max_ciclos} ---")

        # 1. Construir contexto
        subordinate_code = get_file_content(subordinate_agent_path)

        current_code_hash = hashlib.sha256(subordinate_code.encode('utf-8')).hexdigest()
        if current_code_hash == last_code_hash:
            no_change_cycles += 1
        else:
            no_change_cycles = 0
        last_code_hash = current_code_hash

        if no_change_cycles >= 5:
            logging.warning(f"{no_change_cycles} ciclos sem alteração no código. Solicitando mais detalhes da IA.")
            extra_instructions = "AVISO: Você não fez alterações efetivas no código nos últimos ciclos. Por favor, analise o problema com mais cuidado e proponha uma solução diferente ou mais detalhada."
        else:
            extra_instructions = ""

        context = f\"\"\"
        Tarefa do Usuário: {args.tarefa}

        Arquivo a ser modificado: 'agente_subordinado.py'
        Conteúdo atual de 'agente_subordinado.py':
        ---
        {subordinate_code}
        ---

        Resultado do último teste:
        ---
        {last_test_output}
        ---

        Instruções adicionais: {extra_instructions}

        Por favor, forneça sua próxima ação no formato JSON especificado.
        \"\"\"

        # 2. Chamar API
        logging.info("Enviando contexto para a API da Groq...")
        response_json = call_groq_api(context)

        if "error" in response_json:
            logging.error(f"Falha na chamada da API: {response_json['error']}")
            last_test_output = f"Erro na API: {response_json.get('raw_response', response_json['error'])}"
            time.sleep(args.intervalo)
            continue

        logging.info(f"Resposta da IA recebida: {json.dumps(response_json, indent=2)}")

        # 3. Validar resposta
        if not validate_response(response_json):
            last_test_output = f"Resposta JSON inválida recebida da IA: {json.dumps(response_json)}"
            time.sleep(args.intervalo)
            continue

        # 4. Aplicar alterações
        if not apply_changes(workspace, response_json, args.dry_run):
            last_test_output = "Falha ao aplicar as alterações propostas no arquivo."
            time.sleep(args.intervalo)
            continue

        # 5. Atualizar instruções
        if "instructions" in response_json and response_json["instructions"]:
            update_instructions_file(instructions_path, f"Ciclo {ciclo}: {response_json['instructions']}")

        # 6. Rodar testes
        exit_code, stdout, stderr = run_tests(workspace, response_json.get("test_command"))
        last_test_output = f"Exit Code: {exit_code}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        update_instructions_file(instructions_path, f"Resultado do Teste (Ciclo {ciclo}):\n{last_test_output}")

        # 7. Verificar conclusão
        if exit_code == 0:
            logging.info("Teste bem-sucedido! A tarefa pode estar concluída.")
            # Opcional: procurar por um sinal de conclusão da IA
            if response_json.get("task_completed", False):
                 success_message = f"TAREFA CONCLUÍDA com sucesso no ciclo {ciclo}!"
                 logging.info(success_message)
                 update_instructions_file(instructions_path, success_message)
                 break
            else:
                 logging.info("O teste passou, mas a IA não sinalizou o fim da tarefa. Continuando para o próximo ciclo.")
        else:
            logging.warning("Teste falhou. Preparando para o próximo ciclo de correção.")

        time.sleep(args.intervalo)
    else: # Executado se o loop for terminar sem 'break'
        logging.warning(f"Número máximo de ciclos ({args.max_ciclos}) atingido. Encerrando.")
        update_instructions_file(instructions_path, "FALHA: Número máximo de ciclos atingido.")

    logging.info("Orquestração finalizada.")

if __name__ == "__main__":
    main()
