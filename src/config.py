import os

# --- Constantes de Configuração ---

# Configurações da API Groq
GROQ_API_BASE_URL = os.environ.get("GROQ_API_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MODEL_NAME = "llama-3.1-70b-versatile"

# Timeouts
HTTP_TIMEOUT = 60.0
SUBPROCESS_TIMEOUT = 120.0

# Formato de Log
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

# Prompt do Sistema para a IA
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
