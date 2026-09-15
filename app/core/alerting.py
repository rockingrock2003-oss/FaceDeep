import os

import httpx
from fastapi import Request


class SlackNotifier:
    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        self.channel = os.getenv("SLACK_CHANNEL", "#alerts")

    async def send(self, text: str, severity: str = "info"):
        if not self.webhook_url:
            return

        emoji_map = {
            "info": ":information_source:",
            "warning": ":warning:",
            "error": ":rotating_light:",
            "critical": ":fire:",
        }

        emoji = emoji_map.get(severity, ":information_source:")

        payload = {
            "channel": self.channel,
            "text": f"{emoji} *[FaceDeep]* {text}",
        }

        async with httpx.AsyncClient() as client:
            await client.post(self.webhook_url, json=payload)


slack = SlackNotifier()
