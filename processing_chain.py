import os
import json
from dotenv import load_dotenv
from groq_llm import GroqLLM
from datetime import datetime

load_dotenv()

class MessageProcessor:
    def __init__(self, groq_api_key=None):
        print("🚀 Initializing MessageProcessor with GROQ...")
        self.llm = GroqLLM(
            groq_api_key=groq_api_key,
            model_name="llama3-70b-8192"
        )
        self.conversation_history = []
        print("✅ MessageProcessor initialized successfully")

    def process_message(self, message_text: str, user_id: str = None) -> str:
        """Process incoming Slack message and generate coaching response"""
        print(f"📨 Processing message from user {user_id}: {message_text[:50]}...")
        coaching_prompt = f"""You are an AI Shadow Coach designed to help professionals improve their communication, productivity, and leadership skills through Slack interactions.

Current situation: A team member has sent you this message: "{message_text}"

As their AI Shadow Coach, provide:
1. Brief acknowledgment of their message
2. One key insight or coaching point
3. One actionable suggestion
4. Encouraging closing

Guidelines:
- Keep response under 150 words
- Be supportive and professional
- Focus on growth and improvement
- Use a friendly, coaching tone

Response:"""

        try:
            print("🤖 Generating coaching response...")
            response = self.llm.generate(coaching_prompt, temperature=0.7, max_tokens=200)
            self.conversation_history.append({
                "user": user_id,
                "message": message_text,
                "response": response,
                "timestamp": self._get_timestamp()
            })
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            print("✅ Response generated successfully")
            return response
        except Exception as e:
            error_msg = "I'm experiencing some technical difficulties right now. Please try again in a moment."
            print(f"❌ Error processing message: {str(e)}")
            return error_msg

    def extract_categories(self, transcript: str) -> dict:
        """
        Extracts categorized content from a chat transcript.
        Returns JSON {Decisions, ToDos, SOPs, Facts}
        """
        extraction_prompt = f"""
Analyze the following Slack conversation transcript.
For each message, extract and categorize into:
- Decisions (choices made or agreed upon)
- To-Dos (tasks to be completed)
- SOPs (Standard Operating Procedures stated or referenced)
- Facts (objective statements)

Provide output as a JSON object with each key being a category, and the value being a list of extracted items: original text and brief rationale.
Strictly use this format:
{{
  "Decisions": [{{"text": "...", "reason": "..."}}, ...],
  "ToDos": [{{"text": "...", "reason": "..."}}, ...],
  "SOPs": [{{"text": "...", "reason": "..."}}, ...],
  "Facts": [{{"text": "...", "reason": "..."}}, ...]
}}
Omit any category with no results.

Transcript:
{transcript}

Respond with valid JSON only.
        """
        try:
            print("🧠 Running structured extraction prompt...")
            response = self.llm.generate(extraction_prompt, temperature=0.3, max_tokens=700)
            return json.loads(response)
        except Exception as e:
            print(f"❌ Extraction failed: {e}")
            return {"error": "Extraction failed", "raw_response": response if 'response' in locals() else ""}

    def process_command(self, command: str, parameters: str = "", user_id: str = None) -> str:
        """Process specific coaching commands"""
        print(f"⚡ Processing command: {command} with parameters: {parameters}")
        command_prompts = {
            "feedback": f"""As an AI Shadow Coach, provide constructive feedback on this situation: "{parameters}"
Focus on: What went well, Areas for improvement, Specific next steps. Encouraging tone. Under 150 words.""",
            "improve": f"""As an AI Shadow Coach, suggest improvements for this communication: "{parameters}"
Provide: Specific improvement areas, Better phrasing suggestions, Communication best practices, Actionable tips, under 150 words.""",
            "goals": f"""As an AI Shadow Coach, help set professional development goals related to: "{parameters}"
Include: 2-3 SMART goals, Why these goals matter, First steps to take, Success metrics. Under 150 words.""",
            "skills": f"""As an AI Shadow Coach, recommend skill development for: "{parameters}"
Cover: Key skills to develop, Learning resources, Practice opportunities, Timeline suggestions. Under 150 words.""",
            "help": """I'm your AI Shadow Coach! Here's how I can help:
🎯 *feedback [situation]* — Get constructive feedback
🚀 *improve [message]* — Improve your communication
📈 *goals [area]* — Set professional goals
🛠️ *skills [topic]* — Develop new skills
📊 *stats* — View your coaching statistics
Type: `/coach [command] [your text]`
Example: `/coach feedback I had a difficult meeting with my team today`"""
        }
        prompt = command_prompts.get(command.lower(), f"As an AI Shadow Coach, help with: {command} {parameters}")
        try:
            response = self.llm.generate(prompt, temperature=0.6, max_tokens=200)
            print("✅ Command processed successfully")
            return response
        except Exception as e:
            error_msg = "I couldn't process that command right now. Please try '/coach help' for available commands."
            print(f"❌ Error processing command: {str(e)}")
            return error_msg

    def get_stats(self, user_id: str = None) -> str:
        """Get coaching statistics for a user"""
        if user_id:
            user_interactions = [h for h in self.conversation_history if h.get('user') == user_id]
            count = len(user_interactions)
            return f"📊 You've had {count} coaching interactions with me!"
        else:
            total = len(self.conversation_history)
            return f"📊 Total coaching interactions: {total}"

    def _get_timestamp(self):
        """Get current timestamp"""
        return datetime.now().isoformat()

    def get_model_info(self) -> str:
        """Get current GROQ model information"""
        stats = self.llm.get_usage_stats()
        return f"🤖 Using {stats['current_model']} - Best for: {stats['best_for']}"