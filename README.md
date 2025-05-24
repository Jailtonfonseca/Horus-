# Horus Agent System

Horus is a multi-agent system designed for code generation, validation, and management. It utilizes Large Language Models (LLMs) through an abstracted interface, allowing for flexibility in choosing LLM providers (e.g., Groq, OpenAI). The system processes agent tasks asynchronously using Celery with Redis as a message broker, ensuring a responsive user experience.

## Core Components

-   **`app.py`**: A Flask web application providing a user interface for interacting with the Horus agent system. It handles prompt submission, initiates asynchronous tasks, and provides status updates.
-   **`main_agent.py`**: Orchestrates subordinate agents. Manages their creation, lifecycle, and tasks, including selecting the appropriate LLM client.
-   **`subordinate_agent.py`**: Responsible for a specific task, primarily focused on code generation using an LLM, syntax validation, dependency identification, code execution, and (simulated) dependency installation.
-   **`llm_interface.py`**: An abstract base class defining the contract for LLM interactions (e.g., text generation, listing models).
-   **`llm_groq.py`**: Concrete implementation of `LLMInterface` for the Groq API.
-   **`llm_openai.py`**: Concrete implementation of `LLMInterface` for the OpenAI API.
-   **`celery_config.py`**: Configuration file for Celery, specifying the message broker (Redis) and result backend.
-   **`templates/index.html`**: The HTML template for the web interface, including JavaScript for asynchronous task status polling and result display.
-   **`tests/`**: Directory containing unit tests for various components of the system.

## Features

-   **Modular Agent Architecture**: Main agent manages multiple subordinate agents for focused tasks.
-   **Multi-LLM Support**:
    -   Utilizes an LLM abstraction layer (`LLMInterface`) for easy integration of different LLM providers.
    -   Currently supports Groq and OpenAI.
-   **Asynchronous Task Processing**:
    -   Uses Celery with Redis to handle agent tasks asynchronously, preventing UI blocking during LLM interactions and code processing.
    -   Web interface polls for task status and displays results dynamically.
-   **Code Generation**: Subordinate agents generate code based on user prompts and selected LLM.
-   **Syntax Verification**: Uses `ast.parse()` to check the syntax of generated Python code.
-   **Dependency Identification**: Parses import statements in generated code to identify dependencies.
-   **Code Execution**: Executes generated Python code in a controlled environment, capturing stdout and stderr.
-   **Dependency Management (Simulated)**: Simulates the installation of identified dependencies.
-   **Agent Reconstruction**: Allows agents to regenerate code based on new prompts (via `MainAgent.reconstruct_subordinate_agent`).
-   **Web Interface**: User-friendly Flask UI for prompt input, LLM selection, and displaying real-time status and final results.
-   **Unit Tests**: Comprehensive tests for agents, LLM interfaces, the Flask application, and Celery task integration.
-   **Secure API Key Management**: API keys are managed via environment variables.

## System Architecture & Workflow

The Horus system is designed with a decoupled architecture to support various LLMs and asynchronous operations:

1.  **LLM Abstraction Layer**:
    -   `LLMInterface` defines a standard interface for interacting with any LLM.
    -   `GroqLLM` and `OpenAILLM` are concrete implementations for the Groq and OpenAI APIs, respectively. They handle the specifics of API calls and error handling for their particular service.

2.  **Agent Orchestration**:
    -   The `MainAgent` is responsible for creating `SubordinateAgent` instances.
    -   When creating a subordinate agent, `MainAgent` instantiates the appropriate LLM client (e.g., `GroqLLM`, `OpenAILLM`) based on user input (`llm_type`) from the web UI. This client is then passed to the `SubordinateAgent`.

3.  **Asynchronous Task Workflow**:
    1.  A user submits a prompt, selects an LLM provider (Groq/OpenAI), and optionally specifies a model name via the web UI.
    2.  The Flask application (`app.py`) receives the request. Instead of processing directly, it triggers a Celery task (`process_agent_task`).
    3.  The Celery task is sent to a message broker (Redis).
    4.  A Celery worker picks up the task and executes `process_agent_task`. This task involves:
        -   Instantiating `MainAgent` (which loads API keys from environment variables).
        -   Creating a `SubordinateAgent` with the chosen LLM client.
        -   Invoking methods on the `SubordinateAgent` for code generation (using the selected LLM), syntax validation, execution, etc.
        -   The task updates its state periodically using `self.update_state` for progress tracking.
    5.  The web UI, meanwhile, polls a status endpoint (`/task_status/<task_id>`) in `app.py`.
    6.  This endpoint queries Celery (via Redis as the result backend) for the task's current status and any intermediate results or final output.
    7.  The UI dynamically updates to show the progress and, eventually, the final results or errors from the agent processing.

## Configuration

The primary configuration for the application involves setting up API keys.

### API Key Setup

To use the LLM functionalities, you need to configure API keys for the services you intend to use. These keys **must** be set as environment variables.

-   **For Groq**:
    Set the `GROQ_API_KEY` environment variable:
    ```bash
    export GROQ_API_KEY="your_groq_api_key_here"
    ```

