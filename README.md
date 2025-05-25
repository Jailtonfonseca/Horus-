# Horus Agent System

Horus is a multi-agent system designed for code generation, validation, and management. It utilizes Large Language Models (LLMs) through an abstracted interface, allowing for flexibility in choosing LLM providers (e.g., Groq, OpenAI). The system processes agent tasks asynchronously using Celery with Redis as a message broker, and executes generated code in a sandboxed Docker environment with live dependency installation.

## Core Components

-   **`app.py`**: A Flask web application providing a user interface for interacting with the Horus agent system. It handles prompt submission, initiates asynchronous tasks, and provides status updates.
-   **`main_agent.py`**: Orchestrates subordinate agents. Manages their creation, lifecycle, and tasks, including selecting the appropriate LLM client.
-   **`subordinate_agent.py`**: Responsible for a specific task, primarily focused on code generation using an LLM, syntax validation, dependency identification, Dockerized code execution with dependency installation, and iterative self-correction.
-   **`llm_interface.py`**: An abstract base class defining the contract for LLM interactions (e.g., text generation, listing models).
-   **`llm_groq.py`**: Concrete implementation of `LLMInterface` for the Groq API.
-   **`llm_openai.py`**: Concrete implementation of `LLMInterface` for the OpenAI API.
-   **`celery_config.py`**: Configuration file for Celery, specifying the message broker (Redis) and result backend.
-   **`Dockerfile`**: Defines the Docker image (`horus_agent_runner`) used as the sandboxed environment for code execution and dependency installation.
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
-   **Iterative Debugging / Self-Correction**:
    -   Agents attempt to fix their own generated code if syntax or runtime errors occur.
    -   Utilizes a feedback loop: errors from validation or execution are used to construct a new prompt, asking the LLM to correct the previous code.
    -   This process repeats up to a configurable number of attempts (`max_correction_attempts` in `SubordinateAgent`).
    -   The generation history, including all attempts, prompts, generated code, and errors, is tracked and can be displayed in the UI.
-   **Code Generation**: Subordinate agents generate code based on user prompts and selected LLM, potentially making multiple attempts to produce working code.
-   **Syntax Verification**: Uses `ast.parse()` to check the syntax of generated Python code during each correction attempt.
-   **Dependency Identification**: Parses `import` statements in generated code to identify Python package dependencies.
-   **Sandboxed Code Execution (Docker)**: 
    -   Executes generated Python code in an isolated Docker container using the `horus_agent_runner` image (built from the provided `Dockerfile`). This provides enhanced isolation from the main application and Celery worker environment.
    -   Captures `stdout`, `stderr`, and the exit code from the executed script.
    -   Includes a configurable timeout (`execution_timeout` in `SubordinateAgent`) to prevent runaway scripts.
    -   **Sandboxing Limitations**: The current Docker-based sandboxing using the `horus_agent_runner` image offers significantly improved isolation. However, users should be aware of the security implications outlined in the "Known Limitations and Future Work" section.
-   **Dependency Management (Live Installation in Docker)**: 
    -   Identified Python package dependencies (from `import` statements) are installed using `pip install --user --no-cache-dir <dependency>` directly within the Docker container for each execution run, just before the main generated script is executed.
    -   This ensures that the code runs with its specified dependencies in an isolated environment.
    -   Detailed installation logs (including `stdout`, `stderr`, and exit codes from `pip`) for each dependency are captured and stored. This information is accessible via the `generation_history` (as part of the execution attempt details) and is displayed in the web UI, providing transparency into the setup process.
    -   If any dependency fails to install, the main script execution is skipped, and the failure is reported along with the installation logs.
-   **Agent Reconstruction**: Allows agents to regenerate code based on new prompts, utilizing the same iterative debugging and Dockerized execution process.
-   **Web Interface**: User-friendly Flask UI for prompt input, LLM selection, and displaying real-time status, iterative generation history (including detailed dependency installation logs), and final results.
-   **Unit Tests**: Comprehensive tests for agents, LLM interfaces, the Flask application, and Celery task integration.
-   **Secure API Key Management**: API keys are managed via environment variables.

## System Architecture & Workflow

The Horus system is designed with a decoupled architecture to support various LLMs and asynchronous, sandboxed operations:

1.  **LLM Abstraction Layer**:
    -   `LLMInterface` defines a standard interface for interacting with any LLM.
    -   `GroqLLM` and `OpenAILLM` are concrete implementations for the Groq and OpenAI APIs, respectively. They handle the specifics of API calls and error handling for their particular service.

2.  **Agent Orchestration**:
    -   The `MainAgent` is responsible for creating `SubordinateAgent` instances.
    -   When creating a subordinate agent, `MainAgent` instantiates the appropriate LLM client (e.g., `GroqLLM`, `OpenAILLM`) based on user input (`llm_type`) from the web UI. This client is then passed to the `SubordinateAgent`.

