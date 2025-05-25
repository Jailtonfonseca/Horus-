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


    # Tests for attempt_code_generation_and_execution and iterative debugging
    def test_attempt_code_generation_success_first_try(self):
        self.mock_llm_client.generate_text.return_value = "print('Success!')"
        # No need to mock verify_syntax and execute_code if we let them run on simple valid code
        # However, for precise control, mocking them is better.
        with patch.object(self.agent, 'verify_syntax', return_value=True) as mock_verify, \
             patch.object(self.agent, 'execute_code', return_value=None) as mock_execute:
            # Simulate successful execution by setting attributes execute_code would set
            self.agent.execution_successful = True 
            
            self.agent.attempt_code_generation_and_execution("Initial user prompt")

            self.assertEqual(self.agent.correction_attempts, 1)
            self.assertTrue("success_on_attempt_1" in self.agent.status)
            self.assertEqual(len(self.agent.generation_history), 1)
            self.assertEqual(self.agent.generation_history[0]['attempt'], 1)
            self.assertEqual(self.agent.generation_history[0]['prompt_to_llm'], "Initial user prompt")
            self.assertEqual(self.agent.generation_history[0]['generated_code'], "print('Success!')")
            self.assertIsNone(self.agent.generation_history[0]['error_type'])
            self.mock_llm_client.generate_text.assert_called_once_with("Initial user prompt")
            mock_verify.assert_called_once()
            mock_execute.assert_called_once()

    def test_attempt_syntax_error_then_success(self):
        # First call to LLM returns code with syntax error
        # Second call (fix prompt) returns valid code
        self.mock_llm_client.generate_text.side_effect = [
            "print 'syntax error'",  # First attempt (invalid Python 2 print)
            "print('correct code')"  # Second attempt (valid)
        ]
        
        # Mock _create_fix_prompt to verify it's called
        with patch.object(self.agent, '_create_fix_prompt', return_value="Fix prompt content") as mock_create_fix_prompt:
            self.agent.attempt_code_generation_and_execution("User prompt: syntax test")

            self.assertEqual(self.agent.correction_attempts, 2)
            self.assertTrue("success_on_attempt_2" in self.agent.status)
            self.assertEqual(len(self.agent.generation_history), 2)

            # Check first attempt (syntax error)
            history1 = self.agent.generation_history[0]
            self.assertEqual(history1['attempt'], 1)
            self.assertEqual(history1['prompt_to_llm'], "User prompt: syntax test")
            self.assertEqual(history1['generated_code'], "print 'syntax error'")
            self.assertEqual(history1['error_type'], "Syntax")
            self.assertTrue("SyntaxError" in history1['error_message'])
            
            # Check that _create_fix_prompt was called after the first attempt's error
            mock_create_fix_prompt.assert_called_once_with(
                "User prompt: syntax test", 
                "print 'syntax error'", 
                history1['error_message'], 
                "Syntax",
                2 # Attempt number for the *next* try
            )

            # Check second attempt (success)
            history2 = self.agent.generation_history[1]
            self.assertEqual(history2['attempt'], 2)
            self.assertEqual(history2['prompt_to_llm'], "Fix prompt content") # From mock_create_fix_prompt
            self.assertEqual(history2['generated_code'], "print('correct code')")
            self.assertIsNone(history2['error_type'])
            
            self.assertEqual(self.mock_llm_client.generate_text.call_count, 2)


    def test_attempt_runtime_error_then_success(self):
        self.mock_llm_client.generate_text.side_effect = [
            "print(1/0)",         # First attempt (runtime error)
            "print('correct')"    # Second attempt (valid)
        ]
        
        with patch.object(self.agent, '_create_fix_prompt', return_value="Fix runtime error prompt") as mock_create_fix_prompt:
            self.agent.attempt_code_generation_and_execution("User prompt: runtime test")

            self.assertEqual(self.agent.correction_attempts, 2)
            self.assertTrue("success_on_attempt_2" in self.agent.status)
            self.assertEqual(len(self.agent.generation_history), 2)

            history1 = self.agent.generation_history[0]
            self.assertEqual(history1['generated_code'], "print(1/0)")
            self.assertEqual(history1['error_type'], "Runtime")
            self.assertTrue("ZeroDivisionError" in history1['error_message'])
            
            mock_create_fix_prompt.assert_called_once()

            history2 = self.agent.generation_history[1]
            self.assertEqual(history2['generated_code'], "print('correct')")
            self.assertIsNone(history2['error_type'])
            
            self.assertEqual(self.mock_llm_client.generate_text.call_count, 2)

    def test_attempt_failure_after_max_attempts_syntax(self):
        self.agent.max_correction_attempts = 2 # For quicker test
        self.mock_llm_client.generate_text.return_value = "print 'always syntax error'" # Always bad code

        self.agent.attempt_code_generation_and_execution("User prompt: max attempts syntax")

        self.assertEqual(self.agent.correction_attempts, self.agent.max_correction_attempts)
        self.assertTrue(f"failed_syntax_after_{self.agent.max_correction_attempts}_attempts" in self.agent.status)
        self.assertEqual(len(self.agent.generation_history), self.agent.max_correction_attempts)
        for i in range(self.agent.max_correction_attempts):
            self.assertEqual(self.agent.generation_history[i]['error_type'], "Syntax")
        self.assertEqual(self.mock_llm_client.generate_text.call_count, self.agent.max_correction_attempts)

    def test_attempt_failure_after_max_attempts_runtime(self):
        self.agent.max_correction_attempts = 2
        self.mock_llm_client.generate_text.return_value = "print(1/0)" # Always runtime error

        self.agent.attempt_code_generation_and_execution("User prompt: max attempts runtime")

        self.assertEqual(self.agent.correction_attempts, self.agent.max_correction_attempts)
        self.assertTrue(f"failed_runtime_after_{self.agent.max_correction_attempts}_attempts" in self.agent.status)
        self.assertEqual(len(self.agent.generation_history), self.agent.max_correction_attempts)
        for i in range(self.agent.max_correction_attempts):
            self.assertEqual(self.agent.generation_history[i]['error_type'], "Runtime")
        self.assertEqual(self.mock_llm_client.generate_text.call_count, self.agent.max_correction_attempts)

    def test_attempt_llm_call_fails_during_fix(self):
        self.agent.max_correction_attempts = 3
        self.mock_llm_client.generate_text.side_effect = [
            "print 'syntax error'",  # Attempt 1: syntax error
            Exception("LLM API failed during fix attempt"), # Attempt 2: LLM fails
            # No third attempt as LLM failed
        ]
        with patch.object(self.agent, '_create_fix_prompt', return_value="Fix prompt") as mock_create_fix_prompt:
            self.agent.attempt_code_generation_and_execution("User prompt: LLM fail on fix")

            self.assertEqual(self.agent.correction_attempts, 2) # First valid gen, second LLM error
            self.assertTrue(f"failed_llm_generation_after_{self.agent.max_correction_attempts}_attempts" in self.agent.status) # or a more specific status if LLM error is different
            self.assertEqual(len(self.agent.generation_history), 2)
            
            self.assertEqual(self.agent.generation_history[0]['error_type'], "Syntax")
            self.assertEqual(self.agent.generation_history[1]['error_type'], "LLM_Generation")
            self.assertTrue("LLM API failed" in self.agent.generation_history[1]['error_message'])
            
            mock_create_fix_prompt.assert_called_once() # Called after the first syntax error
            self.assertEqual(self.mock_llm_client.generate_text.call_count, 2)


