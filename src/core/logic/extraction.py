from datetime import datetime
from typing import Dict, Any, Tuple
from src.core.interfaces.llm import LLMProvider
from src.core.models.insights import ExtractedInsights
from src.infrastructure.prompts import NOISE_FILTER_PROMPT, EXTRACTION_PROMPT
from src.infrastructure.config import settings

class InsightExtractor:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def is_meaningful(self, text: str) -> Tuple[bool, str]:
        if not settings.noise_filter_enabled:
            return True, "Filter disabled"
        
        if len(text) < settings.noise_min_chars:
            return False, "Too short"

        prompt = NOISE_FILTER_PROMPT.format(text=text)
        try:
            result = await self.llm.generate_json(prompt)
            is_meaningful = result.get("is_meaningful", False)
            confidence = result.get("confidence", 0.0)
            reason = result.get("reason", "")
            
            if is_meaningful and confidence >= settings.noise_llm_threshold:
                return True, reason
            return False, reason
        except Exception as e:
            print(f"Noise filter error: {e}")
            # Failsafe: if error, treat as meaningful to avoid data loss
            return True, "Error in filter"

    async def extract(self, text: str) -> ExtractedInsights:
        prompt = EXTRACTION_PROMPT.format(text=text)
        try:
            data = await self.llm.generate_json(prompt)
            # Normalize list of dicts to list of Pydantic models
            decisions = [{"text": d.get("text"), "reason": d.get("reason")} for d in data.get("decisions", [])]
            todos = [{"text": d.get("text"), "reason": d.get("reason")} for d in data.get("todos", [])]
            facts = [{"text": d.get("text"), "reason": d.get("reason")} for d in data.get("facts", [])]
            
            return ExtractedInsights(decisions=decisions, todos=todos, facts=facts)
        except Exception as e:
            print(f"Extraction error: {e}")
            return ExtractedInsights()