3.  **Asynchronous Task Workflow with Dockerized Execution**:
    1.  A user submits a prompt, selects an LLM provider (Groq/OpenAI), and optionally specifies a model name via the web UI.
    2.  The Flask application (`app.py`) receives the request. Instead of processing directly, it triggers a Celery task (`process_agent_task`).
    3.  The Celery task is sent to a message broker (Redis).
    4.  A Celery worker picks up the task and executes `process_agent_task`. This task involves:
        -   Instantiating `MainAgent` (which loads API keys from environment variables).
        -   Creating a `SubordinateAgent` with the chosen LLM client.
        -   Invoking `SubordinateAgent.generate_code()`. This method encapsulates the iterative debugging loop:
            -   It first attempts to generate code using the selected LLM.
            -   If syntax or runtime errors occur (runtime errors are determined by executing the code within a Docker container), it constructs a "fix prompt" and re-queries the LLM.
            -   **Dependency Installation**: Before each code execution attempt within Docker, identified dependencies are installed using `pip install --user`. Logs are captured. If installation fails, this is treated as an error for the current attempt.
            -   **Code Execution**: The code (if dependencies installed correctly) is run inside a Docker container based on the `horus_agent_runner` image.
            -   This loop continues until the code is successful or `max_correction_attempts` is reached.
        -   The Celery task updates its overall state (e.g., `PROGRESS`). Detailed step-by-step progress of the iterative loop, including live dependency installation attempts (with logs) inside Docker, and script execution, is primarily tracked within the `SubordinateAgent`'s `generation_history` and `installation_logs`.
    5.  The web UI, meanwhile, polls a status endpoint (`/task_status/<task_id>`) in `app.py`.
    6.  This endpoint queries Celery (via Redis as the result backend) for the task's current status and any intermediate results (like `generation_history` which now includes `installation_logs`) or final output.
    7.  The UI dynamically updates to show the progress and, eventually, the final results or errors from the agent processing.

## Prerequisites

