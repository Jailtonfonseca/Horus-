from llm_interface import LLMInterface
import openai

class OpenAILLM(LLMInterface):
    """
    LLM Interface implementation for OpenAI API.
    """
    DEFAULT_MODEL = "gpt-3.5-turbo"
    FALLBACK_MODELS = ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo"] # Common models

    def __init__(self, api_key: str, model_name: str = None):
        """
        Initializes the OpenAILLM client.

        Args:
            api_key: The OpenAI API key.
            model_name: Optional default model name to use. Defaults to "gpt-3.5-turbo".
        """
        super().__init__(api_key=api_key, model_name=model_name or self.DEFAULT_MODEL)
        try:
            self.client = openai.OpenAI(api_key=self.api_key)
        except Exception as e:
            # Handle client initialization errors, e.g., invalid API key format
            print(f"Error initializing OpenAI client: {e}")
            # Potentially raise a custom exception or set client to None and handle in methods
            raise ConnectionError(f"Failed to initialize OpenAI client: {e}")

    def generate_text(self, prompt: str, model_name: str = None, temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """
        Generates text using the OpenAI API.

        Args:
            prompt: The prompt to send to the LLM.
            model_name: Optional model name to override the default.
            temperature: Sampling temperature.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text as a string.
        
        Raises:
            ConnectionError: If the client is not initialized or API connection issues.
            Exception: For other API errors or unexpected issues.
        """
        if not self.client:
            raise ConnectionError("OpenAI client not initialized. Cannot generate text.")

        selected_model = model_name or self.default_model_name
        if not selected_model:
             raise ValueError("Model name must be provided or set during initialization.")

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model=selected_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except openai.APIConnectionError as e:
            print(f"OpenAI API connection error: {e}")
            raise ConnectionError(f"OpenAI API connection error: {e}")
        except openai.RateLimitError as e:
            print(f"OpenAI API rate limit exceeded: {e}")
            raise ConnectionError(f"OpenAI API rate limit exceeded: {e}") # Consider specific RateLimitError
        except openai.APIStatusError as e:
            print(f"OpenAI API status error {e.status_code}: {e.response}")
            raise ConnectionError(f"OpenAI API status error {e.status_code}: {e.response}")
        except openai.APIError as e: # General OpenAI API error
            print(f"OpenAI API error: {e}")
            raise Exception(f"OpenAI API error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred with OpenAI API: {e}")
            raise Exception(f"An unexpected error occurred with OpenAI API: {e}")

    def list_models(self) -> list[str]:
        """
        Lists available models using the OpenAI API.
        Falls back to a predefined list if the API call fails.

        Returns:
            A list of model ID strings.
        """
        if not self.client:
            print("OpenAI client not initialized. Returning fallback models.")
            return self.FALLBACK_MODELS.copy()
        try:
            models_response = self.client.models.list()
            return [model.id for model in models_response.data]
        except openai.APIError as e:
            print(f"Error listing models from OpenAI API: {e}. Returning fallback models.")
            return self.FALLBACK_MODELS.copy()
        except Exception as e:
            print(f"An unexpected error occurred while listing OpenAI models: {e}. Returning fallback models.")
            return self.FALLBACK_MODELS.copy()
