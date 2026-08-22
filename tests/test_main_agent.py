import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import io

from main_agent import MainAgent
from subordinate_agent import SubordinateAgent 
from llm_interface import LLMInterface 
from llm_groq import GroqLLM
from llm_openai import OpenAILLM

class TestMainAgent(unittest.TestCase):
    @patch.dict(os.environ, {"GROQ_API_KEY": "env_groq_key", "OPENAI_API_KEY": "env_openai_key"})
    def test_initialization_with_env_keys(self):
        main_agent = MainAgent()
        self.assertEqual(main_agent.groq_api_key, "env_groq_key")
        self.assertEqual(main_agent.openai_api_key, "env_openai_key")
        self.assertEqual(main_agent.agents, {})
        self.assertEqual(main_agent.next_agent_id, 0)

    @patch.dict(os.environ, {}, clear=True)
    def test_initialization_without_env_keys(self):
        main_agent = MainAgent()
        self.assertIsNone(main_agent.groq_api_key)
        self.assertIsNone(main_agent.openai_api_key)

    @patch.dict(os.environ, {"GROQ_API_KEY": "test_groq_key_from_env"})
    @patch('main_agent.GroqLLM') 
    @patch('main_agent.SubordinateAgent')
    def test_create_subordinate_agent_groq_with_env_key(self, MockSubordinateAgent, MockGroqLLM):
        main_agent = MainAgent()
        self.assertEqual(main_agent.groq_api_key, "test_groq_key_from_env")

        mock_llm_instance = MockGroqLLM.return_value
        mock_sub_agent_instance = MockSubordinateAgent.return_value
        
        prompt = "Test subordinate prompt"
        agent = main_agent.create_subordinate_agent(prompt=prompt, llm_type="groq")

        MockGroqLLM.assert_called_once_with(api_key="test_groq_key_from_env", model_name=None)
        MockSubordinateAgent.assert_called_once_with(prompt=prompt, llm_client=mock_llm_instance)
        
        self.assertEqual(agent, mock_sub_agent_instance)
        self.assertEqual(agent.id, 0)
        self.assertIn(0, main_agent.agents)
        self.assertEqual(main_agent.agents[0], mock_sub_agent_instance)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test_openai_key_from_env"})
    @patch('main_agent.OpenAILLM')
    @patch('main_agent.SubordinateAgent')
    def test_create_subordinate_agent_openai_with_env_key(self, MockSubordinateAgent, MockOpenAILLM):
        main_agent = MainAgent()
        self.assertEqual(main_agent.openai_api_key, "test_openai_key_from_env")

        mock_llm_instance = MockOpenAILLM.return_value
        mock_sub_agent_instance = MockSubordinateAgent.return_value
        
        prompt = "Test OpenAI prompt"
        model_name_param = "gpt-4-test"
        agent = main_agent.create_subordinate_agent(prompt=prompt, llm_type="openai", model_name=model_name_param)

        MockOpenAILLM.assert_called_once_with(api_key="test_openai_key_from_env", model_name=model_name_param)
        MockSubordinateAgent.assert_called_once_with(prompt=prompt, llm_client=mock_llm_instance)
        
        self.assertEqual(agent, mock_sub_agent_instance)
        self.assertEqual(agent.id, 0)

    @patch.dict(os.environ, {}, clear=True)
    def test_create_subordinate_agent_groq_no_env_key(self):
        main_agent = MainAgent()
        self.assertIsNone(main_agent.groq_api_key)
        with self.assertRaisesRegex(ValueError, "Groq API key not provided to MainAgent for llm_type 'groq'."):
            main_agent.create_subordinate_agent(prompt="p", llm_type="groq")

    @patch.dict(os.environ, {}, clear=True)
    def test_create_subordinate_agent_openai_no_env_key(self):
        main_agent = MainAgent()
        self.assertIsNone(main_agent.openai_api_key)
        with self.assertRaisesRegex(ValueError, "OpenAI API key not provided to MainAgent for llm_type 'openai'."):
            main_agent.create_subordinate_agent(prompt="Test", llm_type="openai")

    @patch.dict(os.environ, {"GROQ_API_KEY": "dummy_key"})
    def test_create_subordinate_agent_unsupported_llm(self):
        main_agent = MainAgent()
        with self.assertRaisesRegex(ValueError, "Unsupported LLM type: unknown_llm"):
            main_agent.create_subordinate_agent(prompt="Test", llm_type="unknown_llm")

    @patch.dict(os.environ, {"GROQ_API_KEY": "dummy_key"})
    def test_reconstruct_subordinate_agent_found(self):
        main_agent = MainAgent()
        mock_existing_agent = MagicMock(spec=SubordinateAgent)
        mock_existing_agent.id = 0
        
        main_agent.agents[0] = mock_existing_agent
        main_agent.next_agent_id = 1

        new_prompt = "Reconstruction prompt"
        reconstructed_agent = main_agent.reconstruct_subordinate_agent(agent_id=0, new_prompt=new_prompt)

        self.assertEqual(reconstructed_agent, mock_existing_agent)
        mock_existing_agent.regenerate_with_new_prompt.assert_called_once_with(new_prompt)

    @patch.dict(os.environ, {"GROQ_API_KEY": "dummy_key"})
    def test_reconstruct_subordinate_agent_not_found(self):
        main_agent = MainAgent()
        new_prompt = "Reconstruction prompt"
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            reconstructed_agent = main_agent.reconstruct_subordinate_agent(agent_id=99, new_prompt=new_prompt)
            self.assertIsNone(reconstructed_agent)
            self.assertTrue("Agent 99 not found" in mock_stdout.getvalue())
            
    @patch.dict(os.environ, {"GROQ_API_KEY": "dummy_key"})
    @patch('main_agent.SubordinateAgent')
    def test_manage_agents_placeholder(self, MockSubordinateAgent):
        main_agent = MainAgent()
        main_agent.create_subordinate_agent("prompt1")
        main_agent.create_subordinate_agent("prompt2")

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            main_agent.manage_agents()
            self.assertTrue("Managing 2 agents" in mock_stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
