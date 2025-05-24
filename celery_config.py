# Celery Configuration File

# Broker URL: Specifies the connection URL for your message broker (e.g., Redis).
# Celery uses this to send and receive messages for tasks.
# Format for Redis: redis://hostname:port/database_number
# Example: 'redis://localhost:6379/0' (connects to Redis on localhost, port 6379, database 0)
broker_url = 'redis://localhost:6379/0'

# Result Backend: Specifies the connection URL for storing the results (state and return values) of your tasks.
# This is also often set to Redis, but can be other backends like RabbitMQ, a database, etc.
# Format for Redis: redis://hostname:port/database_number
# Example: 'redis://localhost:6379/0'
result_backend = 'redis://localhost:6379/0'

# Task Ignore Result: If set to True, Celery will not store the results of tasks.
# Set to False if you need to retrieve the return value or status of a task.
# For this application, we want to store and retrieve results.
task_ignore_result = False

# Task Track Started: If True, the task will report its state as 'STARTED' when the task is executed by a worker.
# task_track_started = True

# Other potential configurations:
# task_serializer = 'json'
# result_serializer = 'json'
# accept_content = ['json']
# timezone = 'Europe/Oslo'
# enable_utc = True
# worker_concurrency = 4 # Example: Set number of worker processes/threads
# task_acks_late = True # Tasks acknowledge after completion/failure, not just before execution
# worker_prefetch_multiplier = 1 # Can help with long-running tasks by preventing workers from prefetching too many tasks.
