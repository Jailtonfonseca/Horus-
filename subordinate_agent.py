class SubordinateAgent:
    """
from llm_interface import LLMInterface
import io
import sys
import traceback
import multiprocessing # For sandboxing

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
        # Using a restricted globals dictionary can add a minor layer,
        # but the process isolation is the primary sandbox here.
        # For more advanced restriction within the exec, RestrictedPython would be needed.
        # A more restricted builtins could be:
        # safe_builtins = {k: __builtins__[k] for k in ['print', 'range', 'len', 'str', 'int', 'float', 'list', 'dict', 'set', 'tuple', 'True', 'False', 'None', 'abs', 'all', 'any', 'bool', 'callable', 'chr', 'divmod', 'getattr', 'hasattr', 'hash', 'hex', 'id', 'isinstance', 'issubclass', 'iter', 'max', 'min', 'next', 'oct', 'ord', 'pow', 'repr', 'round', 'sorted', 'sum', 'zip']}
        # exec(code_string, {'__builtins__': safe_builtins}, {})
        exec(code_string, {'__builtins__': __builtins__}, {}) # Pass a slightly safer builtins, empty locals
        result['success'] = True
    except Exception:
        result['exception'] = traceback.format_exc() # Get full traceback
        result['success'] = False
    finally:
        result['stdout'] = redirected_stdout.getvalue()
        result['stderr'] = redirected_stderr.getvalue()
        
        sys.stdout = old_stdout # Restore
        sys.stderr = old_stderr
        
        try:
            conn.send(result)
        except Exception as e:
            # If connection is broken, nothing much to do here. Parent will handle timeout or lack of data.
            # Optionally log this error from the child process side.
            # print(f"Child process: Error sending result: {e}", file=sys.__stderr__) # Use original stderr
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
        # Note: The prompt refers to 'attempt_number - 1' for the attempt that *failed*,
        # and 'attempt_number' for the *current* attempt to fix it.
        # The loop in attempt_code_generation_and_execution manages the actual self.correction_attempts.
        # When calling this, 'attempt_number' is the number of the upcoming attempt.
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
        
        # Ensure llm_client has model_name attribute or handle it appropriately
        # For this example, we assume llm_client either has a default or model_name is passed.
        # If model_name is specific to generate_text, it should be handled there.
        # Here, we assume llm_client.model_name is accessible if needed by generate_text internally,
        # or that generate_text can be called without it.
        # llm_model_name = getattr(self.llm_client, 'default_model_name', None) # Example

        while self.correction_attempts < self.max_correction_attempts:
            self.correction_attempts += 1
            attempt_details = {'attempt': self.correction_attempts, 'prompt_to_llm': current_llm_prompt}
            self.status = f"attempt_{self.correction_attempts}_generating_code"
            
            try:
                # Assuming llm_client.generate_text can take model_name if available/needed
                # or uses its own default if model_name is None.
                generated_code_output = self.llm_client.generate_text(
                    current_llm_prompt
                    # model_name=llm_model_name # Pass if required by your LLMInterface/impl.
                )
                self.generated_code = generated_code_output
                attempt_details['generated_code'] = self.generated_code
            except Exception as e:
                last_error_type, last_error_message = "LLM_Generation", str(e)
                self.status = f"attempt_{self.correction_attempts}_llm_generation_error"
                attempt_details.update({'error_type': last_error_type, 'error_message': last_error_message, 'status': self.status})
                self.generation_history.append(attempt_details)
                # No point in creating a fix prompt if LLM generation itself failed.
                # Break or decide if this counts as a full attempt for retry logic.
                # For now, let it count and try to fix if possible (though prompt might be bad)
                if self.correction_attempts < self.max_correction_attempts:
                    # Create a generic fix prompt or re-use previous one if this was a retry
                    # This part is tricky if generation fails. For now, let's assume it's a code error.
                    # If the prompt itself is bad, this loop won't fix it.
                    # Re-prompting for a fix of a "generation error" is unlikely to work well.
                    # Consider breaking here or using a different strategy for generation errors.
                    # For this iteration, we'll assume the error is in the *generated* code,
                    # so if generation fails, we effectively can't make a fix prompt for that.
                    # The loop will end, and overall_success will be false.
                    print(f"LLM generation failed on attempt {self.correction_attempts}: {e}")
                continue # Or break, depending on desired behavior for LLM errors

            self.verify_syntax() # This calls identify_dependencies if syntax is valid
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
            break # Exit loop on success

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
        # Resetting these attributes here is important before starting a new generation cycle.
        # attempt_code_generation_and_execution also resets some of these (history, attempts),
        # but it's good practice to ensure a clean state for a "regeneration" call.
        self.generated_code = None
        self.is_syntax_valid = None
        self.syntax_error_message = None
        self.execution_successful = None
        self.execution_output = None
        self.execution_error = None
        self.dependencies = set()
        self.dependencies_installed_successfully = None
        self.installation_logs = []
        
        # The status will be set by attempt_code_generation_and_execution
        # self.status = "regenerating_with_new_prompt" # Or let the loop set initial status

        # Call the main iterative generation method with the new prompt
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
            self.identify_dependencies() # Call after successful syntax verification
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

        Sandboxing Details:
        - This method uses `multiprocessing.Process` to run the generated code in a separate
          process. This provides a basic level of isolation from the main application.
        - Standard output and standard error from the executed code are captured.
        - A timeout mechanism (self.execution_timeout) is in place to terminate processes 
          that run too long.
        - The `exec()` call within the sandboxed process uses `{'__builtins__': __builtins__}`
          for globals by default in `_execute_sandboxed_code`, which offers a slight restriction 
          but is not a comprehensive security sandbox. The primary isolation is the process boundary.

        Limitations:
        - Process-based sandboxing is not as secure as containerization (e.g., Docker) or
          virtualization. It can be susceptible to resource exhaustion attacks (e.g., fork bombs
          if the executed code can create subprocesses and system limits are not in place).
        - Inter-process communication via `multiprocessing.Pipe` relies on pickling, which can
          have issues with very complex or unpicklable objects (though here we primarily pass strings
          and basic types for results).
        - Direct access to the filesystem or network from the executed code is still possible
          within the permissions of the user running the Python application. Further OS-level
          sandboxing (like chroot, namespaces, or seccomp) would be needed for stronger
          restrictions and is not implemented here.
        - The effectiveness of `process.terminate()` and `process.kill()` can vary by OS and
          circumstances, and truly runaway processes might require more robust management.
        """
        # Clear previous results
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
        process.daemon = True # Ensure process doesn't outlive parent if parent crashes

        try:
            process.start()
            # Wait for the process to complete or timeout
            process.join(timeout=self.execution_timeout) # Use configured timeout

            if process.is_alive():
                # Process timed out
                process.terminate() # Try to terminate gracefully
                # Give it a moment to terminate, then kill if necessary and possible
                process.join(timeout=1) 
                if process.is_alive() and hasattr(process, 'kill'): # Python 3.7+
                    try:
                        process.kill() # Force kill
                    except Exception: # process might already be gone
                        pass
                    process.join(timeout=0.5)

                self.execution_error = "Execution timed out."
                self.execution_successful = False
                self.status = "error_execution_timeout"
            else:
                # Process completed, check for results
                if parent_conn.poll(timeout=0.2): # Check if there's data with a short timeout
                    result = parent_conn.recv()
                    self.execution_output = result.get('stdout', '')
                    self.execution_error = result.get('stderr', '') # Stderr from executed code
                    
                    if result.get('exception'):
                        # Append exception traceback to stderr if not already there
                        # (it should be if traceback.format_exc() was used)
                        if result['exception'] not in self.execution_error:
                             self.execution_error += f"\nSubprocess Exception: {result['exception']}"
                        self.execution_successful = False
                        self.status = "error_execution_runtime"
                    else:
                        self.execution_successful = result.get('success', False)
                        if self.execution_successful:
                            self.status = "code_executed_successfully"
                            if self.execution_error: # stderr output but no exception
                                self.status = "code_executed_with_stderr"
                        else:
                            # Should ideally be caught by 'exception' but as a fallback
                            self.status = "error_execution_unknown_in_subprocess" 
                            if not self.execution_error and not result.get('exception'):
                                self.execution_error = "Execution failed in subprocess without explicit exception or stderr."
                else:
                    self.execution_error = "Execution process finished but no result received."
                    self.execution_successful = False
                    self.status = "error_execution_no_result"
        except Exception as e:
            # Error in the parent process during setup or result handling
            self.execution_error = f"Parent process error during sandboxed execution: {str(e)}\n{traceback.format_exc()}"
            self.execution_successful = False
            self.status = "error_execution_host_error"
        finally:
            if parent_conn:
                try:
                    parent_conn.close()
                except Exception: pass # Ignore errors on close
            # child_conn is closed by the _execute_sandboxed_code function
            if process: 
                if process.is_alive(): 
                    try:
                        process.terminate()
                        process.join(timeout=0.5)
                        if process.is_alive() and hasattr(process, 'kill'):
                            process.kill()
                    except Exception: pass # Ignore errors on terminate/kill
                try:
                    process.close() # Release resources associated with the process object
                except Exception: pass # Ignore errors on close


    def regenerate_with_new_prompt(self, new_prompt: str):
        """
        Regenerates code using a new prompt.

        Resets relevant status attributes and then calls generate_code().

        Args:
            new_prompt: The new prompt to use for code generation.
        """
        self.prompt = new_prompt
        self.generated_code = None
        self.status = "regenerating"
        self.is_syntax_valid = None
        self.syntax_error_message = None
        self.execution_successful = None
        self.execution_output = None
        self.execution_error = None
        
        # Call generate_code, which will then call verify_syntax
        self.generate_code()

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
                        self.dependencies.add(alias.name.split('.')[0]) # Add base module name
                elif isinstance(node, ast.ImportFrom):
                    if node.module: # Handles 'from . import X' or 'from ..X import Y'
                        self.dependencies.add(node.module.split('.')[0]) # Add base module name
            self.status = "dependencies_identified"
        except Exception as e:
            self.status = f"error_dependency_identification: {e}"
            print(f"Error identifying dependencies: {e}")

    def install_dependencies(self):
        """
        Simulates the installation of identified dependencies.

        In a real environment, this would use pip to install packages.
        Updates status based on the simulated installation process.
        """
        if not hasattr(self, 'dependencies') or not self.dependencies:
            self.status = "info_no_dependencies_to_install"
            self.dependencies_installed_successfully = True # Or None, depending on desired logic
            print("No dependencies identified to install.")
            return

        self.dependencies_installed_successfully = True # Assume success unless an error occurs
        self.installation_logs = []
        print("Attempting to install dependencies (simulation)...")

        for dep_name in self.dependencies:
            log_message = f"Attempting to install {dep_name}... (simulation)"
            print(log_message)
            self.installation_logs.append(log_message)
            # In a real environment, you would use:
            # try:
            #     subprocess.run(["pip", "install", dep_name], check=True, capture_output=True, text=True)
            #     self.installation_logs.append(f"Successfully installed {dep_name}")
            # except subprocess.CalledProcessError as e:
            #     self.dependencies_installed_successfully = False
            #     err_msg = f"Failed to install {dep_name}: {e.stderr}"
            #     print(err_msg)
            #     self.installation_logs.append(err_msg)
            #     self.status = f"error_installing_dependency_{dep_name}"
            #     # Optionally break or collect all errors
            #     break 
            # except FileNotFoundError:
            #      self.dependencies_installed_successfully = False
            #      err_msg = "Error: pip command not found. Cannot install dependencies."
            #      print(err_msg)
            #      self.installation_logs.append(err_msg)
            #      self.status = "error_pip_not_found"
            #      break

        if self.dependencies_installed_successfully:
            self.status = "dependencies_installed_simulated"
            print("All dependencies processed (simulation).")
        else:
            # This part of the status would be set within the commented-out error handling
            print("One or more dependencies failed to install (simulation).")


    def validate_code(self):
        """
        Validates the generated code.
        """
        # TODO: Implement code validation logic
        pass

    def manage_dependencies(self):
        """
        Manages dependencies for the generated code.
        """
        # TODO: Implement dependency management logic
        pass
