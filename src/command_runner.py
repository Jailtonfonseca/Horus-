import logging
import shlex
import subprocess
import sys
from typing import Tuple

from .config import SUBPROCESS_TIMEOUT

def run_tests(workspace: str, test_command: str | None) -> Tuple[int, str, str]:
    """Executa o comando de teste ou um teste de sintaxe padrão de forma segura."""
    subordinate_agent_path = f"{workspace}/agente_subordinado.py"

    if not test_command:
        test_command = f"{sys.executable} -m py_compile {subordinate_agent_path}"
        logging.info(f"Nenhum comando de teste fornecido. Usando teste de sintaxe padrão: '{test_command}'")

    logging.info(f"Executando comando de teste: '{test_command}'")

    try:
        # Usa shlex.split para dividir o comando em uma lista de forma segura,
        # evitando riscos de injeção de shell ao usar shell=False.
        command_args = shlex.split(test_command)

        result = subprocess.run(
            command_args,
            shell=False,  # Mais seguro
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
    except FileNotFoundError:
        logging.error(f"Comando não encontrado: '{command_args[0]}'. Verifique se está no PATH.")
        return -1, "", f"Comando não encontrado: {command_args[0]}"
    except Exception as e:
        logging.error(f"Erro ao executar comando de teste: {e}")
        return -1, "", str(e)
