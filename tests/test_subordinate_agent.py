import unittest
from unittest.mock import MagicMock, patch, call
import sys
import io

# Ensure the main project directory is in the Python path
import os
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from subordinate_agent import SubordinateAgent

class TestSubordinateAgent(unittest.TestCase):
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from subordinate_agent import SubordinateAgent
from llm_interface import LLMInterface # For mocking

class TestSubordinateAgent(unittest.TestCase):
    def setUp(self):
        # Mock the LLMInterface client
        self.mock_llm_client = MagicMock(spec=LLMInterface)
        self.agent = SubordinateAgent(prompt="Initial prompt", llm_client=self.mock_llm_client)
        self.agent.id = 1 # Simulating ID assignment by MainAgent

    def test_initialization(self):
        self.assertEqual(self.agent.prompt, "Initial prompt")
        self.assertIs(self.agent.llm_client, self.mock_llm_client)
        self.assertIsNone(self.agent.generated_code)
        self.assertEqual(self.agent.status, "initialized")
        self.assertEqual(self.agent.id, 1)

    def test_generate_code_success_and_sub_calls(self):
        # Configure the mock LLM client's generate_text method
        generated_code_text = "import os\nprint(os.name)"
        self.mock_llm_client.generate_text.return_value = generated_code_text

        # Spy on verify_syntax and identify_dependencies
        with patch.object(self.agent, 'verify_syntax', wraps=self.agent.verify_syntax) as spy_verify_syntax:
            with patch.object(self.agent, 'identify_dependencies', wraps=self.agent.identify_dependencies) as spy_identify_dependencies:
                self.agent.generate_code()

                self.assertEqual(self.agent.generated_code, generated_code_text)
                # Check that the llm_client's generate_text was called correctly
                self.mock_llm_client.generate_text.assert_called_once_with("Initial prompt")
                
                spy_verify_syntax.assert_called_once()
                self.assertTrue(self.agent.is_syntax_valid) # Assumes generated_code_text is valid
                spy_identify_dependencies.assert_called_once()
                self.assertEqual(self.agent.dependencies, {"os"})
                self.assertEqual(self.agent.status, "dependencies_identified")


    def test_generate_code_llm_error(self):
        # Configure the mock LLM client's generate_text method to raise an exception
        self.mock_llm_client.generate_text.side_effect = Exception("LLM API Error")

        with patch.object(self.agent, 'verify_syntax') as mock_verify_syntax:
            self.agent.generate_code()
            self.assertIsNone(self.agent.generated_code)
            self.assertTrue("error_generating_code: LLM API Error" in self.agent.status)
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
            self.assertEqual(self.agent.status, "dependencies_identified")

    def test_verify_syntax_invalid_does_not_call_identify_dependencies(self):
        self.agent.generated_code = "x = 10\nprint(x y)" # Invalid syntax
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
        self.assertEqual(self.agent.status, "dependencies_identified")

    def test_identify_dependencies_no_imports(self):
        self.agent.generated_code = "print('Hello')\nx = 1"
        self.agent.is_syntax_valid = True
        self.agent.identify_dependencies()
        self.assertEqual(self.agent.dependencies, set())
        self.assertEqual(self.agent.status, "dependencies_identified")

    def test_identify_dependencies_no_code_or_invalid_syntax(self):
        self.agent.generated_code = None
        self.agent.is_syntax_valid = False
        self.agent.identify_dependencies()
        self.assertEqual(self.agent.dependencies, set()) 
        self.assertEqual(self.agent.status, "error_dependency_identification_no_code_or_invalid_syntax")

        self.agent.generated_code = "valid code but not parsed yet"
        self.agent.is_syntax_valid = False # Explicitly set to false
        self.agent.identify_dependencies()
        self.assertEqual(self.agent.status, "error_dependency_identification_no_code_or_invalid_syntax")


    def test_execute_code_success_no_output(self):
        self.agent.generated_code = "a = 1 + 1\nb = a * 2"
        self.agent.is_syntax_valid = True
        self.agent.execute_code()
        self.assertTrue(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_output, "")
        self.assertEqual(self.agent.execution_error, "")
        self.assertEqual(self.agent.status, "code_executed_successfully")

    def test_execute_code_success_with_stdout_and_stderr(self):
        self.agent.generated_code = "import sys\nprint('Hello')\nsys.stderr.write('Warning message\\n')"
        self.agent.is_syntax_valid = True
        self.agent.execute_code()
        self.assertTrue(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_output, "Hello\n")
        self.assertEqual(self.agent.execution_error, "Warning message\n") # Stderr is captured in execution_error
        self.assertEqual(self.agent.status, "code_executed_with_stderr")

    def test_execute_code_runtime_error(self):
        self.agent.generated_code = "x = 1 / 0"
        self.agent.is_syntax_valid = True
        self.agent.execute_code()
        self.assertFalse(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_output, "")
        self.assertTrue("ZeroDivisionError" in self.agent.execution_error)
        self.assertTrue("error_execution_runtime" in self.agent.status)

    def test_execute_code_no_code(self):
        self.agent.generated_code = None
        self.agent.execute_code()
        self.assertFalse(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_error, "No code generated to execute.")
        self.assertEqual(self.agent.status, "error_execution_no_code")

    def test_execute_code_syntax_error_prevents_execution(self):
        self.agent.generated_code = "print( 'hello'" 
        self.agent.is_syntax_valid = False 
        self.agent.syntax_error_message = "Syntax error details"
        self.agent.execute_code()
        self.assertFalse(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_error, "Syntax error prevented execution: Syntax error details")
        self.assertEqual(self.agent.status, "error_execution_syntax_invalid")
    
    @patch.object(SubordinateAgent, 'generate_code')
    def test_regenerate_with_new_prompt(self, mock_generate_code):
        self.agent.generated_code = "old code"
        self.agent.status = "code_executed_successfully"
        self.agent.is_syntax_valid = True
        self.agent.syntax_error_message = None
        self.agent.execution_successful = True
        self.agent.execution_output = "old output"
        self.agent.execution_error = ""
        self.agent.dependencies = {"old_dep"}

        new_prompt = "New test prompt"
        self.agent.regenerate_with_new_prompt(new_prompt)

        self.assertEqual(self.agent.prompt, new_prompt)
        self.assertIsNone(self.agent.generated_code)
        self.assertEqual(self.agent.status, "regenerating") 
        self.assertIsNone(self.agent.is_syntax_valid)
        self.assertIsNone(self.agent.syntax_error_message)
        self.assertIsNone(self.agent.execution_successful)
        self.assertIsNone(self.agent.execution_output)
        self.assertIsNone(self.agent.execution_error)
        # Dependencies are reset by identify_dependencies, which is called by generate_code->verify_syntax
        # So at the point of this test, it depends on whether generate_code was fully mocked or spied
        # Since generate_code is fully mocked here, dependencies wouldn't be cleared by it yet.
        # The test should focus on attributes reset directly by regenerate_with_new_prompt
        
        mock_generate_code.assert_called_once()

    def test_install_dependencies_simulation_success(self):
        self.agent.dependencies = {"numpy", "pandas"}
        # This method currently only prints and sets flags, no external calls to mock
        self.agent.install_dependencies()
        
        self.assertTrue(self.agent.dependencies_installed_successfully)
        self.assertEqual(len(self.agent.installation_logs), 2)
        self.assertTrue("Attempting to install numpy... (simulation)" in self.agent.installation_logs[0] or \
                        "Attempting to install numpy... (simulation)" in self.agent.installation_logs[1]) # Order not guaranteed
        self.assertTrue("Attempting to install pandas... (simulation)" in self.agent.installation_logs[0] or \
                        "Attempting to install pandas... (simulation)" in self.agent.installation_logs[1])
        self.assertEqual(self.agent.status, "dependencies_installed_simulated")

    def test_install_dependencies_no_dependencies(self):
        self.agent.dependencies = set()
        self.agent.install_dependencies()
        self.assertTrue(self.agent.dependencies_installed_successfully) # Or None, based on impl.
        self.assertEqual(self.agent.status, "info_no_dependencies_to_install")
        self.assertIsNone(getattr(self.agent, 'installation_logs', None)) # Logs not created

if __name__ == '__main__':
    # This allows running the tests directly from this file
    # Adjust path if subordinate_agent is not in the root or PYTHONPATH
    if '..' not in sys.path:
         sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from subordinate_agent import SubordinateAgent
    unittest.main()