# Import the target function for direct testing
from subordinate_agent import _execute_sandboxed_code

class TestSandboxExecutionFunction(unittest.TestCase):
    def test_execute_sandboxed_code_success(self):
        mock_conn_child_end = MagicMock() # This is the end of the pipe in the child process
        code = "print('hello from sandbox')"
        _execute_sandboxed_code(code, mock_conn_child_end)
        
        mock_conn_child_end.send.assert_called_once()
        args, _ = mock_conn_child_end.send.call_args
        result = args[0]
        
        self.assertTrue(result['success'])
        self.assertEqual(result['stdout'], 'hello from sandbox\n')
        self.assertEqual(result['stderr'], '')
        self.assertIsNone(result['exception'])
        mock_conn_child_end.close.assert_called_once()

    def test_execute_sandboxed_code_runtime_error(self):
        mock_conn_child_end = MagicMock()
        code = "raise ValueError('sandbox test error')"
        _execute_sandboxed_code(code, mock_conn_child_end)
        
        mock_conn_child_end.send.assert_called_once()
        args, _ = mock_conn_child_end.send.call_args
        result = args[0]
        
        self.assertFalse(result['success'])
        self.assertEqual(result['stdout'], '') # No stdout before error
        self.assertEqual(result['stderr'], '') # Stderr from exec is not captured here, only exception
        self.assertIsNotNone(result['exception'])
        self.assertIn("ValueError: sandbox test error", result['exception'])
        self.assertIn("Traceback (most recent call last):", result['exception'])
        mock_conn_child_end.close.assert_called_once()

    def test_execute_sandboxed_code_syntax_error(self):
        mock_conn_child_end = MagicMock()
        code = "print 'bad syntax" # Syntax error
        _execute_sandboxed_code(code, mock_conn_child_end)
        
        mock_conn_child_end.send.assert_called_once()
        args, _ = mock_conn_child_end.send.call_args
        result = args[0]
        
        self.assertFalse(result['success'])
        self.assertIsNotNone(result['exception'])
        self.assertIn("SyntaxError", result['exception'])
        mock_conn_child_end.close.assert_called_once()

    def test_execute_sandboxed_code_stderr_output(self):
        mock_conn_child_end = MagicMock()
        code = "import sys\nsys.stderr.write('This is a stderr message\\n')"
        _execute_sandboxed_code(code, mock_conn_child_end)
        
        mock_conn_child_end.send.assert_called_once()
        args, _ = mock_conn_child_end.send.call_args
        result = args[0]
        
        self.assertTrue(result['success']) # Code itself ran successfully
        self.assertEqual(result['stdout'], '')
        self.assertEqual(result['stderr'], 'This is a stderr message\n')
        self.assertIsNone(result['exception'])
        mock_conn_child_end.close.assert_called_once()


