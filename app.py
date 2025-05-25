from flask import Flask, render_template, request, jsonify, url_for # Added jsonify, url_for
from celery import Celery
from celery.result import AsyncResult # Added AsyncResult
from main_agent import MainAgent

app = Flask(__name__)

# Configure Celery from celery_config.py
app.config.from_object('celery_config')

# Helper to make Celery work with Flask context
def make_celery(flask_app):
    celery_instance = Celery(
        flask_app.import_name,
        broker=flask_app.config['broker_url'], # Use broker_url from config
        backend=flask_app.config['result_backend'] # Use result_backend from config
    )
    celery_instance.conf.update(flask_app.config)

    class ContextTask(celery_instance.Task):
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

    celery_instance.Task = ContextTask
    return celery_instance

celery_app = make_celery(app)

# The global main_agent_instance is no longer needed here for task processing,
# as tasks will create their own instances. It might be used for other non-task routes if any.
# For this setup, we can comment it out or remove if no other routes use it.
# main_agent_instance = MainAgent() 


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', message="Enter a prompt to create an agent.")


# Celery Task Definition (moved here as per instruction for app.celery_app decorator)
@celery_app.task(bind=True)
def process_agent_task(self, prompt: str, llm_type: str, model_name: str = None):
    """
    Celery task to process agent logic asynchronously.
    """
    try:
        # Instantiate MainAgent INSIDE the task.
        # MainAgent retrieves API keys from environment variables.
        task_main_agent = MainAgent()

        self.update_state(state='PROGRESS', meta={'status': 'Creating subordinate agent...'})
        sub_agent = task_main_agent.create_subordinate_agent(
            prompt=prompt,
            llm_type=llm_type,
            model_name=model_name
            # If max_correction_attempts needs to be configurable, pass it here
        )

        self.update_state(state='PROGRESS', meta={'status': 'Agent processing started (iterative debugging active)...'})
        
        # The generate_code method now encapsulates the iterative debugging loop.
        # The SubordinateAgent's status will be updated internally during this call.
        sub_agent.generate_code() 
        
        # After the loop, sub_agent.status and other attributes reflect the final state.
        # No need for separate calls to execute_code or install_dependencies here,
        # as they are handled within the SubordinateAgent's iterative loop if successful.

        agent_data = {
            'id': getattr(sub_agent, 'id', 'N/A'),
            'prompt': getattr(sub_agent, 'prompt', ''),
            'generated_code': getattr(sub_agent, 'generated_code', ''), # Final generated code
            'status': getattr(sub_agent, 'status', 'N/A'), # Final status from SubordinateAgent
            'is_syntax_valid': getattr(sub_agent, 'is_syntax_valid', None),
            'syntax_error_message': getattr(sub_agent, 'syntax_error_message', None),
            'execution_successful': getattr(sub_agent, 'execution_successful', None),
            'execution_output': getattr(sub_agent, 'execution_output', None),
            'execution_error': getattr(sub_agent, 'execution_error', None),
            'dependencies': list(getattr(sub_agent, 'dependencies', [])),
            'installation_logs': getattr(sub_agent, 'installation_logs', []),
            'generation_history': getattr(sub_agent, 'generation_history', []), 
            'correction_attempts': getattr(sub_agent, 'correction_attempts', 0),
            'max_correction_attempts': getattr(sub_agent, 'max_correction_attempts', 3) # Added
        }
        
        # Determine overall task success based on SubordinateAgent's final status
        # This is a simplified check; more robust status parsing from sub_agent.status might be needed
        # if specific failure types from the loop need to be distinguished here.
        final_message = f"Processing finished. Agent status: {agent_data['status']}"
        if "success" in agent_data['status'].lower():
             return {'status': 'SUCCESS', 'result': agent_data, 'current_status_message': final_message}
        else:
            # The 'error' field here should ideally be a summary or the last critical error.
            # The detailed errors are in generation_history.
            last_error_entry = next((item for item in reversed(agent_data['generation_history']) if item.get('error_message')), None)
            error_summary = last_error_entry['error_message'] if last_error_entry else 'Agent processing failed, see generation history.'
            return {'status': 'FAILURE', 'error': error_summary, 'result': agent_data, 'current_status_message': final_message}

    except ValueError as e: # From MainAgent if API key missing etc.
        return {'status': 'FAILURE', 'error': str(e), 'current_status_message': 'Failed due to configuration error.', 'result': None}
    except Exception as e:
        # Attempt to gather some data even if an unexpected error occurs, if sub_agent was initialized
        agent_data_on_failure = {}
        if 'sub_agent' in locals() and sub_agent:
            agent_data_on_failure = {
                'id': getattr(sub_agent, 'id', 'N/A'),
                'prompt': getattr(sub_agent, 'prompt', ''),
                'status': getattr(sub_agent, 'status', f'unexpected_error_in_task: {str(e)}'),
                'generation_history': getattr(sub_agent, 'generation_history', []),
                'correction_attempts': getattr(sub_agent, 'correction_attempts', 0)
            }
        # import logging; logging.exception("Celery task unexpected error") # Good practice
        return {'status': 'FAILURE', 'error': f'An unexpected error occurred: {str(e)}', 'result': agent_data_on_failure, 'current_status_message': 'Failed due to an unexpected task error.'}


