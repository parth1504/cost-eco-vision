import google.generativeai as genai
import os
import logging

# Initialize logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class GeminiLLM:
    def __init__(self):
        logger.info("Initializing GeminiLLM")
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    def generate(self, prompt):
        logger.info("Generating content with prompt: %s", prompt)
        try:
            response = self.model.generate_content(prompt)
            return response.text if hasattr(response, "text") else str(response)
        except Exception as e:
            logger.error("Error generating content: %s", e)
            return "Unable to generate explanation."