import unittest
from unittest.mock import MagicMock, patch, call
import openai # For error types

# Ensure the main project directory is in the Python path if running directly
import sys
import os
# if '..' not in sys.path:
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm_openai import OpenAILLM # The class we are testing
from llm_interface import LLMInterface # For spec if needed

class TestOpenAILLM(unittest.TestCase):
    def setUp(self):
        self.api_key = "fake_openai_api_key"
        self.default_model = "gpt-3.5-turbo"

    @patch('openai.OpenAI') # Patch where OpenAI client is instantiated
    def test_initialization_success(self, MockOpenAIClient):
        mock_client_instance = MockOpenAIClient.return_value
        llm = OpenAILLM(api_key=self.api_key, model_name="gpt-4-custom")
        
        MockOpenAIClient.assert_called_once_with(api_key=self.api_key)
        self.assertEqual(llm.api_key, self.api_key)
        self.assertEqual(llm.default_model_name, "gpt-4-custom")
        self.assertIs(llm.client, mock_client_instance)

    @patch('openai.OpenAI')
    def test_initialization_default_model(self, MockOpenAIClient):
        OpenAILLM(api_key=self.api_key) # No model_name provided
        self.assertEqual(OpenAILLM.DEFAULT_MODEL, "gpt-3.5-turbo") # Check class attribute if needed
        # The super().__init__ will set self.default_model_name to the passed model_name or the class's DEFAULT_MODEL
        # No, this is wrong. The instance will have its default_model_name set.
        llm = OpenAILLM(api_key=self.api_key)
        self.assertEqual(llm.default_model_name, OpenAILLM.DEFAULT_MODEL)


    @patch('openai.OpenAI')
    def test_initialization_client_error(self, MockOpenAIClient):
        MockOpenAIClient.side_effect = Exception("Client init failed")
        with self.assertRaisesRegex(ConnectionError, "Failed to initialize OpenAI client: Client init failed"):
            OpenAILLM(api_key=self.api_key)

    @patch('openai.OpenAI')
    def test_generate_text_success_default_model(self, MockOpenAIClient):
        mock_client_instance = MockOpenAIClient.return_value
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated text"
        mock_client_instance.chat.completions.create.return_value = mock_response
        
        llm = OpenAILLM(api_key=self.api_key) # Uses default model
        result = llm.generate_text("Test prompt")

        self.assertEqual(result, "Generated text")
        mock_client_instance.chat.completions.create.assert_called_once_with(
            messages=[{"role": "user", "content": "Test prompt"}],
            model=llm.DEFAULT_MODEL, # Should use the default model
            temperature=0.7, # Default temperature
            max_tokens=1000  # Default max_tokens
        )

    @patch('openai.OpenAI')
    def test_generate_text_success_custom_params(self, MockOpenAIClient):
        mock_client_instance = MockOpenAIClient.return_value
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Custom text"
        mock_client_instance.chat.completions.create.return_value = mock_response

        llm = OpenAILLM(api_key=self.api_key, model_name="gpt-4-override")
        result = llm.generate_text(
            prompt="Custom prompt",
            model_name="gpt-3.5-explicit", # Override instance default
            temperature=0.9,
            max_tokens=500
        )

        self.assertEqual(result, "Custom text")
        mock_client_instance.chat.completions.create.assert_called_once_with(
            messages=[{"role": "user", "content": "Custom prompt"}],
            model="gpt-3.5-explicit",
            temperature=0.9,
            max_tokens=500
        )
    
    @patch('openai.OpenAI')
    def test_generate_text_api_connection_error(self, MockOpenAIClient):
        mock_client_instance = MockOpenAIClient.return_value
        mock_client_instance.chat.completions.create.side_effect = openai.APIConnectionError(request=MagicMock())
        llm = OpenAILLM(api_key=self.api_key)
        with self.assertRaises(ConnectionError):
            llm.generate_text("Prompt")

    @patch('openai.OpenAI')
    def test_generate_text_rate_limit_error(self, MockOpenAIClient):
        mock_client_instance = MockOpenAIClient.return_value
        mock_client_instance.chat.completions.create.side_effect = openai.RateLimitError(message="Rate limited", response=MagicMock(), body=None)
        llm = OpenAILLM(api_key=self.api_key)
        with self.assertRaises(ConnectionError): # Or a more specific custom error if defined
            llm.generate_text("Prompt")

    @patch('openai.OpenAI')
    def test_generate_text_api_status_error(self, MockOpenAIClient):
        mock_client_instance = MockOpenAIClient.return_value
        # Proper mocking for APIStatusError requires a response object with a status_code
        mock_response = MagicMock(spec=openai.openai_response.OpenAIResponse)
        mock_response.status_code = 400 # Example status code
        mock_client_instance.chat.completions.create.side_effect = openai.APIStatusError(message="Bad request", response=mock_response, body=None)
        llm = OpenAILLM(api_key=self.api_key)
        with self.assertRaises(ConnectionError):
            llm.generate_text("Prompt")

    @patch('openai.OpenAI')
    def test_generate_text_generic_api_error(self, MockOpenAIClient):
        mock_client_instance = MockOpenAIClient.return_value
        mock_client_instance.chat.completions.create.side_effect = openai.APIError(message="Generic API error", request=MagicMock(), body=None)
        llm = OpenAILLM(api_key=self.api_key)
        with self.assertRaises(Exception) as context: # Wraps openai.APIError
            llm.generate_text("Prompt")
        self.assertTrue("OpenAI API error" in str(context.exception))


    @patch('openai.OpenAI')
    def test_list_models_success(self, MockOpenAIClient):
        mock_client_instance = MockOpenAIClient.return_value
        
        # Mock the model objects returned by the API
        model_data_1 = MagicMock()
        model_data_1.id = "gpt-4"
        model_data_2 = MagicMock()
        model_data_2.id = "gpt-3.5-turbo"
        
        mock_models_response = MagicMock()
        mock_models_response.data = [model_data_1, model_data_2]
        mock_client_instance.models.list.return_value = mock_models_response
        
        llm = OpenAILLM(api_key=self.api_key)
        models = llm.list_models()
        
        self.assertEqual(models, ["gpt-4", "gpt-3.5-turbo"])
        mock_client_instance.models.list.assert_called_once()

    @patch('openai.OpenAI')
    def test_list_models_api_error_fallback(self, MockOpenAIClient):
        mock_client_instance = MockOpenAIClient.return_value
        mock_client_instance.models.list.side_effect = openai.APIError(message="Failed to list models", request=MagicMock(), body=None)
        
        llm = OpenAILLM(api_key=self.api_key)
        # Capture print output (optional)
        with patch('sys.stdout', new_callable=MagicMock) as mock_stdout:
             models = llm.list_models()
        
        self.assertEqual(models, OpenAILLM.FALLBACK_MODELS) # Check against the predefined fallback list
        mock_client_instance.models.list.assert_called_once()
        # Check if error was printed (optional)
        # self.assertTrue("Error listing models from OpenAI API" in mock_stdout.getvalue())

    @patch('openai.OpenAI')
    def test_list_models_client_not_initialized_fallback(self, MockOpenAIClient):
        # Simulate client failing to initialize by making it None after super().__init__
        # This requires a bit of careful patching if client is set in super
        # Or, more directly, test the behavior if self.client is None
        llm = OpenAILLM(api_key=self.api_key)
        llm.client = None # Manually set client to None to simulate failed init for this specific test path
        
        with patch('sys.stdout', new_callable=MagicMock) as mock_stdout:
            models = llm.list_models()
        
        self.assertEqual(models, OpenAILLM.FALLBACK_MODELS)
        # self.assertTrue("OpenAI client not initialized. Returning fallback models." in mock_stdout.getvalue())


if __name__ == '__main__':
    # Ensure the path is correct for direct execution
    if '..' not in sys.path:
         sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from llm_openai import OpenAILLM # Re-import for direct run context
    import openai # For direct run context if needed by tests
    unittest.main()
