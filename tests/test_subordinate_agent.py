import unittest
from unittest.mock import MagicMock, patch, call
import sys
import io
import os

from subordinate_agent import SubordinateAgent, _execute_sandboxed_code
from llm_interface import LLMInterface

class TestSubordinateAgent(unittest.TestCase):
    def setUp(self):
        self.mock_llm_client = MagicMock(spec=LLMInterface)
        self.agent = SubordinateAgent(prompt="Initial prompt", llm_client=self.mock_llm_client)
        self.agent.id = 1

    def test_initialization(self):
        self.assertEqual(self.agent.prompt, "Initial prompt")
        self.assertIs(self.agent.llm_client, self.mock_llm_client)
        self.assertIsNone(self.agent.generated_code)
        self.assertEqual(self.agent.status, "initialized")
        self.assertEqual(self.agent.id, 1)

    def test_generate_code_success_and_sub_calls(self):
        generated_code_text = "import os\nprint(os.name)"
        self.mock_llm_client.generate_text.return_value = generated_code_text

        with patch.object(self.agent, 'verify_syntax', wraps=self.agent.verify_syntax) as spy_verify_syntax:
            with patch.object(self.agent, 'identify_dependencies', wraps=self.agent.identify_dependencies) as spy_identify_dependencies:
                self.agent.generate_code()

                self.assertEqual(self.agent.generated_code, generated_code_text)
                self.mock_llm_client.generate_text.assert_called_once_with("Initial prompt")
                
                spy_verify_syntax.assert_called_once()
                self.assertTrue(self.agent.is_syntax_valid)
                spy_identify_dependencies.assert_called_once()
                self.assertEqual(self.agent.dependencies, {"os"})

    def test_generate_code_llm_error(self):
        self.mock_llm_client.generate_text.side_effect = Exception("LLM API Error")

        with patch.object(self.agent, 'verify_syntax') as mock_verify_syntax:
            self.agent.generate_code()
            self.assertIsNone(self.agent.generated_code)
            self.assertTrue("failed_llm_generation_after" in self.agent.status or "attempt_1_llm_generation_error" in self.agent.status)
            mock_verify_syntax.assert_not_called()

    def test_verify_syntax_valid_calls_identify_dependencies(self):
        self.agent.generated_code = "import math\nx = math.sqrt(10)"
        with patch.object(self.agent, 'identify_dependencies', wraps=self.agent.identify_dependencies) as spy_identify_dependencies:
            result = self.agent.verify_syntax()
            self.assertTrue(result)
            self.assertTrue(self.agent.is_syntax_valid)
            self.assertIsNone(self.agent.syntax_error_message)
            spy_identify_dependencies.assert_called_once()
            self.assertEqual(self.agent.dependencies, {"math"})

    def test_verify_syntax_invalid_does_not_call_identify_dependencies(self):
        self.agent.generated_code = "x = 10\nprint(x y)"
        with patch.object(self.agent, 'identify_dependencies') as mock_identify_dependencies:
            result = self.agent.verify_syntax()
            self.assertFalse(result)
            self.assertFalse(self.agent.is_syntax_valid)
            self.assertIsNotNone(self.agent.syntax_error_message)
            self.assertTrue("error_syntax_invalid" in self.agent.status)
            mock_identify_dependencies.assert_not_called()

    def test_verify_syntax_no_code(self):
        self.agent.generated_code = None
        result = self.agent.verify_syntax()
        self.assertFalse(result)
        self.assertFalse(self.agent.is_syntax_valid)
        self.assertEqual(self.agent.syntax_error_message, "No code generated to verify.")
        self.assertEqual(self.agent.status, "error_syntax_check_no_code")

    def test_identify_dependencies_various_imports(self):
        self.agent.generated_code = "import os, sys\nfrom math import sqrt, pow\nimport pandas.api as pd_api\nfrom concurrent.futures import ThreadPoolExecutor"
        self.agent.is_syntax_valid = True 
        self.agent.identify_dependencies()
        self.assertEqual(self.agent.dependencies, {"os", "sys", "math", "pandas", "concurrent"})

    def test_identify_dependencies_no_imports(self):
        self.agent.generated_code = "print('Hello')\nx = 1"
        self.agent.is_syntax_valid = True
        self.agent.identify_dependencies()
        self.assertEqual(self.agent.dependencies, set())

    def test_identify_dependencies_no_code_or_invalid_syntax(self):
        self.agent.generated_code = None
        self.agent.is_syntax_valid = False
        self.agent.identify_dependencies()
        self.assertEqual(self.agent.dependencies, set()) 
        self.assertEqual(self.agent.status, "error_dependency_identification_no_code_or_invalid_syntax")

    def test_execute_code_success_no_output(self):
        self.agent.generated_code = "a = 1 + 1\nb = a * 2"
        self.agent.is_syntax_valid = True
        self.agent.execute_code()
        self.assertTrue(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_output, "")
        self.assertEqual(self.agent.execution_error, "")

    def test_execute_code_success_with_stdout_and_stderr(self):
        self.agent.generated_code = "import sys\nprint('Hello')\nsys.stderr.write('Warning message\\n')"
        self.agent.is_syntax_valid = True
        self.agent.execute_code()
        self.assertTrue(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_output, "Hello\n")
        self.assertEqual(self.agent.execution_error, "Warning message\n")

    def test_execute_code_runtime_error(self):
        self.agent.generated_code = "x = 1 / 0"
        self.agent.is_syntax_valid = True
        self.agent.execute_code()
        self.assertFalse(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_output, "")
        self.assertTrue("ZeroDivisionError" in self.agent.execution_error)

    def test_execute_code_no_code(self):
        self.agent.generated_code = None
        self.agent.execute_code()
        self.assertFalse(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_error, "No code generated to execute.")

    def test_execute_code_syntax_error_prevents_execution(self):
        self.agent.generated_code = "print( 'hello'" 
        self.agent.is_syntax_valid = False 
        self.agent.syntax_error_message = "Syntax error details"
        self.agent.execute_code()
        self.assertFalse(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_error, "Syntax error prevented execution: Syntax error details")
    
    @patch.object(SubordinateAgent, 'attempt_code_generation_and_execution')
    def test_regenerate_with_new_prompt(self, mock_attempt):
        self.agent.generated_code = "old code"
        self.agent.status = "code_executed_successfully"

        new_prompt = "New test prompt"
        self.agent.regenerate_with_new_prompt(new_prompt)

        self.assertEqual(self.agent.prompt, new_prompt)
        self.assertIsNone(self.agent.generated_code)
        self.assertIsNone(self.agent.is_syntax_valid)
        self.assertIsNone(self.agent.syntax_error_message)
        self.assertIsNone(self.agent.execution_successful)
        mock_attempt.assert_called_once_with(initial_user_prompt=new_prompt)

    def test_install_dependencies_simulation_success(self):
        self.agent.dependencies = {"numpy", "pandas"}
        self.agent.install_dependencies()
        
        self.assertTrue(self.agent.dependencies_installed_successfully)
        self.assertEqual(len(self.agent.installation_logs), 2)

    def test_install_dependencies_no_dependencies(self):
        self.agent.dependencies = set()
        self.agent.install_dependencies()
        self.assertTrue(self.agent.dependencies_installed_successfully)

    def test_attempt_code_generation_success_first_try(self):
        self.mock_llm_client.generate_text.return_value = "print('Success!')"
        def mock_verify_side_effect():
            self.agent.is_syntax_valid = True
            return True

        def mock_execute_side_effect():
            self.agent.execution_successful = True

        with patch.object(self.agent, 'verify_syntax', side_effect=mock_verify_side_effect) as mock_verify, \
             patch.object(self.agent, 'execute_code', side_effect=mock_execute_side_effect) as mock_execute:
            self.agent.attempt_code_generation_and_execution("Initial user prompt")

            self.assertEqual(self.agent.correction_attempts, 1)
            self.assertTrue("success_on_attempt_1" in self.agent.status)
            self.assertEqual(len(self.agent.generation_history), 1)

    def test_attempt_syntax_error_then_success(self):
        self.mock_llm_client.generate_text.side_effect = [
            "print 'syntax error'",
            "print('correct code')"
        ]
        
        with patch.object(self.agent, '_create_fix_prompt', return_value="Fix prompt content") as mock_create_fix_prompt:
            self.agent.attempt_code_generation_and_execution("User prompt: syntax test")

            self.assertEqual(self.agent.correction_attempts, 2)
            self.assertTrue("success_on_attempt_2" in self.agent.status)
            self.assertEqual(len(self.agent.generation_history), 2)

    def test_attempt_runtime_error_then_success(self):
        self.mock_llm_client.generate_text.side_effect = [
            "print(1/0)",
            "print('correct')"
        ]
        
        with patch.object(self.agent, '_create_fix_prompt', return_value="Fix runtime error prompt") as mock_create_fix_prompt:
            self.agent.attempt_code_generation_and_execution("User prompt: runtime test")

            self.assertEqual(self.agent.correction_attempts, 2)
            self.assertTrue("success_on_attempt_2" in self.agent.status)

    def test_attempt_failure_after_max_attempts_syntax(self):
        self.agent.max_correction_attempts = 2
        self.mock_llm_client.generate_text.return_value = "print 'always syntax error'"

        self.agent.attempt_code_generation_and_execution("User prompt: max attempts syntax")

        self.assertEqual(self.agent.correction_attempts, self.agent.max_correction_attempts)
        self.assertTrue(f"failed_syntax_after_{self.agent.max_correction_attempts}_attempts" in self.agent.status)

    def test_attempt_failure_after_max_attempts_runtime(self):
        self.agent.max_correction_attempts = 2
        self.mock_llm_client.generate_text.return_value = "print(1/0)"

        self.agent.attempt_code_generation_and_execution("User prompt: max attempts runtime")

        self.assertEqual(self.agent.correction_attempts, self.agent.max_correction_attempts)
        self.assertTrue(f"failed_runtime_after_{self.agent.max_correction_attempts}_attempts" in self.agent.status)


class TestSandboxExecutionFunction(unittest.TestCase):
    def test_execute_sandboxed_code_success(self):
        mock_conn_child_end = MagicMock()
        code = "print('hello from sandbox')"
        _execute_sandboxed_code(code, mock_conn_child_end)
        
        mock_conn_child_end.send.assert_called_once()
        args, _ = mock_conn_child_end.send.call_args
        result = args[0]
        
        self.assertTrue(result['success'])
        self.assertEqual(result['stdout'], 'hello from sandbox\n')

    def test_execute_sandboxed_code_runtime_error(self):
        mock_conn_child_end = MagicMock()
        code = "raise ValueError('sandbox test error')"
        _execute_sandboxed_code(code, mock_conn_child_end)
        
        mock_conn_child_end.send.assert_called_once()
        args, _ = mock_conn_child_end.send.call_args
        result = args[0]
        
        self.assertFalse(result['success'])
        self.assertIn("ValueError: sandbox test error", result['exception'])


if __name__ == '__main__':
    unittest.main()
