class MainAgent:
    """
    The main agent responsible for orchestrating subordinate agents.
    """
    def __init__(self, groq_api_key: str):
        """
        Initializes the MainAgent.

import os # Added import
from llm_groq import GroqLLM
from llm_openai import OpenAILLM

class MainAgent:
    """
    The main agent responsible for orchestrating subordinate agents.
    API keys are retrieved from environment variables.
    """
    def __init__(self):
        """
        Initializes the MainAgent.
        Retrieves API keys from environment variables:
        - GROQ_API_KEY for Groq
        - OPENAI_API_KEY for OpenAI
        """
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.agents = {}
        self.next_agent_id = 0
        # TODO: Potentially initialize a default LLM client here or allow selection.

    def create_subordinate_agent(self, prompt: str, llm_type: str = "groq", model_name: str = None):
        """
        Creates, stores, and returns a new SubordinateAgent instance,
        initialized with a specified LLM client and optional model name.

        Args:
            prompt: The prompt for the subordinate agent.
            llm_type: The type of LLM to use (e.g., "groq", "openai"). Default is "groq".
            model_name: Optional specific model name to pass to the LLM client.
        
        Returns:
            The created SubordinateAgent instance.
        
        Raises:
            ValueError: If an unsupported llm_type is provided or if the required API key is missing.
        """
        from subordinate_agent import SubordinateAgent
        
        llm_client = None
        if llm_type == "groq":
            if not self.groq_api_key:
                raise ValueError("Groq API key not provided to MainAgent for llm_type 'groq'.")
            llm_client = GroqLLM(api_key=self.groq_api_key, model_name=model_name)
        elif llm_type == "openai":
            if not self.openai_api_key:
                raise ValueError("OpenAI API key not provided to MainAgent for llm_type 'openai'.")
            llm_client = OpenAILLM(api_key=self.openai_api_key, model_name=model_name)
        else:
            raise ValueError(f"Unsupported LLM type: {llm_type}")

        agent_id = self.next_agent_id
        self.next_agent_id += 1
        
        agent = SubordinateAgent(prompt=prompt, llm_client=llm_client)
        agent.id = agent_id 
        self.agents[agent_id] = agent
        
        return agent

    def manage_agents(self):
        """
        Manages the lifecycle and execution of subordinate agents.
        (Placeholder for now)
        """
        # TODO: Implement agent management logic
        print(f"Managing {len(self.agents)} agents.")
        pass

    def reconstruct_subordinate_agent(self, agent_id: int, new_prompt: str):
        """
        Finds a subordinate agent by its ID and prompts it to regenerate
        code with a new prompt.

        Args:
            agent_id: The ID of the agent to reconstruct.
            new_prompt: The new prompt for the agent.
        
        Returns:
            The agent instance if found and reconstruction initiated, else None.
        """
        agent = self.agents.get(agent_id)
        if agent:
            print(f"Reconstructing agent {agent_id} with new prompt.")
            agent.regenerate_with_new_prompt(new_prompt)
            return agent
        else:
            print(f"Agent {agent_id} not found.")
            return None
