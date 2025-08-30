import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import shlex
import subprocess

# Adiciona o diretório raiz ao sys.path para encontrar o pacote 'src'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.command_runner import run_tests
from src.config import SUBPROCESS_TIMEOUT

class TestCommandRunner(unittest.TestCase):

    @patch('src.command_runner.subprocess.run')
    def test_run_tests_with_command(self, mock_subprocess_run):
        """Testa a execução de um comando de teste fornecido."""
        # Configura o mock para simular um processo bem-sucedido
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "Tests passed"
        mock_process.stderr = ""
        mock_subprocess_run.return_value = mock_process

        workspace = "/tmp/workspace"
        test_command = "pytest tests/"

        exit_code, stdout, stderr = run_tests(workspace, test_command)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "Tests passed")
        self.assertEqual(stderr, "")

        # Verifica se subprocess.run foi chamado corretamente
        expected_args = shlex.split(test_command)
        mock_subprocess_run.assert_called_once_with(
            expected_args,
            shell=False,
            capture_output=True,
            text=True,
            encoding='utf-8',
            cwd=workspace,
            timeout=SUBPROCESS_TIMEOUT
        )

    @patch('src.command_runner.subprocess.run')
    def test_run_tests_no_command(self, mock_subprocess_run):
        """Testa a execução do comando de teste padrão (py_compile)."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = ""
        mock_process.stderr = ""
        mock_subprocess_run.return_value = mock_process

        workspace = "/tmp/workspace"

        run_tests(workspace, None)

        # Constrói o comando padrão esperado
        expected_command = f"{sys.executable} -m py_compile {workspace}/agente_subordinado.py"
        expected_args = shlex.split(expected_command)

        mock_subprocess_run.assert_called_once_with(
            expected_args,
            shell=False,
            capture_output=True,
            text=True,
            encoding='utf-8',
            cwd=workspace,
            timeout=SUBPROCESS_TIMEOUT
        )

    @patch('src.command_runner.subprocess.run')
    def test_run_tests_timeout(self, mock_subprocess_run):
        """Testa o comportamento em caso de timeout do subprocesso."""
        # Configura o mock para levantar um TimeoutExpired
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(cmd="dummy", timeout=10)

        workspace = "/tmp/workspace"
        test_command = "sleep 20"

        exit_code, stdout, stderr = run_tests(workspace, test_command)

        self.assertEqual(exit_code, -1)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "Timeout Expirado")

    @patch('src.command_runner.subprocess.run')
    def test_run_tests_file_not_found(self, mock_subprocess_run):
        """Testa o comportamento quando o comando não é encontrado."""
        mock_subprocess_run.side_effect = FileNotFoundError

        workspace = "/tmp/workspace"
        test_command = "comando_inexistente"

        exit_code, stdout, stderr = run_tests(workspace, test_command)

        self.assertEqual(exit_code, -1)
        self.assertEqual(stdout, "")
        self.assertIn("Comando não encontrado", stderr)

if __name__ == '__main__':
    unittest.main()
