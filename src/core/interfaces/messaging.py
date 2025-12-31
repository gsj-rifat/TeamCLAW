from abc import ABC, abstractmethod
from typing import Optional

class NotificationProvider(ABC):
    @abstractmethod
    async def post_message(self, channel_id: str, text: str) -> bool:
        """Post a message to a channel."""
        pass

    @abstractmethod
    async def post_thread_reply(self, channel_id: str, thread_ts: str, text: str) -> bool:
        """Post a reply in a message thread."""
        pass
