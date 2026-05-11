import logging
from openai import OpenAI

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class WebAILLM:
    def __init__(self):
        self.client = OpenAI(
            api_key="dummy",
            base_url="http://127.0.0.1:6969/v1"
        )

    def generate(self, prompt: str, model="gemini-3-flash"):
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.choices[0].message.content


def get_llm_client():
    logger.info("Getting WebAI LLM client instance")
    return WebAILLM()