# Tests for the SubordinateAgent.execute_code method (sandboxing part)
class TestSubordinateAgentExecuteCodeSandboxing(unittest.TestCase):
    def setUp(self):
        self.mock_llm_client = MagicMock(spec=LLMInterface)
        self.agent = SubordinateAgent(prompt="Test", llm_client=self.mock_llm_client)
        self.agent.generated_code = "print('hello')" # Default valid code
        self.agent.is_syntax_valid = True # Assume syntax is pre-verified for these tests

    @patch('multiprocessing.Process')
    @patch('multiprocessing.Pipe')
    def test_execute_code_starts_process_and_gets_success(self, MockPipe, MockProcess):
        # Setup mocks for Pipe and Process
        mock_parent_conn = MagicMock()
        mock_child_conn = MagicMock() # Not used by parent, but created by Pipe
        MockPipe.return_value = (mock_parent_conn, mock_child_conn)
        
        mock_process_instance = MockProcess.return_value
        
        # Simulate successful execution result from child via pipe
        success_result = {'stdout': 'output', 'stderr': '', 'exception': None, 'success': True}
        # Configure poll to return True first (data available), then False to exit loop (if any)
        mock_parent_conn.poll.side_effect = [True, False] 
        mock_parent_conn.recv.return_value = success_result

        self.agent.execute_code()

        MockProcess.assert_called_once() # Check if Process was instantiated
        # Args for Process: (target=_execute_sandboxed_code, args=(self.generated_code, mock_child_conn_from_pipe))
        # We can be more specific here if needed by inspecting call_args
        self.assertEqual(MockProcess.call_args[1]['target'], _execute_sandboxed_code)

        mock_process_instance.start.assert_called_once()
        mock_process_instance.join.assert_called_once_with(timeout=self.agent.execution_timeout)
        
        self.assertTrue(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_output, 'output')
        self.assertTrue("code_executed_successfully" in self.agent.status)
        mock_parent_conn.close.assert_called_once()
        mock_process_instance.close.assert_called_once()


    @patch('multiprocessing.Process')
    @patch('multiprocessing.Pipe')
    def test_execute_code_timeout(self, MockPipe, MockProcess):
        mock_parent_conn, _ = MockPipe.return_value
        mock_process_instance = MockProcess.return_value
        
        # Simulate process.join() timing out by making is_alive return True after timeout
        mock_process_instance.is_alive.return_value = True # After join, it's still alive

        self.agent.execute_code()

        mock_process_instance.join.assert_called_once_with(timeout=self.agent.execution_timeout)
        mock_process_instance.terminate.assert_called_once() # Should be called if timeout
        if hasattr(mock_process_instance, 'kill'): # If kill is available (Py 3.7+)
            mock_process_instance.kill.assert_called_once() # Check if kill was attempted after terminate
        
        self.assertFalse(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_error, "Execution timed out.")
        self.assertTrue("error_execution_timeout" in self.agent.status)
        mock_parent_conn.close.assert_called_once()
        mock_process_instance.close.assert_called_once()

    @patch('multiprocessing.Process')
    @patch('multiprocessing.Pipe')
    def test_execute_code_receives_runtime_error_from_child(self, MockPipe, MockProcess):
        mock_parent_conn, _ = MockPipe.return_value
        mock_process_instance = MockProcess.return_value
        
        error_result = {'stdout': '', 'stderr': 'Error output', 'exception': 'Traceback...', 'success': False}
        mock_parent_conn.poll.return_value = True
        mock_parent_conn.recv.return_value = error_result
        
        # Simulate process finishing normally (is_alive is False after join)
        mock_process_instance.is_alive.return_value = False

        self.agent.execute_code()
        
        self.assertFalse(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_output, '')
        self.assertIn('Error output', self.agent.execution_error)
        self.assertIn('Traceback...', self.agent.execution_error)
        self.assertTrue("error_execution_runtime" in self.agent.status)
        mock_parent_conn.close.assert_called_once()
        mock_process_instance.close.assert_called_once()

    @patch('multiprocessing.Process')
    @patch('multiprocessing.Pipe')
    def test_execute_code_no_result_from_pipe(self, MockPipe, MockProcess):
        mock_parent_conn, _ = MockPipe.return_value
        mock_process_instance = MockProcess.return_value

        mock_process_instance.is_alive.return_value = False # Process finished
        mock_parent_conn.poll.return_value = False # But no data in pipe

        self.agent.execute_code()

        self.assertFalse(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_error, "Execution process finished but no result received.")
        self.assertTrue("error_execution_no_result" in self.agent.status)
        mock_parent_conn.close.assert_called_once()
        mock_process_instance.close.assert_called_once()


if __name__ == '__main__':
    # This allows running the tests directly from this file
    # Adjust path if subordinate_agent is not in the root or PYTHONPATH
    if '..' not in sys.path:
         sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from subordinate_agent import SubordinateAgent, _execute_sandboxed_code # Ensure _execute is imported if used in tests
    from llm_interface import LLMInterface # For TestSubordinateAgent setup
    unittest.main()
