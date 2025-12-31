from typing import List
from src.core.interfaces.llm import LLMProvider
from src.core.interfaces.db import DatabasePort
from src.core.models.sop import Sop, Sopreadiness

class SopGenerator:
    def __init__(self, llm: LLMProvider, db: DatabasePort):
        self.llm = llm
        self.db = db

    async def check_readiness(self, topic: str, context: List[str]) -> Sopreadiness:
        # Simple implementation for now - strict check
        if len(context) < 3:
             return Sopreadiness(is_complete=False, missing_info=["Not enough context messages"])
        
        # In a real scenario, this would ask LLM if context is sufficient
        return Sopreadiness(is_complete=True)

    async def generate_sop(self, topic: str, input_context: List[str]) -> str:
        context_str = "\n".join(input_context)
        prompt = f"""
        Draft a Standard Operating Procedure (SOP) for "{topic}" based on this context:
        
        {context_str}
        
        Format as Markdown with Title, Purpose, Scope, Procedures.
        """
        return await self.llm.generate_text(prompt)