-   **For OpenAI**:
    Set the `OPENAI_API_KEY` environment variable:
    ```bash
    export OPENAI_API_KEY="your_openai_api_key_here"
    ```

**Important**:
-   Replace `"your_..._api_key_here"` with your actual API key.
-   **Never commit your API keys directly into version control.** If you are using a `.env` file for local development (see "Local Development with .env" below), ensure `.env` is listed in your `.gitignore` file.
-   You only need to set the key for the service(s) you plan to use. The application will raise an error if you try to use an LLM service for which the key is not set (e.g., selecting "OpenAI" in the UI if `OPENAI_API_KEY` is not set).

The Celery broker and result backend URLs are configured in `celery_config.py` and default to `redis://localhost:6379/0`. Modify this file if your Redis instance runs elsewhere.

## Running the Application

To run the full application with asynchronous task processing, you need to manage three main components: a Redis server, Celery worker(s), and the Flask application.

1.  **Clone the Repository**:
    ```bash
    git clone <repository_url>
    cd horus-agent-system 
    ```
    (Replace `<repository_url>` with the actual URL of your repository).

2.  **Create a Virtual Environment** (recommended):
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set API Keys**:
    Ensure your API keys (`GROQ_API_KEY`, `OPENAI_API_KEY` as needed) are set as environment variables as described in the "API Key Setup" section.

5.  **Install and Start Redis Server**:
    Redis is used as the message broker and result backend.
    -   **Installation**:
        -   On macOS (using Homebrew): `brew install redis`
        -   On Ubuntu/Debian: `sudo apt-get update && sudo apt-get install redis-server`
        -   For other systems or Docker, refer to the [official Redis documentation](https://redis.io/docs/getting-started/installation/).
    -   **Start Server**:
        Once installed, start the Redis server. Typically:
        ```bash
        redis-server
        ```
        By default, Redis runs on `localhost:6379`. If your Redis configuration is different, update `celery_config.py`.

6.  **Start the Celery Worker**:
    Open a **new terminal window/tab** in the project's root directory and activate your virtual environment. Then, run:
    ```bash
    celery -A app.celery_app worker -l info
    ```
    -   `app.celery_app` points to the Celery application instance named `celery_app` within your `app.py` file.
    -   `-l info` sets the logging level to info.
    -   The worker must have access to the environment variables for API keys.

7.  **Run the Flask Application**:
    Open **another new terminal window/tab**, activate your virtual environment, and run the Flask app:
    ```bash
    python app.py
    ```

8.  **Access the Application**:
    Open your web browser and navigate to `http://127.0.0.1:5000/`.

You should now have three main processes running: Redis, the Celery worker, and the Flask app. You can submit prompts via the web UI, select an LLM, and observe asynchronous processing.

## Running Tests

To run the unit tests:

```bash
python -m unittest discover tests
```

Ensure you are in the root directory of the project and your virtual environment is activated. Some tests for `MainAgent` mock environment variables for API keys, so they can run without keys being globally set. However, for full end-to-end testing or if you modify tests, ensure your environment is configured appropriately.

## Local Development with `.env` (Optional)

For easier local development, you can use a `.env` file to manage your API keys. This is not a requirement for the application to run if environment variables are set globally, but it's a common practice.

1.  **Install `python-dotenv`**:
    If not already in `requirements.txt`, add it:
    ```bash
    pip install python-dotenv
    pip freeze > requirements.txt 
    ```

2.  **Create a `.env` file** in the root of the project:
    ```
    GROQ_API_KEY="your_groq_api_key_here"
    OPENAI_API_KEY="your_openai_api_key_here"
    ```

3.  **Add `.env` to your `.gitignore` file**:
    Create or edit `.gitignore` in your project root and add the line:
    ```
    .env
    ```

4.  **Load environment variables in `app.py`** (and potentially `main_agent.py` if run standalone, though not necessary if `MainAgent` is only used by `app.py` which loads dotenv):
    At the very beginning of `app.py` (before other project imports like `MainAgent`), add:
    ```python
    from dotenv import load_dotenv
    load_dotenv()
    ```
    The `MainAgent` will then be able to pick up these variables when it calls `os.getenv()`. Celery workers will also pick up these variables if `load_dotenv()` is called when the Celery app is defined or imported.

## Future Enhancements (TODOs from code)

-   Expand `MainAgent` to accept a dictionary of API keys or a more structured configuration for even more flexible multi-LLM management.
-   Implement a more sophisticated execution environment/sandbox for `SubordinateAgent.execute_code` for better security and isolation.
-   Implement actual (non-simulated) dependency installation in `SubordinateAgent.install_dependencies` using `subprocess`.
-   Enhance the Flask UI to dynamically list available models for the selected LLM provider.
-   Persist agent state and task history, potentially using a database.
-   Add more robust error handling, user feedback, and comprehensive logging throughout the application.
-   Implement user authentication and authorization if the application were to be deployed in a multi-user environment.
```
