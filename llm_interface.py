from abc import ABC, abstractmethod

class LLMInterface(ABC):
    """
    Abstract base class for Large Language Model interfaces.
    """
    def __init__(self, api_key: str, model_name: str = None):
        """
        Initializes the LLM interface.

        Args:
            api_key: The API key for the LLM service.
            model_name: Optional default model name to use for generation.
        """
        self.api_key = api_key
        self.default_model_name = model_name

    @abstractmethod
    def generate_text(self, prompt: str, model_name: str = None, temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """
        Generates text using the LLM.

        Args:
            prompt: The prompt to send to the LLM.
            model_name: Optional model name to override the default.
            temperature: Sampling temperature.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text as a string.
        
        Raises:
            NotImplementedError: If the method is not implemented by a subclass.
            Exception: For API errors or other issues during generation.
        """
        raise NotImplementedError

    @abstractmethod
    def list_models(self) -> list[str]:
        """
        Lists available models.

        Returns:
            A list of model name strings.
        
        Raises:
            NotImplementedError: If the method is not implemented by a subclass.
        """
        raise NotImplementedError
