from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from src.core.models.insights import InsightRecord, ExtractedInsights
from src.core.models.sop import Sop

class DatabasePort(ABC):
    @abstractmethod
    async def save_insight(self, insight: InsightRecord) -> int:
        pass

    @abstractmethod
    async def fetch_insights(self, start_ts: int, end_ts: int, channel_id: Optional[str] = None) -> List[InsightRecord]:
        pass

    @abstractmethod
    async def save_sop(self, sop: Sop) -> int:
        pass

    @abstractmethod
    async def fetch_sops(self, limit: int = 100, status: Optional[str] = None) -> List[Sop]:
        pass
