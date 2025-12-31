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
