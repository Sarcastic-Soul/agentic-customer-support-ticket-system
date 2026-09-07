"""Maps a Channel to its adapter instance. The worker looks up the adapter
by channel rather than hardcoding which one to use.
"""

from app.channels.base import Channel, ChannelAdapter
from app.channels.email import EmailAdapter
from app.channels.web import WebAdapter
from app.channels.whatsapp import WhatsAppAdapter

_ADAPTERS: dict[Channel, ChannelAdapter] = {}


def get_adapter(channel: Channel | str) -> ChannelAdapter:
    channel = Channel(channel)
    if channel not in _ADAPTERS:
        if channel == Channel.web:
            _ADAPTERS[channel] = WebAdapter()
        elif channel == Channel.whatsapp:
            _ADAPTERS[channel] = WhatsAppAdapter()
        elif channel == Channel.email:
            _ADAPTERS[channel] = EmailAdapter()
        else:
            raise NotImplementedError(f"no adapter registered for channel {channel!r} yet")
    return _ADAPTERS[channel]
