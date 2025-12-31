from abc import ABC, abstractmethod
from typing import List, Optional

class TicketProvider(ABC):
    @abstractmethod
    async def create_ticket(self, project_key: str, summary: str, description: str, labels: List[str]) -> str:
        """Create a ticket and return its key/ID."""
        pass

    @abstractmethod
    async def update_ticket(self, key: str, summary: Optional[str] = None, description: Optional[str] = None) -> bool:
        """Update an existing ticket."""
        pass
