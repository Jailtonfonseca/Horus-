from flask import Flask, render_template, request
from main_agent import MainAgent
# SubordinateAgent is not directly used in app.py but MainAgent uses it.

app = Flask(__name__)

# IMPORTANT: Configure your Groq API key securely, e.g., via environment variables.
# Do not commit your actual API key to version control.
GROQ_API_KEY = "YOUR_GROQ_API_KEY" # Replace with your actual key for testing if you have one, or leave as placeholder
main_agent_instance = MainAgent(groq_api_key=GROQ_API_KEY)

@app.route('/', methods=['GET'])
def index():
    # Later, you might want to pass a list of existing agents
    return render_template('index.html', message="Enter a prompt to create an agent.")

@app.route('/create_agent', methods=['POST'])
def create_agent_route():
    prompt = request.form.get('prompt')
    if not prompt:
        return render_template('index.html', message="Prompt cannot be empty.", agent_status=None)

    # Create a subordinate agent using the global main_agent_instance
    sub_agent = main_agent_instance.create_subordinate_agent(prompt=prompt)
    
    # Trigger code generation (and syntax check + dependency identification)
    sub_agent.generate_code() 

    # Optionally, attempt to execute the code if syntax is valid
    if getattr(sub_agent, 'is_syntax_valid', False):
       sub_agent.execute_code()

    # Optionally, attempt to "install" dependencies if identified
    if getattr(sub_agent, 'is_syntax_valid', False) and getattr(sub_agent, 'dependencies', None):
        sub_agent.install_dependencies()
    
    # Prepare data for the template
    # Ensure dependencies is a list for Jinja, and provide defaults for all fields
    agent_status_data = {
        'id': getattr(sub_agent, 'id', 'N/A'),
        'prompt': getattr(sub_agent, 'prompt', ''),
        'generated_code': getattr(sub_agent, 'generated_code', ''),
        'status': getattr(sub_agent, 'status', 'N/A'),
        'is_syntax_valid': getattr(sub_agent, 'is_syntax_valid', None),
        'syntax_error_message': getattr(sub_agent, 'syntax_error_message', None),
        'execution_successful': getattr(sub_agent, 'execution_successful', None),
        'execution_output': getattr(sub_agent, 'execution_output', None),
        'execution_error': getattr(sub_agent, 'execution_error', None),
        'dependencies': list(getattr(sub_agent, 'dependencies', [])),
        'installation_logs': getattr(sub_agent, 'installation_logs', [])
    }
    
    return render_template('index.html', agent_status=agent_status_data, message="Agent processing complete.")

if __name__ == '__main__':
    app.run(debug=True)
