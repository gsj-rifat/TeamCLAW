from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
from src.core.interfaces.messaging import NotificationProvider
from src.infrastructure.config import settings

class SlackAdapter(NotificationProvider):
    def __init__(self, token: str = settings.slack_bot_token):
        self.client = AsyncWebClient(token=token)

    async def post_message(self, channel_id: str, text: str) -> bool:
        if not channel_id:
            return False
        try:
            await self.client.chat_postMessage(channel=channel_id, text=text)
            return True
        except SlackApiError as e:
            print(f"Error posting to Slack channel {channel_id}: {e}")
            return False

    async def post_thread_reply(self, channel_id: str, thread_ts: str, text: str) -> bool:
        if not channel_id or not thread_ts:
            return False
        try:
            await self.client.chat_postMessage(channel=channel_id, text=text, thread_ts=thread_ts)
            return True
        except SlackApiError as e:
            print(f"Error posting thread reply to Slack {channel_id}: {e}")
            return False

    async def get_permalink(self, channel_id: str, message_ts: str) -> str:
        """
        Get a permanent link to a Slack message for Proof of Insight.
        
        Args:
            channel_id: The channel where the message was posted
            message_ts: The timestamp of the message
            
        Returns:
            The permanent URL to the message, or empty string if failed
        """
        if not channel_id or not message_ts:
            return ""
        try:
            result = await self.client.chat_getPermalink(channel=channel_id, message_ts=message_ts)
            return result.get("permalink", "")
        except SlackApiError as e:
            print(f"Error getting permalink for {channel_id}/{message_ts}: {e}")
            return ""

