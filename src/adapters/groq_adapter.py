import json
from groq import AsyncGroq
from typing import Dict, Any
from src.core.interfaces.llm import LLMProvider
from src.infrastructure.config import settings

class GroqAdapter(LLMProvider):
    def __init__(self, api_key: str = settings.groq_api_key, model: str = settings.groq_model):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model

    async def generate_text(self, prompt: str, **kwargs) -> str:
        try:
            chat_completion = await self.client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model=self.model,
                temperature=kwargs.get("temperature", 0.5),
                max_tokens=kwargs.get("max_tokens", 1024),
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            print(f"Error in GroqAdapter.generate_text: {e}")
            raise

    async def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        text_response = await self.generate_text(prompt, **kwargs)
        try:
            # Naive JSON extraction (robust extraction would go here or in logic layer)
            # Find first { and last }
            start = text_response.find("{")
            end = text_response.rfind("}")
            if start != -1 and end != -1:
                json_str = text_response[start:end+1]
                return json.loads(json_str)
            return json.loads(text_response)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON from Groq response: {text_response}")
            return {}
