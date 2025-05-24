import unittest
from unittest.mock import MagicMock, patch

# Ensure the main project directory is in the Python path
import sys
import os
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main_agent import MainAgent
from subordinate_agent import SubordinateAgent # Needed for type checking and instantiation

class TestMainAgent(unittest.TestCase):
    def setUp(self):
        self.main_agent = MainAgent(groq_api_key="main_fake_key")

    def test_initialization(self):
        self.assertEqual(self.main_agent.groq_api_key, "main_fake_key")
        self.assertEqual(self.main_agent.agents, {})
        self.assertEqual(self.main_agent.next_agent_id, 0)

    @patch('main_agent.SubordinateAgent') # Patch SubordinateAgent where it's used in main_agent.py
    def test_create_subordinate_agent(self, MockSubordinateAgent):
        # Configure the mock SubordinateAgent instance that will be returned
        mock_agent_instance = MockSubordinateAgent.return_value
        
        prompt = "Test subordinate prompt"
        agent = self.main_agent.create_subordinate_agent(prompt)

        # Check that SubordinateAgent was called correctly
        MockSubordinateAgent.assert_called_once_with(prompt=prompt, groq_api_key="main_fake_key")
        
        # Check that an ID was assigned and the agent is stored
        self.assertEqual(agent, mock_agent_instance) # Ensure the created agent is returned
        self.assertEqual(agent.id, 0) # First agent ID
        self.assertIn(0, self.main_agent.agents)
        self.assertEqual(self.main_agent.agents[0], mock_agent_instance)
        self.assertEqual(self.main_agent.next_agent_id, 1)

        # Create another agent to check ID increment
        prompt2 = "Another prompt"
        agent2 = self.main_agent.create_subordinate_agent(prompt2)
        self.assertEqual(agent2.id, 1)
        self.assertIn(1, self.main_agent.agents)
        self.assertEqual(self.main_agent.agents[1], mock_agent_instance) # Still mock_agent_instance if not reset
        self.assertEqual(self.main_agent.next_agent_id, 2)


    def test_reconstruct_subordinate_agent_found(self):
        # Create a real SubordinateAgent (or a more detailed mock) for this test
        # because we need to interact with its methods/attributes if not fully mocking regenerate
        existing_agent = SubordinateAgent(prompt="Original prompt", groq_api_key="main_fake_key")
        existing_agent.id = 0 
        
        # Mock the method that would be called
        existing_agent.regenerate_with_new_prompt = MagicMock()
        
        self.main_agent.agents[0] = existing_agent
        self.main_agent.next_agent_id = 1 # Simulate it was already created

        new_prompt = "Reconstruction prompt"
        reconstructed_agent = self.main_agent.reconstruct_subordinate_agent(agent_id=0, new_prompt=new_prompt)

        self.assertEqual(reconstructed_agent, existing_agent)
        existing_agent.regenerate_with_new_prompt.assert_called_once_with(new_prompt)

    def test_reconstruct_subordinate_agent_not_found(self):
        new_prompt = "Reconstruction prompt"
        # Capture print output to verify message (optional)
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            reconstructed_agent = self.main_agent.reconstruct_subordinate_agent(agent_id=99, new_prompt=new_prompt)
            self.assertIsNone(reconstructed_agent)
            self.assertTrue("Agent 99 not found" in mock_stdout.getvalue())
            
    @patch('main_agent.SubordinateAgent')
    def test_manage_agents_placeholder(self, MockSubordinateAgent):
        # This test is minimal as manage_agents is a placeholder
        # It primarily serves to ensure the method can be called without error.
        self.main_agent.create_subordinate_agent("prompt1")
        self.main_agent.create_subordinate_agent("prompt2")

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            self.main_agent.manage_agents()
            self.assertTrue("Managing 2 agents" in mock_stdout.getvalue())


if __name__ == '__main__':
    # This allows running the tests directly from this file
    # Adjust path if main_agent or subordinate_agent are not in the root or PYTHONPATH
    if '..' not in sys.path:
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from main_agent import MainAgent
    from subordinate_agent import SubordinateAgent # For type hinting or direct use if not mocking
    import io # For capturing stdout
    unittest.main()
