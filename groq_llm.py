# groq_llm.py
import os
from groq import Groq
from typing import Dict, Any, Optional


class GroqLLM:
    """Simple GROQ LLM wrapper for AI Shadow Coach"""

    def __init__(self, groq_api_key: str = None, model_name: str = "llama3-70b-8192"):
        # Use provided API key or get from environment
        api_key = groq_api_key or os.getenv('GROQ_API_KEY')
        if not api_key:
            raise ValueError(
                "GROQ API key is required. Set GROQ_API_KEY environment variable or pass groq_api_key parameter.")

        # Initialize GROQ client
        self.client = Groq(api_key=api_key)

        # Select the best model for your use case
        self.model_name = model_name

        # Available GROQ models with their capabilities
        self.available_models = {
            # Best for general conversation and reasoning
            "llama3-70b-8192": {
                "name": "Meta Llama 3 70B",
                "context": 8192,
                "best_for": "Complex reasoning, long conversations, detailed analysis"
            },
            # Fastest for quick responses
            "llama3-8b-8192": {
                "name": "Meta Llama 3 8B",
                "context": 8192,
                "best_for": "Quick responses, simple tasks, real-time chat"
            },
            # Best for coding and technical tasks
            "mixtral-8x7b-32768": {
                "name": "Mixtral 8x7B",
                "context": 32768,
                "best_for": "Code generation, technical discussions, large context"
            },
            # Good balance of speed and capability
            "gemma-7b-it": {
                "name": "Google Gemma 7B",
                "context": 8192,
                "best_for": "Balanced performance, instruction following"
            }
        }

        print(f"✅ Initialized GROQ LLM with model: {self.model_name}")
        print(f"📝 Model info: {self.available_models.get(self.model_name, {}).get('best_for', 'General use')}")

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using GROQ API"""
        try:
            # Prepare the message
            messages = [
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            # Make API call to GROQ
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=kwargs.get('max_tokens', 1000),
                temperature=kwargs.get('temperature', 0.7),
                top_p=kwargs.get('top_p', 1.0),
                stream=False
            )

            return response.choices[0].message.content

        except Exception as e:
            error_msg = f"Error calling GROQ API: {str(e)}"
            print(f"❌ {error_msg}")
            return f"Sorry, I encountered an error while processing your request. Please try again."

    def predict(self, text: str, **kwargs) -> str:
        """Simple prediction method (alias for generate)"""
        return self.generate(text, **kwargs)

    def __call__(self, text: str, **kwargs) -> str:
        """Make the class callable"""
        return self.generate(text, **kwargs)

    def chat(self, messages: list, **kwargs) -> str:
        """Chat with multiple messages"""
        try:
            # Make API call to GROQ with message history
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=kwargs.get('max_tokens', 1000),
                temperature=kwargs.get('temperature', 0.7),
                top_p=kwargs.get('top_p', 1.0),
                stream=False
            )

            return response.choices[0].message.content

        except Exception as e:
            error_msg = f"Error in chat: {str(e)}"
            print(f"❌ {error_msg}")
            return f"Sorry, I encountered an error during our chat. Please try again."

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model"""
        return self.available_models.get(self.model_name, {})

    def list_available_models(self) -> Dict[str, Dict]:
        """List all available models and their capabilities"""
        return self.available_models

    def change_model(self, model_name: str):
        """Change the model being used"""
        if model_name in self.available_models:
            old_model = self.model_name
            self.model_name = model_name
            print(f"🔄 Switched from {old_model} to {model_name}")
            print(f"📝 Best for: {self.available_models[model_name].get('best_for', 'General use')}")
            return True
        else:
            print(f"❌ Model {model_name} not available. Available models: {list(self.available_models.keys())}")
            return False

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current model usage statistics"""
        return {
            "current_model": self.model_name,
            "context_length": self.available_models.get(self.model_name, {}).get('context', 'Unknown'),
            "best_for": self.available_models.get(self.model_name, {}).get('best_for', 'General use')
        }