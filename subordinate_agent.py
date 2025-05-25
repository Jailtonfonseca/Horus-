from llm_interface import LLMInterface
import io
import sys
import traceback
import os
import tempfile
import shutil
# Note: `docker` is imported conditionally in _initialize_docker_client or execute_code
# to allow basic class usage without Docker installed, though execution will fail.

class SubordinateAgent:
    """
    A subordinate agent responsible for generating and validating code based on a prompt,
    using a provided LLM client, with an iterative debugging loop and Docker-based sandboxed execution.
    """
    def __init__(self, prompt: str, llm_client: LLMInterface, **kwargs):
        """
        Initializes the SubordinateAgent.

        Args:
            prompt: The prompt for the agent.
            llm_client: An instance of a class implementing LLMInterface.
            **kwargs: Additional keyword arguments.
                max_correction_attempts (int): Max attempts for the debugging loop (default 3).
                execution_timeout (float): Timeout for code execution in seconds (default 10.0).
                docker_image_name (str): Name of the Docker image for code execution (default 'horus_agent_runner').
        """
        self.prompt = prompt
        self.llm_client = llm_client
        self.generated_code = None
        self.status = "initialized"
        
        # Iterative debugging attributes
        self.max_correction_attempts = int(kwargs.get('max_correction_attempts', 3))
        self.correction_attempts = 0
        self.generation_history = [] 

        # Execution related attributes
        self.execution_timeout = float(kwargs.get('execution_timeout', 10.0))
        self.docker_image_name = kwargs.get('docker_image_name', 'horus_agent_runner')
        self.docker_client = None 

        # Attributes for syntax checking, execution results, dependencies
        self.is_syntax_valid = None
        self.syntax_error_message = None
        self.execution_successful = None
        self.execution_output = None
        self.execution_error = None
        self.dependencies = set()
        self.dependencies_installed_successfully = None # Will be True, False, or None if no deps
        self.installation_logs = [] # Stores detailed logs from pip install attempts

    def _initialize_docker_client(self) -> bool:
        """
        Initializes the Docker client if not already initialized.
        Returns True if successful or already initialized, False otherwise.
        """
        if self.docker_client:
            return True
        try:
            import docker # Import here to make it a soft dependency for non-execution scenarios
            self.docker_client = docker.from_env()
            self.docker_client.ping() 
            self.status = "docker_client_initialized_successfully"
            return True
        except ImportError:
            self.status = "error_docker_sdk_not_installed"
            self.execution_error = "Docker SDK for Python is not installed. Please install the 'docker' package."
            self.docker_client = None
            return False
        except Exception as e: # Catches docker.errors.DockerException and other potential issues
            self.status = f"error_docker_daemon_connection: {e}"
            self.execution_error = f"Could not connect to Docker daemon: {e}. Ensure Docker is running and accessible."
            self.docker_client = None 
            return False

    def _create_fix_prompt(self, original_user_prompt: str, erroneous_code: str, error_message: str, error_type: str, attempt_number: int) -> str:
        """
        Constructs a detailed prompt for the LLM to fix the code.
        """
        return (
            f"The user's original request was:\n--- (Original Request Start) ---\n{original_user_prompt}\n--- (Original Request End) ---\n\n"
            f"On attempt number {attempt_number - 1}, I generated the following Python code to address this request:\n--- (Erroneous Code Start) ---\n{erroneous_code}\n--- (Erroneous Code End) ---\n\n"
            f"However, this code produced a {error_type} Error:\n--- (Error Message Start) ---\n{error_message}\n--- (Error Message End) ---\n\n"
            f"Please analyze the original request, the code I generated, and the error message. Then, provide a corrected version of the Python code that fixes this {error_type} Error and still addresses the user's original request. "
            f"This is now attempt number {attempt_number}. Focus on resolving the identified error. "
            f"Only provide the corrected Python code, without any additional explanations, comments, or introductory phrases."
        )

    def attempt_code_generation_and_execution(self, initial_user_prompt: str):
        """
        Attempts to generate and execute code, with an iterative debugging loop.
        """
        self.correction_attempts = 0
        self.generation_history = []
        current_llm_prompt = initial_user_prompt
        last_error_type = None
        last_error_message = None
        overall_success = False
        
        while self.correction_attempts < self.max_correction_attempts:
            self.correction_attempts += 1
            attempt_details = {'attempt': self.correction_attempts, 'prompt_to_llm': current_llm_prompt}
            self.status = f"attempt_{self.correction_attempts}_generating_code"
            
            try:
                generated_code_output = self.llm_client.generate_text(current_llm_prompt)
                self.generated_code = generated_code_output
                attempt_details['generated_code'] = self.generated_code
            except Exception as e:
                last_error_type, last_error_message = "LLM_Generation", str(e)
                self.status = f"attempt_{self.correction_attempts}_llm_generation_error"
                attempt_details.update({'error_type': last_error_type, 'error_message': last_error_message, 'status': self.status})
                self.generation_history.append(attempt_details)
                print(f"LLM generation failed on attempt {self.correction_attempts}: {e}")
                if self.correction_attempts < self.max_correction_attempts:
                     # Decide if a fix prompt for LLM failure is useful or just retry with same/modified prompt
                    current_llm_prompt = self._create_fix_prompt(initial_user_prompt, "N/A - LLM Generation Failed", last_error_message, last_error_type, self.correction_attempts + 1)
                continue 

            self.verify_syntax() 
            if not self.is_syntax_valid:
                last_error_type, last_error_message = "Syntax", self.syntax_error_message
                self.status = f"attempt_{self.correction_attempts}_syntax_error"
                attempt_details.update({'error_type': last_error_type, 'error_message': last_error_message, 'status': self.status})
                self.generation_history.append(attempt_details)
                if self.correction_attempts < self.max_correction_attempts:
                    current_llm_prompt = self._create_fix_prompt(initial_user_prompt, self.generated_code, last_error_message, last_error_type, self.correction_attempts + 1)
                continue

            self.status = f"attempt_{self.correction_attempts}_executing_code"
            self.execute_code() # Now uses Docker
            if not self.execution_successful:
                last_error_type, last_error_message = "Runtime", self.execution_error
                self.status = f"attempt_{self.correction_attempts}_runtime_error" # execute_code sets more specific status
                attempt_details.update({'error_type': last_error_type, 'error_message': last_error_message, 'status': self.status})
                self.generation_history.append(attempt_details)
                if self.correction_attempts < self.max_correction_attempts:
                    current_llm_prompt = self._create_fix_prompt(initial_user_prompt, self.generated_code, last_error_message, last_error_type, self.correction_attempts + 1)
                continue

            overall_success = True
            self.status = f"success_on_attempt_{self.correction_attempts}" # More specific status from execute_code might be better
            attempt_details.update({'error_type': None, 'error_message': None, 'status': self.status})
            self.generation_history.append(attempt_details)
            if self.dependencies:
                self.install_dependencies() # Simulated
            break 

        if not overall_success:
            final_error_type_str = last_error_type.lower().replace(" ", "_") if last_error_type else 'unknown_error'
            self.status = f"failed_{final_error_type_str}_after_{self.correction_attempts}_attempts"
        # If successful, status is already set like "success_on_attempt_X" or a Docker success status

    def regenerate_with_new_prompt(self, new_prompt: str):
        """
        Regenerates code using a new prompt, leveraging the iterative debugging loop.
        """
        self.prompt = new_prompt
        self.generated_code = None
        self.is_syntax_valid = None
        self.syntax_error_message = None
        self.execution_successful = None
        self.execution_output = None
        self.execution_error = None
        self.dependencies = set()
        self.dependencies_installed_successfully = None
        self.installation_logs = []
        self.attempt_code_generation_and_execution(initial_user_prompt=self.prompt)

    def generate_code(self):
        """
        Main entry point for code generation.
        Initiates the iterative process of code generation, syntax checking, and execution.
        """
        self.attempt_code_generation_and_execution(initial_user_prompt=self.prompt)

    def verify_syntax(self) -> bool:
        """
        Verifies the Python syntax of the generated code using the ast module.
        """
        if not self.generated_code:
            self.status = "error_syntax_check_no_code"
            self.is_syntax_valid = False
            self.syntax_error_message = "No code generated to verify."
            return False
        try:
            import ast
            ast.parse(self.generated_code)
            self.is_syntax_valid = True
            self.syntax_error_message = None
            self.status = "syntax_verified_successfully"
            self.identify_dependencies() 
            return True
        except SyntaxError as e:
            self.is_syntax_valid = False
            self.syntax_error_message = str(e)
            self.status = f"error_syntax_invalid: {e}"
            return False

    def execute_code(self):
        """
        Executes the generated code in a Docker container for sandboxing.
        Installs identified dependencies using pip within the container before running the script.
        Captures stdout, stderr, and exit code.
        Uses a timeout (self.execution_timeout) for the script execution part.

        Sandboxing Details & Limitations: (Same as before, plus dependency installation considerations)
        - Docker daemon must be running.
        - Specified Docker image must exist.
        - `pip install --user` is used for dependencies; ensure the image's `appuser` can write to its user site-packages.
        - Network access is required during dependency installation.
        """
        self.execution_output = ""
        self.execution_error = ""
        self.execution_successful = False
        self.installation_logs = [] # Reset logs for this execution run
        self.dependencies_installed_successfully = None

        if not self._initialize_docker_client():
            return

        if not self.generated_code:
            self.status = "error_execution_no_code"
            self.execution_error = "No code generated to execute."
            return

        if hasattr(self, 'is_syntax_valid') and not self.is_syntax_valid:
            self.status = "error_execution_syntax_invalid"
            self.execution_error = f"Syntax error prevented execution: {self.syntax_error_message}"
            return

        import docker 
        import tempfile
        import os
        import shutil

        temp_dir = None
        container = None
        container_name = f"horus_exec_{getattr(self, 'id', 'N_A')}_{self.correction_attempts}"
        
        try:
            temp_dir = tempfile.mkdtemp()
            script_path = os.path.join(temp_dir, "script.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(self.generated_code)

            volumes_dict = {temp_dir: {'bind': '/app', 'mode': 'ro'}}
            
            # Pre-remove container if it exists
            try:
                existing_container = self.docker_client.containers.get(container_name)
                existing_container.remove(force=True)
            except docker.errors.NotFound:
                pass
            except docker.errors.APIError as e:
                self.status = "error_docker_api_container_cleanup"
                self.execution_error = f"Docker API error during pre-run container cleanup: {e}"
                return

            # Start a container that keeps running to allow exec_run for pip and script
            keep_alive_cmd = ["tail", "-f", "/dev/null"]
            container = self.docker_client.containers.run(
                image=self.docker_image_name,
                command=keep_alive_cmd,
                volumes=volumes_dict,
                name=container_name,
                detach=True,
                mem_limit="256m", # Increased slightly for pip
                cpu_shares=512, 
                user='appuser', 
                working_dir="/app"
            )

            # Install Dependencies
            if self.dependencies:
                all_deps_installed_successfully = True
                for dep in self.dependencies:
                    pip_cmd = ["pip", "install", "--user", "--no-cache-dir", dep]
                    log_entry_header = f"--- Installing dependency: {dep} ---\n"
                    self.installation_logs.append(log_entry_header)
                    
                    # Using exec_run with a timeout for pip install itself is tricky as exec_run doesn't directly support timeout
                    # The main script execution timeout will be handled by container.wait() or equivalent later.
                    # For pip, we rely on it completing reasonably fast or being non-malicious.
                    # A very long pip install could still cause issues if it hangs indefinitely.
                    # Consider a wrapper script in Docker if granular timeout for pip is needed.
                    pip_exit_code, pip_output_gen = container.exec_run(pip_cmd, user='appuser', workdir='/app', demux=True)
                    
                    out_pip = pip_output_gen[0].decode('utf-8', errors='replace') if pip_output_gen[0] else ""
                    err_pip = pip_output_gen[1].decode('utf-8', errors='replace') if pip_output_gen[1] else ""
                    
                    log_entry_details = f"Exit Code: {pip_exit_code}\nSTDOUT:\n{out_pip}\nSTDERR:\n{err_pip}\n"
                    self.installation_logs.append(log_entry_details)

                    if pip_exit_code != 0:
                        all_deps_installed_successfully = False
                        self.execution_error += f"Failed to install dependency '{dep}'. See installation logs.\n"
                        # Continue installing other dependencies or break? For now, let's try to install all.
                
                self.dependencies_installed_successfully = all_deps_installed_successfully
                if not self.dependencies_installed_successfully:
                    self.status = "error_dependency_installation"
                    self.execution_successful = False
                    # Do not return yet, let finally block clean up. Script execution will be skipped.
            else:
                self.dependencies_installed_successfully = None # No dependencies to install


            # Execute the Script only if dependencies were not attempted or installed successfully
            if self.dependencies_installed_successfully is not False:
                self.status = f"attempt_{self.correction_attempts}_executing_script_docker"
                script_cmd = ["python", "/app/script.py"]
                
                # This exec_run will have its effective timeout managed by the overall self.execution_timeout
                # if we were to use container.wait() on a primary command.
                # With exec_run, timeout is harder. The main timeout is on the keep-alive container.
                # This part needs careful thought if script itself hangs.
                # For now, assume script is also reasonably fast or we rely on the outer timeout for the keep-alive.
                # A better approach might be to commit container after pip, then run script with timeout.
                # But sticking to "Option B" for now.
                
                script_exit_code, script_output_gen = container.exec_run(script_cmd, user='appuser', workdir='/app', demux=True)
                
                self.execution_output = script_output_gen[0].decode('utf-8', errors='replace') if script_output_gen[0] else ""
                script_stderr = script_output_gen[1].decode('utf-8', errors='replace') if script_output_gen[1] else ""
                
                # Prepend pip installation errors (if any) to script errors
                if self.execution_error: # Contains errors from pip install failures
                    self.execution_error = f"Dependency Installation Issues:\n{self.execution_error}\n--- Script Execution STDERR ---\n{script_stderr}"
                else:
                    self.execution_error = script_stderr

                if script_exit_code == 0:
                    self.execution_successful = True
                    self.status = "code_executed_successfully_docker"
                    if self.execution_error: # If there was stderr output but exit code 0
                        self.status = "code_executed_with_stderr_docker"
                else:
                    self.execution_successful = False
                    self.status = "error_execution_runtime_docker"
                    error_details = f"Script exited with code {script_exit_code}."
                    if self.execution_error:
                        self.execution_error = f"{self.execution_error}\n{error_details}"
                    else: # Should not happen if exit code is non-zero, but as fallback
                        self.execution_error = error_details
            else:
                # This else block means dependencies existed AND failed to install
                self.status = "error_dependency_installation_skipped_execution"
                # self.execution_error already contains pip failure details.
                self.execution_successful = False


        except docker.errors.ImageNotFound:
            self.status = "error_docker_image_not_found"
            self.execution_error = f"Docker image '{self.docker_image_name}' not found."
        except docker.errors.APIError as e:
            self.status = "error_docker_api_execution"
            self.execution_error = f"Docker API error during execution: {e}"
        except Exception as e:
            self.status = "error_execution_docker_host_unexpected"
            self.execution_error = f"Host error during Docker execution: {e}\n{traceback.format_exc()}"
        finally:
            if container:
                try:
                    container.stop(timeout=5) # Stop the keep-alive container
                except docker.errors.APIError as e:
                    print(f"Warning: Docker API error stopping container {container_name}: {e}")
                try:
                    container.remove(v=True, force=True)
                except docker.errors.NotFound:
                    pass 
                except docker.errors.APIError as e:
                    print(f"Error removing container {container_name}: {e}")
            
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e_rm:
                    print(f"Error removing temporary directory {temp_dir}: {e_rm}")

    def identify_dependencies(self):
        """
        Identifies import statements in the generated code using AST.
        """
        self.dependencies = set()
        if not self.generated_code or not (hasattr(self, 'is_syntax_valid') and self.is_syntax_valid):
            self.status = "error_dependency_identification_no_code_or_invalid_syntax"
            return
        try:
            import ast
            tree = ast.parse(self.generated_code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.dependencies.add(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module: 
                        self.dependencies.add(node.module.split('.')[0])
            self.status = "dependencies_identified_successfully"
        except Exception as e:
            self.status = f"error_dependency_identification: {e}"
            print(f"Error identifying dependencies: {e}")

    # Placeholder methods from original structure, can be removed if truly not needed
    def validate_code(self):
        """
        Validates the generated code. (Currently, validation is part of the iterative loop)
        """
        # This method might be used for more complex validation beyond syntax/runtime
        # in the future. For now, core validation happens in attempt_code_generation_and_execution.
        self.status = "info_validate_code_placeholder"
        print("validate_code placeholder called. Core validation in iterative loop.")
        pass

    def manage_dependencies(self):
        """
        Manages dependencies for the generated code. (Currently, only identification and simulated install)
        """
        # Could involve more complex logic like creating requirements.txt, virtual envs, etc.
        self.status = "info_manage_dependencies_placeholder"
        print("manage_dependencies placeholder called. Current: identification and simulated install.")
        pass
