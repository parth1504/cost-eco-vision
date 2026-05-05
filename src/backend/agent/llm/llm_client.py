import logging

# Initialize logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from agent.llm.providers.gemini_client import GeminiLLM

def get_llm_client():
    logger.info("Getting LLM client instance")
    return GeminiLLM()