"""Guest messages (e.g. 'your table is ready'), behind a provider so SMS can be switched on later.

"log" records the message in Larder only. To send real texts, add a provider (e.g. Twilio):
subclass MessageProvider, implement send(), register it in PROVIDERS, set LARDER_MESSAGE_PROVIDER.
Only text guests who gave you their number for this purpose.
"""
from django.conf import settings

from .models import Message


class MessageProvider:
    key = ""

    def send(self, to: str, body: str) -> tuple[str, str]:
        """Return (status, provider_ref)."""
        raise NotImplementedError


class LogProvider(MessageProvider):
    key = "log"

    def send(self, to, body):
        return "logged", ""


PROVIDERS = {LogProvider.key: LogProvider}


def send(location, to: str, body: str) -> Message:
    provider = PROVIDERS.get(settings.LARDER_MESSAGE_PROVIDER, LogProvider)()
    try:
        status, ref = provider.send(to, body)
    except Exception as exc:  # a failed text must never block seating a table
        status, ref = "failed", str(exc)[:120]
    return Message.objects.create(location=location, to=to, body=body[:480], provider=provider.key, status=status, provider_ref=ref)
