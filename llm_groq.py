from llm_interface import LLMInterface
import groq

class GroqLLM(LLMInterface):
    """
    LLM Interface implementation for Groq API.
    """
    DEFAULT_MODEL = "mixtral-8x7b-32768"
    KNOWN_MODELS = [
        "mixtral-8x7b-32768",
        "llama3-70b-8192",
        "llama3-8b-8192",
        "gemma-7b-it"
    ]

    def __init__(self, api_key: str, model_name: str = None):
        """
        Initializes the GroqLLM client.

        Args:
            api_key: The Groq API key.
            model_name: Optional default model name to use.
        """
        super().__init__(api_key=api_key, model_name=model_name or self.DEFAULT_MODEL)
        try:
            self.client = groq.Groq(api_key=self.api_key)
        except Exception as e:
            # Handle client initialization errors, e.g., invalid API key format
            # (though Groq client might not validate key until first API call)
            print(f"Error initializing Groq client: {e}")
            # Potentially raise a custom exception or set client to None and handle in methods
            raise ConnectionError(f"Failed to initialize Groq client: {e}")


    def generate_text(self, prompt: str, model_name: str = None, temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """
        Generates text using the Groq API.

        Args:
            prompt: The prompt to send to the LLM.
            model_name: Optional model name to override the default.
            temperature: Sampling temperature.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text as a string.
        
        Raises:
            Exception: For API errors or other issues during generation.
        """
        if not self.client:
            raise ConnectionError("Groq client not initialized. Cannot generate text.")

        selected_model = model_name or self.default_model_name
        if not selected_model: # Should have been set by init or provided
             raise ValueError("Model name must be provided or set during initialization.")


        try:
            chat_completion = self.client.chat.completions.create(
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
            return chat_completion.choices[0].message.content
        except groq.APIConnectionError as e:
            print(f"Groq API connection error: {e}")
            raise ConnectionError(f"Groq API connection error: {e}")
        except groq.RateLimitError as e:
            print(f"Groq API rate limit exceeded: {e}")
            raise ConnectionError(f"Groq API rate limit exceeded: {e}") # Or a specific RateLimitError
        except groq.APIStatusError as e:
            print(f"Groq API status error {e.status_code}: {e.response}")
            raise ConnectionError(f"Groq API status error {e.status_code}: {e.response}")
        except Exception as e:
            print(f"An unexpected error occurred with Groq API: {e}")
            raise Exception(f"An unexpected error occurred with Groq API: {e}")

    def list_models(self) -> list[str]:
        """
        Lists known available models for Groq (as API doesn't provide a direct listing endpoint).

        Returns:
            A list of model name strings.
        """
        return self.KNOWN_MODELS.copy()
