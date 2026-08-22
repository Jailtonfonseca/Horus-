import io
import sys
import traceback
import multiprocessing # For sandboxing
import multiprocessing.connection
from llm_interface import LLMInterface

# This function must be defined at the top level of the module for pickling.
def _execute_sandboxed_code(code_string: str, conn: multiprocessing.connection.Connection):
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    redirected_stdout = io.StringIO()
    redirected_stderr = io.StringIO()
    sys.stdout = redirected_stdout
    sys.stderr = redirected_stderr
    
    result = {
        'stdout': '',
        'stderr': '',
        'exception': None,
        'success': False
    }

    try:
        exec(code_string, {'__builtins__': __builtins__}, {})
        result['success'] = True
    except Exception:
        result['exception'] = traceback.format_exc()
        result['success'] = False
    finally:
        result['stdout'] = redirected_stdout.getvalue()
        result['stderr'] = redirected_stderr.getvalue()
        
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        
        try:
            conn.send(result)
        except Exception:
            pass 
        finally:
            conn.close()


class SubordinateAgent:
    """
    A subordinate agent responsible for generating and validating code based on a prompt,
    using a provided LLM client, with an iterative debugging loop and sandboxed execution.
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
        """
        self.prompt = prompt
        self.llm_client = llm_client
        self.generated_code = None
        self.status = "initialized"
        
        # Iterative debugging attributes
        self.max_correction_attempts = int(kwargs.get('max_correction_attempts', 3))
        self.execution_timeout = float(kwargs.get('execution_timeout', 10.0))
        self.correction_attempts = 0
        self.generation_history = [] # Stores details of each generation attempt

        # Attributes for syntax checking, execution, dependencies (will be set by respective methods)
        self.is_syntax_valid = None
        self.syntax_error_message = None
        self.execution_successful = None
        self.execution_output = None
        self.execution_error = None
        self.dependencies = set()
        self.dependencies_installed_successfully = None
        self.installation_logs = []

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
                if self.correction_attempts < self.max_correction_attempts:
                    print(f"LLM generation failed on attempt {self.correction_attempts}: {e}")
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
            self.execute_code()
            if not self.execution_successful:
                last_error_type, last_error_message = "Runtime", self.execution_error
                self.status = f"attempt_{self.correction_attempts}_runtime_error"
                attempt_details.update({'error_type': last_error_type, 'error_message': last_error_message, 'status': self.status})
                self.generation_history.append(attempt_details)
                if self.correction_attempts < self.max_correction_attempts:
                    current_llm_prompt = self._create_fix_prompt(initial_user_prompt, self.generated_code, last_error_message, last_error_type, self.correction_attempts + 1)
                continue

            overall_success = True
            self.status = f"attempt_{self.correction_attempts}_success"
            attempt_details.update({'error_type': None, 'error_message': None, 'status': self.status})
            self.generation_history.append(attempt_details)
            if self.dependencies:
                self.install_dependencies()
            break

        if not overall_success:
            self.status = f"failed_{last_error_type.lower() if last_error_type else 'unknown_error'}_after_{self.max_correction_attempts}_attempts"
        else:
            self.status = f"success_on_attempt_{self.correction_attempts}"

    def regenerate_with_new_prompt(self, new_prompt: str):
        """
        Regenerates code using a new prompt, leveraging the iterative debugging loop.

        Resets relevant status attributes and then calls attempt_code_generation_and_execution().

        Args:
            new_prompt: The new prompt to use for code generation.
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
        The initial prompt for this process is self.prompt.
        """
        self.attempt_code_generation_and_execution(initial_user_prompt=self.prompt)

    def verify_syntax(self) -> bool:
        """
        Verifies the Python syntax of the generated code using the ast module.

        Returns:
            True if the syntax is valid, False otherwise.
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
            self.status = "syntax_verified"
            self.identify_dependencies()
            return True
        except SyntaxError as e:
            self.is_syntax_valid = False
            self.syntax_error_message = str(e)
            self.status = f"error_syntax_invalid: {e}"
            return False

    def execute_code(self):
        """
        Executes the generated code in a sandboxed environment using multiprocessing.Process.
        Captures stdout, stderr, and any exceptions during execution.
        Stores execution success status and any output/error messages.
        Uses a timeout (self.execution_timeout) to prevent runaway code.
        """
        self.execution_output = ""
        self.execution_error = ""
        self.execution_successful = False

        if not self.generated_code:
            self.status = "error_execution_no_code"
            self.execution_error = "No code generated to execute."
            return

        if hasattr(self, 'is_syntax_valid') and not self.is_syntax_valid:
            self.status = "error_execution_syntax_invalid"
            self.execution_error = f"Syntax error prevented execution: {self.syntax_error_message}"
            return

        parent_conn, child_conn = multiprocessing.Pipe()
        process = multiprocessing.Process(
            target=_execute_sandboxed_code,
            args=(self.generated_code, child_conn)
        )
        process.daemon = True

        try:
            process.start()
            process.join(timeout=self.execution_timeout)

            if process.is_alive():
                process.terminate()
                process.join(timeout=1) 
                if process.is_alive() and hasattr(process, 'kill'):
                    try:
                        process.kill()
                    except Exception:
                        pass
                    process.join(timeout=0.5)

                self.execution_error = "Execution timed out."
                self.execution_successful = False
                self.status = "error_execution_timeout"
            else:
                if parent_conn.poll(timeout=0.2):
                    result = parent_conn.recv()
                    self.execution_output = result.get('stdout', '')
                    self.execution_error = result.get('stderr', '')
                    
                    if result.get('exception'):
                        if result['exception'] not in self.execution_error:
                             self.execution_error += f"\nSubprocess Exception: {result['exception']}"
                        self.execution_successful = False
                        self.status = "error_execution_runtime"
                    else:
                        self.execution_successful = result.get('success', False)
                        if self.execution_successful:
                            self.status = "code_executed_successfully"
                            if self.execution_error:
                                self.status = "code_executed_with_stderr"
                        else:
                            self.status = "error_execution_unknown_in_subprocess" 
                            if not self.execution_error and not result.get('exception'):
                                self.execution_error = "Execution failed in subprocess without explicit exception or stderr."
                else:
                    self.execution_error = "Execution process finished but no result received."
                    self.execution_successful = False
                    self.status = "error_execution_no_result"
        except Exception as e:
            self.execution_error = f"Parent process error during sandboxed execution: {str(e)}\n{traceback.format_exc()}"
            self.execution_successful = False
            self.status = "error_execution_host_error"
        finally:
            if parent_conn:
                try:
                    parent_conn.close()
                except Exception: pass
            if process: 
                if process.is_alive(): 
                    try:
                        process.terminate()
                        process.join(timeout=0.5)
                        if process.is_alive() and hasattr(process, 'kill'):
                            process.kill()
                    except Exception: pass
                try:
                    process.close()
                except Exception: pass

    def identify_dependencies(self):
        """
        Identifies import statements in the generated code using AST.
        Stores unique module names in self.dependencies.
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
            self.status = "dependencies_identified"
        except Exception as e:
            self.status = f"error_dependency_identification: {e}"
            print(f"Error identifying dependencies: {e}")

    def install_dependencies(self):
        """
        Simulates the installation of identified dependencies.
        """
        if not hasattr(self, 'dependencies') or not self.dependencies:
            self.status = "info_no_dependencies_to_install"
            self.dependencies_installed_successfully = True
            print("No dependencies identified to install.")
            return

        self.dependencies_installed_successfully = True
        self.installation_logs = []
        print("Attempting to install dependencies (simulation)...")

        for dep_name in self.dependencies:
            log_message = f"Attempting to install {dep_name}... (simulation)"
            print(log_message)
            self.installation_logs.append(log_message)

        if self.dependencies_installed_successfully:
            self.status = "dependencies_installed_simulated"
            print("All dependencies processed (simulation).")
        else:
            print("One or more dependencies failed to install (simulation).")

    def validate_code(self):
        """
        Validates the generated code.
        """
        pass

    def manage_dependencies(self):
        """
        Manages dependencies for the generated code.
        """
        pass
