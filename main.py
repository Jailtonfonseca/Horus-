import argparse
import hashlib
import json
import logging
import os
import sys
import time

from src.config import GROQ_API_KEY
from src.logger_setup import setup_logging
from src.api_client import call_groq_api, validate_response
from src.file_manager import (
    setup_workspace,
    get_file_content,
    apply_changes,
    update_instructions_file,
)
from src.command_runner import run_tests

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

    try:
        setup_workspace(workspace)
    except Exception:
        sys.exit(1)

    log_file_path = os.path.join(workspace, "agente.log")
    setup_logging(log_file_path)

    if not GROQ_API_KEY:
        logging.error("A variável de ambiente GROQ_API_KEY é obrigatória. Encerrando.")
        sys.exit(1)

    logging.info(f"Iniciando orquestração com a tarefa: '{args.tarefa}'")
    if args.dry_run:
        logging.info("MODO DRY-RUN ATIVADO. Nenhuma alteração será escrita.")

    subordinate_agent_path = os.path.join(workspace, "agente_subordinado.py")
    instructions_path = os.path.join(workspace, "instrucoes.txt")

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

        subordinate_code = get_file_content(subordinate_agent_path)
        if subordinate_code is None:
            logging.error(f"Não foi possível ler o agente subordinado em '{subordinate_agent_path}'. Encerrando.")
            break

        current_code_hash = hashlib.sha256(subordinate_code.encode('utf-8')).hexdigest()
        if current_code_hash == last_code_hash:
            no_change_cycles += 1
        else:
            no_change_cycles = 0
        last_code_hash = current_code_hash

        extra_instructions = ""
        if no_change_cycles >= 5:
            logging.warning(f"{no_change_cycles} ciclos sem alteração no código. Solicitando mais detalhes da IA.")
            extra_instructions = "AVISO: Você não fez alterações efetivas no código nos últimos ciclos. Por favor, analise o problema com mais cuidado e proponha uma solução diferente ou mais detalhada."

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

        logging.info("Enviando contexto para a API da Groq...")
        response_json = call_groq_api(context)

        if "error" in response_json:
            logging.error(f"Falha na chamada da API: {response_json['error']}")
            last_test_output = f"Erro na API: {response_json.get('raw_response', response_json['error'])}"
            time.sleep(args.intervalo)
            continue

        logging.info(f"Resposta da IA recebida: {json.dumps(response_json, indent=2)}")

        if not validate_response(response_json):
            last_test_output = f"Resposta JSON inválida recebida da IA: {json.dumps(response_json)}"
            time.sleep(args.intervalo)
            continue

        if not apply_changes(workspace, response_json, args.dry_run):
            last_test_output = "Falha ao aplicar as alterações propostas no arquivo."
            time.sleep(args.intervalo)
            continue

        if "instructions" in response_json and response_json["instructions"]:
            update_instructions_file(instructions_path, f"Ciclo {ciclo}: {response_json['instructions']}")

        exit_code, stdout, stderr = run_tests(workspace, response_json.get("test_command"))
        last_test_output = f"Exit Code: {exit_code}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        update_instructions_file(instructions_path, f"Resultado do Teste (Ciclo {ciclo}):\n{last_test_output}")

        if exit_code == 0:
            success_message = f"TAREFA CONCLUÍDA com sucesso no ciclo {ciclo}!"
            logging.info(success_message)
            update_instructions_file(instructions_path, success_message)
            break  # Encerra o loop com sucesso
        else:
            logging.warning("Teste falhou. Preparando para o próximo ciclo de correção.")

        time.sleep(args.intervalo)
    else:
        logging.warning(f"Número máximo de ciclos ({args.max_ciclos}) atingido. Encerrando.")
        update_instructions_file(instructions_path, "FALHA: Número máximo de ciclos atingido.")

    logging.info("Orquestração finalizada.")

if __name__ == "__main__":
    main()
