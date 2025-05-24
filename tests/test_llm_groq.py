import unittest
from unittest.mock import MagicMock, patch
import groq as groq_sdk # Alias to avoid conflict with module name 'groq' if used as var

# Ensure the main project directory is in the Python path if running directly
import sys
import os
# if '..' not in sys.path:
#     sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm_groq import GroqLLM # The class we are testing

class TestGroqLLM(unittest.TestCase):
    def setUp(self):
        self.api_key = "fake_groq_api_key"
        self.default_model = GroqLLM.DEFAULT_MODEL # "mixtral-8x7b-32768"

    @patch('llm_groq.groq.Groq') # Patch where Groq client is instantiated in llm_groq.py
    def test_initialization_success(self, MockGroqClient):
        mock_client_instance = MockGroqClient.return_value
        llm = GroqLLM(api_key=self.api_key, model_name="llama3-70b-8192")
        
        MockGroqClient.assert_called_once_with(api_key=self.api_key)
        self.assertEqual(llm.api_key, self.api_key)
        self.assertEqual(llm.default_model_name, "llama3-70b-8192")
        self.assertIs(llm.client, mock_client_instance)

    @patch('llm_groq.groq.Groq')
    def test_initialization_default_model(self, MockGroqClient):
        llm = GroqLLM(api_key=self.api_key) # No model_name provided
        self.assertEqual(llm.default_model_name, self.default_model)

    @patch('llm_groq.groq.Groq')
    def test_initialization_client_error(self, MockGroqClient):
        MockGroqClient.side_effect = Exception("Client init failed")
        with self.assertRaisesRegex(ConnectionError, "Failed to initialize Groq client: Client init failed"):
            GroqLLM(api_key=self.api_key)

    @patch('llm_groq.groq.Groq')
    def test_generate_text_success_default_model(self, MockGroqClient):
        mock_client_instance = MockGroqClient.return_value
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated Groq text"
        mock_client_instance.chat.completions.create.return_value = mock_response
        
        llm = GroqLLM(api_key=self.api_key) # Uses default model
        result = llm.generate_text("Test prompt")

        self.assertEqual(result, "Generated Groq text")
        mock_client_instance.chat.completions.create.assert_called_once_with(
            messages=[{"role": "user", "content": "Test prompt"}],
            model=self.default_model,
            temperature=0.7, # Default temperature
            max_tokens=1000  # Default max_tokens
        )

    @patch('llm_groq.groq.Groq')
    def test_generate_text_success_custom_params(self, MockGroqClient):
        mock_client_instance = MockGroqClient.return_value
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Custom Groq text"
        mock_client_instance.chat.completions.create.return_value = mock_response

        llm = GroqLLM(api_key=self.api_key, model_name="llama3-8b-8192") # Instance default
        result = llm.generate_text(
            prompt="Custom prompt",
            model_name="gemma-7b-it", # Override instance default
            temperature=0.9,
            max_tokens=500
        )

        self.assertEqual(result, "Custom Groq text")
        mock_client_instance.chat.completions.create.assert_called_once_with(
            messages=[{"role": "user", "content": "Custom prompt"}],
            model="gemma-7b-it",
            temperature=0.9,
            max_tokens=500
        )
    
    @patch('llm_groq.groq.Groq')
    def test_generate_text_api_connection_error(self, MockGroqClient):
        mock_client_instance = MockGroqClient.return_value
        mock_client_instance.chat.completions.create.side_effect = groq_sdk.APIConnectionError(request=MagicMock())
        llm = GroqLLM(api_key=self.api_key)
        with self.assertRaisesRegex(ConnectionError, "Groq API connection error"):
            llm.generate_text("Prompt")

    @patch('llm_groq.groq.Groq')
    def test_generate_text_rate_limit_error(self, MockGroqClient):
        mock_client_instance = MockGroqClient.return_value
        mock_client_instance.chat.completions.create.side_effect = groq_sdk.RateLimitError(message="Rate limited", response=MagicMock(), body=None)
        llm = GroqLLM(api_key=self.api_key)
        with self.assertRaisesRegex(ConnectionError, "Groq API rate limit exceeded"):
            llm.generate_text("Prompt")

    @patch('llm_groq.groq.Groq')
    def test_generate_text_api_status_error(self, MockGroqClient):
        mock_client_instance = MockGroqClient.return_value
        mock_response = MagicMock(spec=groq_sdk.groq_response.GroqResponse) # Adjusted for Groq if different
        mock_response.status_code = 400 
        mock_client_instance.chat.completions.create.side_effect = groq_sdk.APIStatusError(message="Bad request", response=mock_response, body=None)
        llm = GroqLLM(api_key=self.api_key)
        with self.assertRaisesRegex(ConnectionError, "Groq API status error 400"):
            llm.generate_text("Prompt")

    @patch('llm_groq.groq.Groq')
    def test_generate_text_generic_api_error(self, MockGroqClient):
        # For Groq, a generic error might still be one of the specific ones, or a base APIError
        mock_client_instance = MockGroqClient.return_value
        mock_client_instance.chat.completions.create.side_effect = groq_sdk.APIError("Generic API error", request=MagicMock(), body=None)
        llm = GroqLLM(api_key=self.api_key)
        with self.assertRaises(Exception) as context:
            llm.generate_text("Prompt")
        self.assertTrue("An unexpected error occurred with Groq API" in str(context.exception))


    def test_list_models_success(self):
        # This method in GroqLLM currently returns a hardcoded list
        llm = GroqLLM(api_key=self.api_key)
        models = llm.list_models()
        self.assertEqual(models, GroqLLM.KNOWN_MODELS)
        self.assertNotEqual(models, []) # Ensure it's not empty

    # No client needed for list_models in current GroqLLM, so no error state to test for it.

if __name__ == '__main__':
    # Ensure the path is correct for direct execution
    if '..' not in sys.path:
         sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from llm_groq import GroqLLM # Re-import for direct run context
    import groq as groq_sdk # For direct run context if needed by tests
    unittest.main()