@app.route('/create_agent', methods=['POST'])
def create_agent_route():
    prompt = request.form.get('prompt')
    llm_type = request.form.get('llm_type', 'groq') 
    model_name = request.form.get('model_name', None) 

    if not prompt:
        return jsonify({'error': 'Prompt cannot be empty'}), 400

    task = process_agent_task.apply_async(args=[prompt, llm_type, model_name])
    
    return jsonify({'task_id': task.id, 'status_url': url_for('task_status_route', task_id=task.id, _external=True)})


@app.route('/task_status/<task_id>', methods=['GET'])
def task_status_route(task_id):
    task_result = AsyncResult(task_id, app=celery_app)
    response_data = {
        'task_id': task_id,
        'state': task_result.state,
    }
    current_status_msg = 'Processing...' # Default message

    if task_result.info and isinstance(task_result.info, dict):
        current_status_msg = task_result.info.get('status', current_status_msg)
        if task_result.info.get('error'): # If task explicitly returned an error in its meta
             response_data['error'] = task_result.info.get('error')

    response_data['current_status_message'] = current_status_msg

    if task_result.state == 'PENDING':
        response_data['status_message'] = 'Task is pending.'
    elif task_result.state == 'PROGRESS':
        response_data['status_message'] = 'Task in progress.'
        # task_result.info should contain the 'meta' dictionary from update_state
        if task_result.info and isinstance(task_result.info, dict):
             response_data['meta'] = task_result.info
    elif task_result.state == 'SUCCESS':
        response_data['status_message'] = 'Task completed successfully.'
        if task_result.result and isinstance(task_result.result, dict):
            response_data['result'] = task_result.result.get('result')
            response_data['current_status_message'] = task_result.result.get('current_status_message', 'Completed')
    elif task_result.state == 'FAILURE':
        response_data['status_message'] = 'Task failed.'
        if task_result.result and isinstance(task_result.result, dict): # Error returned by our task structure
            response_data['error'] = task_result.result.get('error', 'Unknown error')
            response_data['current_status_message'] = task_result.result.get('current_status_message', 'Failed')
        elif isinstance(task_result.info, Exception): # Unhandled exception in task
            response_data['error'] = str(task_result.info)
            response_data['current_status_message'] = 'Failed with unhandled exception.'
        else: # Other failure types
            response_data['error'] = 'Unknown failure type.'
            response_data['current_status_message'] = 'Failed.'
    else:
        response_data['status_message'] = f'Task state is {task_result.state}.' # More generic
    
    return jsonify(response_data)


if __name__ == '__main__':
    # For local development with Celery, you'd typically run:
    # 1. Redis server (e.g., `redis-server`)
    # 2. Celery worker (e.g., `celery -A app.celery_app worker -l info`)
    # 3. Flask app (e.g., `python app.py`)
    app.run(debug=True)
