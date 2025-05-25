import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure the main project directory is in the Python path
# This might be needed if running tests from a different directory or with certain test runners
# if '..' not in sys.path:
#     sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app # Import the Flask app instance
# from main_agent import MainAgent # Not strictly needed if we patch main_agent_instance
# from subordinate_agent import SubordinateAgent # Not strictly needed for these tests

# Import app for context in AsyncResult mock checks
from app import app, celery_app 

class TestWebApp(unittest.TestCase):
    def setUp(self):
        """Set up test client and app configuration for each test."""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for testing forms if applicable
        # Ensure Celery is in eager mode for synchronous testing of task logic if needed elsewhere,
        # but for route testing, we mock apply_async and AsyncResult.
        # celery_app.conf.update(task_always_eager=True)
        self.app = app.test_client()

    def test_index_route_get(self):
        """Test the index route for a GET request."""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Horus Agent Interface", response.data)
        # The message is now set by JS, so we might not find the old one.
        # self.assertIn(b"Enter a prompt to create an agent.", response.data) 
        self.assertIn(b"Create New Agent", response.data) # Check for form presence

    # Test /create_agent endpoint
    @patch('app.process_agent_task') # Patch the Celery task object in app.py
    def test_create_agent_route_calls_celery_task(self, mock_process_agent_task):
        # Configure the mock task's apply_async method
        mock_task_instance = MagicMock()
        mock_task_instance.id = "test_task_123"
        mock_process_agent_task.apply_async.return_value = mock_task_instance

        response = self.app.post('/create_agent', data={
            'prompt': 'test celery prompt',
            'llm_type': 'groq',
            'model_name': 'mixtral-test'
        })
        self.assertEqual(response.status_code, 200)
        json_response = response.get_json()
        self.assertEqual(json_response['task_id'], "test_task_123")
        self.assertIn('/task_status/test_task_123', json_response['status_url'])
        
        mock_process_agent_task.apply_async.assert_called_once_with(
            args=['test celery prompt', 'groq', 'mixtral-test']
        )

    def test_create_agent_route_post_empty_prompt(self):
        """Test the /create_agent route with an empty prompt."""
        response = self.app.post('/create_agent', data={'prompt': ''})
        self.assertEqual(response.status_code, 400) 
        json_response = response.get_json()
        self.assertIn("Prompt cannot be empty", json_response['error'])
        
    # Tests for /task_status/<task_id> endpoint
    @patch('app.AsyncResult') # Patch AsyncResult where it's used in app.py
    def test_task_status_route_pending(self, MockAsyncResult):
        mock_task = MockAsyncResult.return_value
        mock_task.id = "test_task_pending"
        mock_task.state = "PENDING"
        mock_task.info = None # Or some initial info if set by Celery

        response = self.app.get('/task_status/test_task_pending')
        self.assertEqual(response.status_code, 200)
        json_response = response.get_json()
        self.assertEqual(json_response['state'], "PENDING")
        self.assertEqual(json_response['status_message'], "Task is pending.")
        MockAsyncResult.assert_called_once_with("test_task_pending", app=celery_app)


    @patch('app.AsyncResult')
    def test_task_status_route_progress(self, MockAsyncResult):
        mock_task = MockAsyncResult.return_value
        mock_task.id = "test_task_prog"
        mock_task.state = "PROGRESS"
        # This is what update_state(meta=...) sets in task_result.info
        mock_task.info = {'status': 'Generating code...'} 

        response = self.app.get('/task_status/test_task_prog')
        self.assertEqual(response.status_code, 200)
        json_response = response.get_json()
        self.assertEqual(json_response['state'], "PROGRESS")
        self.assertEqual(json_response['status_message'], "Task in progress.")
        self.assertEqual(json_response['current_status_message'], 'Generating code...')
        self.assertEqual(json_response['meta']['status'], 'Generating code...')
        MockAsyncResult.assert_called_once_with("test_task_prog", app=celery_app)

    @patch('app.AsyncResult')
    def test_task_status_route_success(self, MockAsyncResult):
        mock_task = MockAsyncResult.return_value
        mock_task.id = "test_task_success"
        mock_task.state = "SUCCESS"
        # This structure matches what our process_agent_task returns
        mock_task.result = { 
            'status': 'SUCCESS', 
            'result': {
                'id': 1, 
                'prompt': 'done', 
                'status': 'completed_successfully',
                'generation_history': [{'attempt': 1, 'status': 'success_on_attempt_1', 'error_type': None}],
                'correction_attempts': 1,
                'max_correction_attempts': 3 
            },
            'current_status_message': 'All done!'
        }

        response = self.app.get('/task_status/test_task_success')
        self.assertEqual(response.status_code, 200)
        json_response = response.get_json()
        self.assertEqual(json_response['state'], "SUCCESS")
        self.assertEqual(json_response['status_message'], "Task completed successfully.")
        self.assertEqual(json_response['result']['prompt'], 'done')
        self.assertEqual(json_response['current_status_message'], 'All done!')
        MockAsyncResult.assert_called_once_with("test_task_success", app=celery_app)
    
    @patch('app.AsyncResult')
    def test_task_status_route_failure_custom_error(self, MockAsyncResult):
        mock_task = MockAsyncResult.return_value
        mock_task.id = "test_task_fail_custom"
        mock_task.state = "FAILURE"
        # This structure matches what our process_agent_task returns on handled failure (e.g. max attempts)
        mock_task.result = {
            'status': 'FAILURE', 
            'error': 'Agent processing failed, see generation history.',
            'result': { # This nested 'result' now contains agent_data
                'id': 1, 
                'prompt': 'failed prompt', 
                'status': 'failed_syntax_after_3_attempts',
                'generation_history': [{'attempt': 1, 'status': 'syntax_error', 'error_type': 'Syntax'}],
                'correction_attempts': 3,
                'max_correction_attempts': 3 
            },
            'current_status_message': 'Processing failed after multiple attempts.'
        }
        # Celery might put the task's return value (the dict above) in .info for FAILURE states too,
        # or sometimes directly in .result. Our app.py code checks task_result.result first.
        mock_task.info = mock_task.result 

        response = self.app.get('/task_status/test_task_fail_custom')
        self.assertEqual(response.status_code, 200)
        json_response = response.get_json()
        self.assertEqual(json_response['state'], "FAILURE")
        self.assertEqual(json_response['status_message'], "Task failed.")
        self.assertEqual(json_response['error'], 'Agent processing failed, see generation history.')
        self.assertIsNotNone(json_response['result']) # Check that the nested agent_data is present
        self.assertEqual(json_response['result']['status'], 'failed_syntax_after_3_attempts')
        self.assertEqual(json_response['result']['correction_attempts'], 3)
        self.assertTrue(len(json_response['result']['generation_history']) > 0)
        self.assertEqual(json_response['current_status_message'], 'Processing failed after multiple attempts.')
        MockAsyncResult.assert_called_once_with("test_task_fail_custom", app=celery_app)

    @patch('app.AsyncResult')
    def test_task_status_route_failure_config_error(self, MockAsyncResult): # For ValueError case
        mock_task = MockAsyncResult.return_value
        mock_task.id = "test_task_fail_config"
        mock_task.state = "FAILURE"
        mock_task.result = { # Matches the return for ValueError in process_agent_task
            'status': 'FAILURE',
            'error': 'Groq API key not provided...',
            'result': None, # Explicitly None for this error type
            'current_status_message': 'Failed due to configuration error.'
        }
        mock_task.info = mock_task.result

        response = self.app.get('/task_status/test_task_fail_config')
        self.assertEqual(response.status_code, 200)
        json_response = response.get_json()
        self.assertEqual(json_response['state'], "FAILURE")
        self.assertEqual(json_response['error'], 'Groq API key not provided...')
        self.assertNotIn('result', json_response) # or self.assertIsNone(json_response.get('result'))
        MockAsyncResult.assert_called_once_with("test_task_fail_config", app=celery_app)


    @patch('app.AsyncResult')
    def test_task_status_route_failure_unhandled_exception(self, MockAsyncResult):
        mock_task = MockAsyncResult.return_value
        mock_task.id = "test_task_fail_unhandled"
        mock_task.state = "FAILURE"
        # Celery stores the actual exception instance in .info for unhandled exceptions
        mock_task.info = ValueError("Something went very wrong") 
        mock_task.result = None # No custom result structure in this case

        response = self.app.get('/task_status/test_task_fail_unhandled')
        self.assertEqual(response.status_code, 200)
        json_response = response.get_json()
        self.assertEqual(json_response['state'], "FAILURE")
        self.assertEqual(json_response['status_message'], "Task failed.")
        self.assertEqual(json_response['error'], "ValueError('Something went very wrong')") # str(exception)
        self.assertEqual(json_response['current_status_message'], 'Failed with unhandled exception.')
        MockAsyncResult.assert_called_once_with("test_task_fail_unhandled", app=celery_app)


if __name__ == '__main__':
    # This allows running the tests directly from this file
    # Make sure the app and its dependencies can be imported
    if '..' not in sys.path: # Add parent directory to path if script is run directly
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from app import app # Re-import for direct run context
    unittest.main()
