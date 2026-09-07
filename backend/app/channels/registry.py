"""Maps a Channel to its adapter instance. The worker looks up the adapter
by channel rather than hardcoding which one to use.
"""

from app.channels.base import Channel, ChannelAdapter
from app.channels.web import WebAdapter

_ADAPTERS: dict[Channel, ChannelAdapter] = {}


def get_adapter(channel: Channel | str) -> ChannelAdapter:
    channel = Channel(channel)
    if channel not in _ADAPTERS:
        if channel == Channel.web:
            _ADAPTERS[channel] = WebAdapter()
        else:
            raise NotImplementedError(f"no adapter registered for channel {channel!r} yet")
    return _ADAPTERS[channel]