Before you begin, ensure you have the following installed:
-   **Python 3.10 or higher**
-   **pip** (Python package installer)
-   **Redis Server**: Used as the message broker and result backend for Celery.
    -   Installation guides: [Official Redis Documentation](https://redis.io/docs/getting-started/installation/)
-   **Docker Desktop (for macOS and Windows) or Docker Engine (for Linux)**: Essential for sandboxed code execution and dependency installation.
    -   Official Docker installation guide: [https://docs.docker.com/get-docker/](https://docs.docker.com/get-docker/)
    -   Ensure the Docker daemon is running and accessible by the user running the Celery workers (this often means the user needs to be in the `docker` group on Linux, or Docker Desktop needs to be running).

## Configuration

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

### Other Configuration
-   **Iterative Debugging**:
    -   `max_correction_attempts`: The maximum number of self-correction attempts an agent will make. Default is 3. This is set in `SubordinateAgent.__init__`.
    -   `execution_timeout`: The timeout in seconds for each code execution attempt within the sandbox. Default is 10.0 seconds. This is also set in `SubordinateAgent.__init__`.
    Currently, these are not exposed via the UI or environment variables but can be modified directly in the `SubordinateAgent` code if needed.
-   **Docker Image**: The default Docker image used for execution is `horus_agent_runner`. This can be changed via a keyword argument to `SubordinateAgent` if needed.

## Running the Application

To run the full application with asynchronous task processing and Dockerized code execution, you need to manage four main components: the Docker daemon, the Docker image, a Redis server, Celery worker(s), and the Flask application.

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
    Ensure Docker is running.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set API Keys**:
    Ensure your API keys (`GROQ_API_KEY`, `OPENAI_API_KEY` as needed) are set as environment variables as described in the "API Key Setup" section.

5.  **Build the Docker Image**:
    The `Dockerfile` in the project root defines the sandboxed execution environment. Build the Docker image using:
    ```bash
    docker build -t horus_agent_runner .
    ```
    This command builds an image named `horus_agent_runner`. This only needs to be done once initially or when the `Dockerfile` changes. Ensure the Docker daemon is running before this step.

6.  **Start Redis Server**:
    Once installed (see Prerequisites), start the Redis server. Typically:
    ```bash
    redis-server
    ```
    By default, Redis runs on `localhost:6379`. If your Redis configuration is different, update `celery_config.py`.

7.  **Start the Celery Worker**:
    Open a **new terminal window/tab** in the project's root directory (where `app.py` is located) and activate your virtual environment. Then, run:
    ```bash
    celery -A app.celery_app worker -l info
    ```
    -   `app.celery_app` points to the Celery application instance named `celery_app` within your `app.py` file.
    -   `-l info` sets the logging level to info.
    -   The worker must have access to the environment variables for API keys and needs to be able to connect to the Docker daemon.

8.  **Run the Flask Application**:
    Open **another new terminal window/tab**, activate your virtual environment, and run the Flask app:
    ```bash
    python app.py
    ```

9.  **Access the Application**:
    Open your web browser and navigate to `http://127.0.0.1:5000/`.

You should now have four main components active: the Docker daemon, the Redis server, the Celery worker, and the Flask app. You can submit prompts via the web UI, select an LLM, and observe asynchronous processing with code execution and dependency installation happening inside Docker containers.

## Running Tests

To run the unit tests:

```bash
python -m unittest discover tests
```

Ensure you are in the root directory of the project and your virtual environment is activated. Some tests for `MainAgent` mock environment variables for API keys. Tests for Docker-based execution (`tests/test_subordinate_agent.py`) mock the Docker SDK, so they can run without a live Docker daemon.

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

4.  **Load environment variables in `app.py`**:
    At the very beginning of `app.py` (before other project imports like `MainAgent`), add:
    ```python
    from dotenv import load_dotenv
    load_dotenv()
    ```
    The `MainAgent` (when instantiated by the Celery worker) will then be able to pick up these variables when it calls `os.getenv()`.

## Known Limitations and Future Work

-   **Sandboxing & Docker Integration**:
    -   **Docker Daemon Access**: The Celery worker process (which runs `SubordinateAgent`) needs access to the Docker daemon socket (e.g., `/var/run/docker.sock`). This is a common setup but has security implications: a process with access to the Docker socket effectively has root-equivalent privileges on the host system if it can start arbitrary containers. This risk should be managed carefully in production environments (e.g., by running Celery workers as a dedicated, less privileged user where possible, though Docker socket access often requires higher privileges, or by using technologies like rootless Docker if feasible for the use case).
    -   **Initial Image Pull/Build Time**: The first time the `horus_agent_runner` image is built (using `docker build -t horus_agent_runner .`), it will take some time. If the base Python image specified in the `Dockerfile` needs to be pulled, that will also add to the initial setup time. Subsequent builds are faster due to Docker's caching.
    -   **Disk Space**: Docker images and containers can consume significant disk space. Users should be aware of Docker's pruning commands (e.g., `docker system prune`) to manage unused resources.
    -   **Resource Configuration**: While basic memory (`256m`) and CPU share limits (`512`) are set for containers in `SubordinateAgent.execute_code`, these are general defaults. More advanced or dynamically configurable resource management per container might be needed for production use or diverse workloads.
    -   **Network Access from Container**: By default, Docker containers created by `docker.from_env().containers.run()` can access external networks. This is necessary for `pip install` to fetch dependencies. If generated code needs to be restricted from accessing the internet during its execution phase (after dependencies are installed), further Docker networking configurations (e.g., custom Docker network with no external access, or disconnecting the container from the network after pip install) would be required. This is a current limitation of the sandboxing.
-   **LLM Errors During Correction**: If the LLM itself fails to generate a response during a correction attempt (e.g., API error, rate limit), the current loop might not handle this as gracefully as it handles code errors. More sophisticated error handling for LLM failures within the iterative loop could be added.
-   **Prompt Engineering for Fixes**: The quality of the "fix prompts" (`_create_fix_prompt`) is crucial for effective self-correction. Further refinement of these prompts may improve the success rate of the debugging loop.
-   **Dependency Management Efficiency**:
    -   The current approach installs dependencies (`pip install --user --no-cache-dir`) into the running container for each execution that requires them. This ensures a clean environment for each run but is not efficient if the same dependencies are repeatedly used across many executions without changes to the base Docker image (`horus_agent_runner`).
    -   Future improvements could involve:
        -   Building custom Docker images with common or frequently used dependencies pre-installed to speed up execution.
        -   Implementing a more sophisticated caching mechanism for dependencies if the base image remains static.
        -   Allowing users to specify a custom Docker image that might already contain necessary dependencies.
-   **Configuration Management**: Parameters like `max_correction_attempts` and `execution_timeout` are currently hardcoded defaults in `SubordinateAgent`. Exposing these via environment variables, a configuration file, or through the UI would offer more flexibility.
-   **Real-time Progress Updates**: While Celery tasks update their state, the fine-grained progress of the iterative debugging loop within `SubordinateAgent` is not currently streamed to the frontend in real-time. This could be a future enhancement using WebSockets or more frequent polling with detailed status updates.

### Other TODOs (from code)
-   Expand `MainAgent` to accept a dictionary of API keys or a more structured configuration for multi-LLM management.
-   Enhance the Flask UI to dynamically list available models for the selected LLM provider.
-   Persist agent state and task history, potentially using a database.
-   Add more robust error handling and logging throughout the application.
-   Implement user authentication and authorization if the application were to be deployed in a multi-user environment.
```
