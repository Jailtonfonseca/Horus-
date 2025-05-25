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


# Tests for the SubordinateAgent.execute_code method (Docker sandboxing part)
# These tests will mock the docker library interactions.
@patch('subordinate_agent.docker', create=True) # Mock the docker module in subordinate_agent.py
class TestSubordinateAgentExecuteCodeDocker(unittest.TestCase):
    def setUp(self):
        self.mock_llm_client = MagicMock(spec=LLMInterface)
        # Initialize agent with a specific docker_image_name for tests
        self.agent = SubordinateAgent(
            prompt="Test Docker Execution", 
            llm_client=self.mock_llm_client,
            docker_image_name="test_horus_runner" 
        )
        self.agent.generated_code = "print('hello from docker')"
        self.agent.is_syntax_valid = True
        self.agent.id = "test_agent_id" # For container naming

        # Mock tempfile and shutil for cleanup verification
        self.mock_tempfile_patch = patch('subordinate_agent.tempfile.mkdtemp')
        self.mock_shutil_patch = patch('subordinate_agent.shutil.rmtree')
        self.MockMkdtmp = self.mock_tempfile_patch.start()
        self.MockRmtree = self.mock_shutil_patch.start()
        self.MockMkdtmp.return_value = "/fake/temp_dir"


    def tearDown(self):
        self.mock_tempfile_patch.stop()
        self.mock_shutil_patch.stop()

    def _configure_docker_mocks(self, MockDockerModule):
        mock_docker_client = MagicMock()
        MockDockerModule.from_env.return_value = mock_docker_client
        
        mock_container = MagicMock()
        mock_docker_client.containers.run.return_value = mock_container
        mock_docker_client.containers.get.return_value = mock_container # For pre-run cleanup
        
        return mock_docker_client, mock_container

    def test_execute_code_success_no_dependencies(self, MockDockerModule):
        mock_docker_client, mock_container = self._configure_docker_mocks(MockDockerModule)
        
        # Script execution mock
        mock_container.exec_run.return_value = (0, (b"hello from docker\n", b"")) # exit_code, (stdout, stderr)
        
        self.agent.dependencies = set() # No dependencies
        self.agent.execute_code()

        self.assertTrue(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_output, "hello from docker\n")
        self.assertEqual(self.agent.execution_error, "")
        self.assertTrue("code_executed_successfully_docker" in self.agent.status)
        self.assertIsNone(self.agent.dependencies_installed_successfully) # No deps, so should be None
        self.assertEqual(len(self.agent.installation_logs), 0)
        
        mock_docker_client.containers.run.assert_called_once()
        mock_container.exec_run.assert_called_once_with(
            ["python", "/app/script.py"], user='appuser', workdir='/app', demux=True
        )
        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once_with(v=True, force=True)
        self.MockRmtree.assert_called_once_with("/fake/temp_dir")


    def test_execute_code_success_with_dependencies(self, MockDockerModule):
        mock_docker_client, mock_container = self._configure_docker_mocks(MockDockerModule)
        self.agent.dependencies = {"requests", "numpy"}

        # Mock pip install (called twice) then script execution
        mock_container.exec_run.side_effect = [
            (0, (b"requests installed\n", b"")),  # pip install requests
            (0, (b"numpy installed\n", b"")),     # pip install numpy
            (0, (b"script output\n", b""))        # python script.py
        ]

        self.agent.execute_code()

        self.assertTrue(self.agent.execution_successful)
        self.assertTrue(self.agent.dependencies_installed_successfully)
        self.assertEqual(self.agent.execution_output, "script output\n")
        self.assertIn("requests installed", self.agent.installation_logs[1]) # Index 1 for first dep log details
        self.assertIn("numpy installed", self.agent.installation_logs[3])   # Index 3 for second dep log details
        self.assertEqual(mock_container.exec_run.call_count, 3)
        
        pip_calls = [
            call(["pip", "install", "--user", "--no-cache-dir", "requests"], user='appuser', workdir='/app', demux=True),
            call(["pip", "install", "--user", "--no-cache-dir", "numpy"], user='appuser', workdir='/app', demux=True)
        ]
        # Note: Order of dependencies in set is not guaranteed, so check calls flexibly
        mock_container.exec_run.assert_any_call(*pip_calls[0][0], **pip_calls[0][1])
        mock_container.exec_run.assert_any_call(*pip_calls[1][0], **pip_calls[1][1])
        mock_container.exec_run.assert_called_with(["python", "/app/script.py"], user='appuser', workdir='/app', demux=True) # Last call for script
        self.MockRmtree.assert_called_once_with("/fake/temp_dir")


    def test_execute_code_dependency_install_fails(self, MockDockerModule):
        mock_docker_client, mock_container = self._configure_docker_mocks(MockDockerModule)
        self.agent.dependencies = {"failed_package"}

        # Mock pip install failure
        mock_container.exec_run.return_value = (1, (b"", b"Error installing failed_package\n")) # pip install failed_package

        self.agent.execute_code()

        self.assertFalse(self.agent.execution_successful)
        self.assertFalse(self.agent.dependencies_installed_successfully)
        self.assertIn("Failed to install dependency 'failed_package'", self.agent.execution_error)
        self.assertIn("Error installing failed_package", self.agent.installation_logs[1])
        self.assertTrue("error_dependency_installation_skipped_execution" in self.agent.status)
        
        # Ensure script execution was NOT called
        # If pip was the only call to exec_run:
        mock_container.exec_run.assert_called_once_with(
            ["pip", "install", "--user", "--no-cache-dir", "failed_package"], user='appuser', workdir='/app', demux=True
        )
        self.MockRmtree.assert_called_once_with("/fake/temp_dir")


    def test_execute_code_script_runtime_error(self, MockDockerModule):
        mock_docker_client, mock_container = self._configure_docker_mocks(MockDockerModule)
        self.agent.dependencies = set()

        # Mock script execution failure
        mock_container.exec_run.return_value = (1, (b"", b"Runtime error in script\n"))

        self.agent.execute_code()

        self.assertFalse(self.agent.execution_successful)
        self.assertEqual(self.agent.execution_output, "")
        self.assertIn("Runtime error in script", self.agent.execution_error)
        self.assertIn("Script exited with code 1", self.agent.execution_error)
        self.assertTrue("error_execution_runtime_docker" in self.agent.status)
        self.MockRmtree.assert_called_once_with("/fake/temp_dir")

    def test_execute_code_docker_image_not_found(self, MockDockerModule):
        mock_docker_client, _ = self._configure_docker_mocks(MockDockerModule)
        # Simulate ImageNotFound when containers.run is called
        mock_docker_client.containers.run.side_effect = MockDockerModule.errors.ImageNotFound("Image not found")
        
        self.agent.execute_code()

        self.assertFalse(self.agent.execution_successful)
        self.assertIn(f"Docker image '{self.agent.docker_image_name}' not found", self.agent.execution_error)
        self.assertTrue("error_docker_image_not_found" in self.agent.status)
        # self.MockRmtree should still be called due to finally block
        self.MockRmtree.assert_called_once_with("/fake/temp_dir")


    def test_execute_code_docker_api_error_on_run(self, MockDockerModule):
        mock_docker_client, _ = self._configure_docker_mocks(MockDockerModule)
        mock_docker_client.containers.run.side_effect = MockDockerModule.errors.APIError("Docker API Error on run")

        self.agent.execute_code()

        self.assertFalse(self.agent.execution_successful)
        self.assertIn("Docker API error during execution: Docker API Error on run", self.agent.execution_error)
        self.assertTrue("error_docker_api_execution" in self.agent.status)
        self.MockRmtree.assert_called_once_with("/fake/temp_dir")


    def test_docker_client_initialization_fails(self, MockDockerModule):
        # Test the case where _initialize_docker_client fails
        MockDockerModule.from_env.side_effect = MockDockerModule.errors.DockerException("Cannot connect to Docker daemon")
        
        # Reset agent's docker_client to force re-initialization attempt
        self.agent.docker_client = None 
        self.agent.execute_code()

        self.assertFalse(self.agent.execution_successful)
        self.assertIn("Could not connect to Docker daemon", self.agent.execution_error)
        self.assertTrue("error_docker_daemon_connection" in self.agent.status)
        # Temp dir should not be created if docker client init fails early
        self.MockMkdtmp.assert_not_called()
        self.MockRmtree.assert_not_called()


    def test_execute_code_timeout_on_container_wait(self, MockDockerModule):
        # This test is more about the container.wait() part if the primary command was long-running
        # Our current model runs a keep-alive, then exec_run. exec_run itself is blocking.
        # The timeout in execute_code is for container.wait(), which applies to the keep-alive container.
        # If a script via exec_run hangs, it will block the exec_run call, and the container.stop()
        # in the finally block is the main mechanism to stop it. The container.wait() timeout
        # in the current structure is for the initial keep-alive command, which shouldn't timeout.
        #
        # To properly test script timeout, we'd need a more complex setup or a different container run pattern.
        # For now, we'll test timeout on container.run() if it were blocking and had a timeout param,
        # or accept that exec_run calls don't use self.execution_timeout directly.
        # The current execute_code has `container.wait(timeout=self.execution_timeout)` but this is
        # on the detached container running `tail -f /dev/null`. This wait would indeed timeout.
        
        mock_docker_client, mock_container = self._configure_docker_mocks(MockDockerModule)
        
        # Make the initial container.run() call (which is detached and runs tail -f /dev/null)
        # then make the container.wait() call raise a Timeout exception.
        # This is a bit artificial as tail -f /dev/null itself won't complete to trigger wait() in a normal sense,
        # but this tests the exception handling around container.wait().
        
        # This part is tricky. The `container.wait()` is on the detached container.
        # However, the actual script execution happens via `exec_run`.
        # The timeout `self.execution_timeout` is NOT applied to `exec_run`.
        # The current structure of `execute_code` does not have a direct timeout for the script execution part via `exec_run`.
        # The container.wait() is on the keep-alive command.
        # Let's simulate the keep-alive container itself having an issue that makes `wait` timeout.
        
        mock_container.wait.side_effect = MockDockerModule.errors.Timeout("Container wait timed out")
        # This Timeout is from docker.errors, not the built-in TimeoutError.
        # The code has `except (docker.errors.Timeout, TimeoutError):`

        self.agent.dependencies = set() # No dependencies to simplify
        self.agent.execute_code()

        self.assertFalse(self.agent.execution_successful)
        self.assertIn(f"Execution timed out after {self.agent.execution_timeout} seconds in Docker", self.agent.execution_error)
        self.assertTrue("error_execution_timeout_docker" in self.agent.status)
        mock_container.stop.assert_called_once() # Should be called if timeout
        self.MockRmtree.assert_called_once_with("/fake/temp_dir")


if __name__ == '__main__':
    # This allows running the tests directly from this file
    # Adjust path if subordinate_agent is not in the root or PYTHONPATH
    if '..' not in sys.path:
         sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    # from subordinate_agent import SubordinateAgent, _execute_sandboxed_code # _execute_sandboxed_code removed
    from subordinate_agent import SubordinateAgent
    from llm_interface import LLMInterface # For TestSubordinateAgent setup
    import docker # For docker.errors in test setup if needed
    unittest.main()
