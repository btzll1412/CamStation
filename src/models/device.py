"""
Data models for devices and cameras.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class Camera:
    """Represents a single camera/channel."""
    
    id: int
    device_id: int
    channel_number: int
    name: str
    rtsp_url: str
    rtsp_url_sub: Optional[str] = None  # Sub-stream URL
    is_online: bool = True
    has_ptz: bool = False
    has_audio: bool = False
    has_lpr: bool = False
    resolution: Optional[str] = None
    
    # Configuration
    stream_type: str = "main"  # main, sub
    
    def get_stream_url(self, stream_type: str = "main") -> str:
        """Get the appropriate stream URL."""
        if stream_type == "sub" and self.rtsp_url_sub:
            return self.rtsp_url_sub
        return self.rtsp_url


@dataclass
class Device:
    """Represents an NVR or standalone IP camera."""
    
    id: int
    name: str
    ip_address: str
    port: int = 80
    rtsp_port: int = 554
    username: str = "admin"
    password: str = ""
    
    # Device info
    device_type: str = "unknown"  # nvr, ipcam
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    mac_address: Optional[str] = None
    
    # Status
    is_online: bool = False
    last_seen: Optional[datetime] = None
    
    # Capabilities
    has_lpr: bool = False
    max_channels: int = 1
    
    # Child cameras/channels
    cameras: List[Camera] = field(default_factory=list)
    
    def get_isapi_base_url(self) -> str:
        """Get the base URL for ISAPI requests."""
        return f"http://{self.ip_address}:{self.port}"
    
    def get_rtsp_base_url(self) -> str:
        """Get the base URL for RTSP streams."""
        return f"rtsp://{self.username}:{self.password}@{self.ip_address}:{self.rtsp_port}"


@dataclass
class LPREvent:
    """Represents a license plate recognition event."""
    
    id: int
    camera_id: int
    plate_number: str
    timestamp: datetime
    confidence: float
    plate_color: Optional[str] = None
    vehicle_color: Optional[str] = None
    vehicle_type: Optional[str] = None
    direction: Optional[str] = None  # in, out
    snapshot_path: Optional[str] = None
    plate_snapshot_path: Optional[str] = None


@dataclass 
class MotionEvent:
    """Represents a motion detection event."""
    
    id: int
    camera_id: int
    timestamp: datetime
    duration_seconds: float = 0
    region: Optional[str] = None
    snapshot_path: Optional[str] = None


@dataclass
class Recording:
    """Represents a recording segment."""
    
    camera_id: int
    start_time: datetime
    end_time: datetime
    file_size: int = 0
    record_type: str = "continuous"  # continuous, motion, alarm, manual
    
    def get_playback_url(self, device: Device, camera: Camera) -> str:
        """Generate RTSP playback URL for this recording."""
        # Format: rtsp://user:pass@ip:554/Streaming/tracks/CHANNEL?starttime=YYYYMMDDTHHMMSSZ
        start_str = self.start_time.strftime("%Y%m%dT%H%M%SZ")
        return (
            f"rtsp://{device.username}:{device.password}@"
            f"{device.ip_address}:{device.rtsp_port}/"
            f"Streaming/tracks/{camera.channel_number}01?starttime={start_str}"
        )
