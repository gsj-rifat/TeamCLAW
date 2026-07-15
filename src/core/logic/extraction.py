from typing import Tuple

from src.core.interfaces.llm import LLMProvider
from src.core.models.insights import ExtractedInsights, ExtractedItem
from src.infrastructure.config import settings
from src.infrastructure.logging_config import get_logger
from src.infrastructure.prompts import EXTRACTION_PROMPT, NOISE_FILTER_PROMPT

logger = get_logger(__name__)


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
            logger.warning("Noise filter error: %s", e)
            return True, "Error in filter"

    async def extract(self, text: str) -> ExtractedInsights:
        prompt = EXTRACTION_PROMPT.format(text=text)
        try:
            data = await self.llm.generate_json(prompt)
            decisions = [
                ExtractedItem(text=d.get("text", ""), reason=d.get("reason"))
                for d in data.get("decisions", [])
                if d.get("text")
            ]
            todos = [
                ExtractedItem(
                    text=t.get("text", ""),
                    reason=t.get("reason"),
                    assignee=t.get("assignee"),
                    due_date=t.get("due_date"),
                )
                for t in data.get("todos", [])
                if t.get("text")
            ]
            facts = [
                ExtractedItem(text=f.get("text", ""), reason=f.get("reason"))
                for f in data.get("facts", [])
                if f.get("text")
            ]
            return ExtractedInsights(decisions=decisions, todos=todos, facts=facts)
        except Exception as e:
            logger.warning("Extraction error: %s", e)
            return ExtractedInsights()
