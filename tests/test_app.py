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

class TestWebApp(unittest.TestCase):
    def setUp(self):
        """Set up test client and app configuration for each test."""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for testing forms if applicable
        self.app = app.test_client()

    def test_index_route_get(self):
        """Test the index route for a GET request."""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Horus Agent Interface", response.data)
        self.assertIn(b"Enter a prompt to create an agent.", response.data)

    @patch('app.main_agent_instance') # Patch the global instance in app.py
    def test_create_agent_route_post_valid_prompt(self, MockMainAgentInstance):
        """Test the /create_agent route with a valid prompt."""
        # Configure the mock MainAgent's create_subordinate_agent method
        mock_sub_agent = MagicMock()
        mock_sub_agent.id = 1
        mock_sub_agent.prompt = "test prompt for app"
        mock_sub_agent.generated_code = "print('mocked code by app test')"
        mock_sub_agent.status = "mock_status_complete_for_app"
        mock_sub_agent.is_syntax_valid = True
        mock_sub_agent.syntax_error_message = None
        mock_sub_agent.execution_successful = True
        mock_sub_agent.execution_output = "Mocked execution output."
        mock_sub_agent.execution_error = ""
        mock_sub_agent.dependencies = {"mock_dep1", "mock_dep2"}
        mock_sub_agent.installation_logs = ["Installed mock_dep1 (simulated)"]
        
        MockMainAgentInstance.create_subordinate_agent.return_value = mock_sub_agent

        # Simulate POST request to /create_agent
        response = self.app.post('/create_agent', data={'prompt': 'test prompt for app'})
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Agent processing complete", response.data)
        self.assertIn(b"mocked code by app test", response.data)
        self.assertIn(b"mock_status_complete_for_app", response.data)
        self.assertIn(b"Mocked execution output.", response.data)
        self.assertIn(b"mock_dep1", response.data) # Check if dependencies are displayed

        # Verify that MainAgent's method was called correctly
        MockMainAgentInstance.create_subordinate_agent.assert_called_once_with(prompt='test prompt for app')
        
        # Verify methods on the subordinate agent mock were called
        mock_sub_agent.generate_code.assert_called_once()
        # Given is_syntax_valid = True, execute_code should be called
        mock_sub_agent.execute_code.assert_called_once()
        # Given dependencies were identified, install_dependencies should be called
        mock_sub_agent.install_dependencies.assert_called_once()

    def test_create_agent_route_post_empty_prompt(self):
        """Test the /create_agent route with an empty prompt."""
        response = self.app.post('/create_agent', data={'prompt': ''})
        self.assertEqual(response.status_code, 200) # The route returns 200 but shows an error message
        self.assertIn(b"Prompt cannot be empty", response.data)
        self.assertNotIn(b"Agent processing complete", response.data)


if __name__ == '__main__':
    # This allows running the tests directly from this file
    # Make sure the app and its dependencies can be imported
    if '..' not in sys.path: # Add parent directory to path if script is run directly
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from app import app # Re-import for direct run context
    unittest.main()
