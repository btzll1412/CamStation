"""
Core services for CamStation.

Provides async-first architecture for:
- Stream management with lazy loading
- Connection pooling
- Playback control with smooth scrubbing
"""

from .stream_manager import StreamManager
from .playback_controller import PlaybackController

__all__ = ['StreamManager', 'PlaybackController']
