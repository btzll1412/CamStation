"""
Core services for CamStation.

Provides async-first architecture for:
- Stream management with lazy loading
- Connection pooling
- Playback control with smooth scrubbing
- Multi-protocol device management
"""

from .stream_manager import StreamManager
from .playback_controller import PlaybackController
from .device_manager import (
    DeviceManager, DeviceProtocol, DeviceInfo,
    DeviceCapabilities, ChannelInfo, UnifiedDeviceClient
)

__all__ = [
    'StreamManager',
    'PlaybackController',
    'DeviceManager',
    'DeviceProtocol',
    'DeviceInfo',
    'DeviceCapabilities',
    'ChannelInfo',
    'UnifiedDeviceClient'
]
