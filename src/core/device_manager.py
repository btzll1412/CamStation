"""
Unified device manager for multi-protocol camera support.

Supports:
- Hikvision (ISAPI) - Full features including LPR
- ONVIF - Any compatible camera
- Generic RTSP - Basic streaming only
"""

import logging
from typing import Dict, List, Optional, Callable, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor, Future

from api.isapi_client import ISAPIClient
from api.onvif_client import ONVIFClient, ONVIFDiscovery, DiscoveredDevice, test_onvif_connection

logger = logging.getLogger(__name__)


class DeviceProtocol(Enum):
    """Supported device protocols."""
    HIKVISION = "hikvision"  # Hikvision ISAPI
    ONVIF = "onvif"          # ONVIF standard
    RTSP = "rtsp"            # Generic RTSP only
    AUTO = "auto"            # Auto-detect


@dataclass
class DeviceCapabilities:
    """Device capabilities."""
    live_view: bool = True
    playback: bool = False
    ptz: bool = False
    audio: bool = False
    lpr: bool = False
    motion_detection: bool = False
    line_crossing: bool = False
    intrusion: bool = False
    events: bool = False


@dataclass
class ChannelInfo:
    """Information about a camera channel."""
    channel_number: int
    name: str
    rtsp_url: str
    rtsp_url_sub: Optional[str] = None
    snapshot_url: Optional[str] = None
    has_ptz: bool = False
    has_audio: bool = False
    has_lpr: bool = False
    resolution: Optional[str] = None
    encoding: str = "H264"
    is_online: bool = True


@dataclass
class DeviceInfo:
    """Unified device information."""
    protocol: DeviceProtocol
    ip_address: str
    port: int
    username: str
    password: str
    name: str
    model: str
    manufacturer: str
    serial_number: str
    firmware_version: str
    channels: List[ChannelInfo]
    capabilities: DeviceCapabilities
    rtsp_port: int = 554
    raw_info: Optional[Dict] = None  # Protocol-specific info


class UnifiedDeviceClient:
    """
    Unified client that wraps protocol-specific clients.

    Provides a common interface regardless of underlying protocol.
    """

    def __init__(self, device_info: DeviceInfo):
        self.device_info = device_info
        self._hikvision_client: Optional[ISAPIClient] = None
        self._onvif_client: Optional[ONVIFClient] = None
        self._connected = False

    def connect(self) -> bool:
        """Connect to the device using appropriate protocol."""
        try:
            if self.device_info.protocol == DeviceProtocol.HIKVISION:
                self._hikvision_client = ISAPIClient(
                    self.device_info.ip_address,
                    self.device_info.port,
                    self.device_info.username,
                    self.device_info.password
                )
                # Test connection
                info = self._hikvision_client.get_device_info()
                self._connected = info is not None

            elif self.device_info.protocol == DeviceProtocol.ONVIF:
                self._onvif_client = ONVIFClient(
                    self.device_info.ip_address,
                    self.device_info.port,
                    self.device_info.username,
                    self.device_info.password
                )
                self._connected = self._onvif_client.connect()

            elif self.device_info.protocol == DeviceProtocol.RTSP:
                # RTSP-only devices don't have a management connection
                self._connected = True

            return self._connected

        except Exception as e:
            logger.error(f"Failed to connect to device: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from the device."""
        if self._hikvision_client:
            self._hikvision_client.close()
            self._hikvision_client = None

        if self._onvif_client:
            self._onvif_client.disconnect()
            self._onvif_client = None

        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # === PTZ Control ===

    def ptz_move(self, channel: int, pan: float, tilt: float, zoom: float) -> bool:
        """
        Move PTZ camera.

        Args:
            channel: Channel number
            pan: -1.0 to 1.0 (or -100 to 100 for Hikvision)
            tilt: -1.0 to 1.0
            zoom: -1.0 to 1.0
        """
        if self._hikvision_client:
            # Hikvision uses -100 to 100 scale
            return self._hikvision_client.ptz_move(
                channel,
                int(pan * 100),
                int(tilt * 100),
                int(zoom * 100)
            ) is not None

        elif self._onvif_client:
            # Get profile token for channel
            profiles = self._onvif_client.get_profiles()
            if channel <= len(profiles):
                return self._onvif_client.ptz_move(
                    profiles[channel - 1].token,
                    pan, tilt, zoom
                )

        return False

    def ptz_stop(self, channel: int) -> bool:
        """Stop PTZ movement."""
        if self._hikvision_client:
            return self._hikvision_client.ptz_stop(channel) is not None

        elif self._onvif_client:
            profiles = self._onvif_client.get_profiles()
            if channel <= len(profiles):
                return self._onvif_client.ptz_stop(profiles[channel - 1].token)

        return False

    def ptz_goto_preset(self, channel: int, preset: int) -> bool:
        """Go to PTZ preset."""
        if self._hikvision_client:
            return self._hikvision_client.ptz_goto_preset(channel, preset) is not None

        elif self._onvif_client:
            profiles = self._onvif_client.get_profiles()
            if channel <= len(profiles):
                presets = self._onvif_client.get_ptz_presets(profiles[channel - 1].token)
                if preset <= len(presets):
                    return self._onvif_client.ptz_goto_preset(
                        profiles[channel - 1].token,
                        presets[preset - 1]['token']
                    )

        return False

    # === Recording Search ===

    def search_recordings(self, channel: int, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Search for recordings."""
        if self._hikvision_client:
            return self._hikvision_client.search_recordings(channel, start_time, end_time)

        elif self._onvif_client:
            return self._onvif_client.search_recordings(start_time, end_time)

        return []

    # === Event Search ===

    def search_motion_events(self, channel: int, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Search for motion events."""
        if self._hikvision_client:
            return self._hikvision_client.search_motion_events(channel, start_time, end_time)

        return []

    def search_lpr_events(self, start_time: datetime, end_time: datetime,
                          plate_number: Optional[str] = None) -> List[Dict]:
        """Search for LPR events (Hikvision only)."""
        if self._hikvision_client:
            return self._hikvision_client.search_lpr_events(start_time, end_time, plate_number)

        return []

    # === Snapshot ===

    def get_snapshot(self, channel: int) -> Optional[bytes]:
        """Get snapshot from camera."""
        if self._hikvision_client:
            return self._hikvision_client.get_snapshot(channel)

        # For ONVIF, would need to fetch from snapshot URL
        return None


class DeviceManager:
    """
    Manages multiple devices with different protocols.

    Features:
    - Auto-detection of device protocol
    - Network discovery (ONVIF + Hikvision)
    - Connection pooling
    - Health monitoring
    """

    def __init__(self):
        self._devices: Dict[str, UnifiedDeviceClient] = {}  # device_id -> client
        self._device_info: Dict[str, DeviceInfo] = {}  # device_id -> info
        self._executor = ThreadPoolExecutor(max_workers=8)
        self._discovery = ONVIFDiscovery()

    def add_device(self, device_info: DeviceInfo) -> Tuple[bool, str]:
        """
        Add a device to the manager.

        Returns:
            Tuple of (success, message)
        """
        device_id = f"{device_info.ip_address}:{device_info.port}"

        if device_id in self._devices:
            return False, "Device already exists"

        client = UnifiedDeviceClient(device_info)
        if not client.connect():
            return False, "Failed to connect to device"

        self._devices[device_id] = client
        self._device_info[device_id] = device_info

        return True, f"Added device: {device_info.name}"

    def remove_device(self, device_id: str):
        """Remove a device from the manager."""
        if device_id in self._devices:
            self._devices[device_id].disconnect()
            del self._devices[device_id]
            del self._device_info[device_id]

    def get_device(self, device_id: str) -> Optional[UnifiedDeviceClient]:
        """Get a device client by ID."""
        return self._devices.get(device_id)

    def get_device_info(self, device_id: str) -> Optional[DeviceInfo]:
        """Get device info by ID."""
        return self._device_info.get(device_id)

    def get_all_devices(self) -> List[DeviceInfo]:
        """Get all device info."""
        return list(self._device_info.values())

    # === Device Discovery ===

    def discover_devices(self, timeout: float = 5.0,
                        on_device_found: Optional[Callable] = None,
                        on_complete: Optional[Callable] = None):
        """
        Discover devices on the network.

        Args:
            timeout: Discovery timeout in seconds
            on_device_found: Callback for each device found
            on_complete: Callback when discovery completes
        """
        def _discovery_callback(device: DiscoveredDevice):
            if on_device_found:
                on_device_found(device)

        def _complete_callback(devices: List[DiscoveredDevice]):
            if on_complete:
                on_complete(devices)

        self._discovery.discover_async(timeout, _discovery_callback, _complete_callback)

    def stop_discovery(self):
        """Stop ongoing device discovery."""
        self._discovery.stop()

    # === Auto-Detection ===

    def detect_device(self, ip: str, port: int, username: str, password: str,
                     on_progress: Optional[Callable] = None) -> Tuple[Optional[DeviceInfo], str]:
        """
        Auto-detect device type and get info.

        Args:
            ip: Device IP address
            port: Device port
            username: Login username
            password: Login password
            on_progress: Progress callback (message: str)

        Returns:
            Tuple of (DeviceInfo or None, status_message)
        """
        if on_progress:
            on_progress("Detecting device type...")

        # Try Hikvision first (fastest)
        if on_progress:
            on_progress("Trying Hikvision ISAPI...")

        hik_info = self._try_hikvision(ip, port, username, password)
        if hik_info:
            return hik_info, "Detected Hikvision device"

        # Try ONVIF
        if on_progress:
            on_progress("Trying ONVIF...")

        onvif_info = self._try_onvif(ip, port, username, password)
        if onvif_info:
            return onvif_info, "Detected ONVIF device"

        # Try generic RTSP
        if on_progress:
            on_progress("Trying RTSP...")

        rtsp_info = self._try_rtsp(ip, port, username, password)
        if rtsp_info:
            return rtsp_info, "Detected RTSP stream"

        return None, "Failed to detect device type"

    def _try_hikvision(self, ip: str, port: int, username: str, password: str) -> Optional[DeviceInfo]:
        """Try to connect as Hikvision device."""
        try:
            client = ISAPIClient(ip, port, username, password, timeout=5)
            info = client.get_device_info()

            if not info:
                return None

            # Get channels
            channels_data = client.get_channels()
            channels = []

            # Detect capabilities
            has_lpr = False
            try:
                # Check if device supports LPR
                status = client.get_device_status()
                # LPR devices typically have specific capabilities
            except Exception:
                pass

            # Build RTSP base URL
            rtsp_base = f"rtsp://{username}:{password}@{ip}:554"

            for ch_data in channels_data:
                ch_num = ch_data.get('channel_number', 1)

                # Get channel capabilities
                caps = client.get_channel_capabilities(ch_num) or {}

                channels.append(ChannelInfo(
                    channel_number=ch_num,
                    name=ch_data.get('name', f"Channel {ch_num}"),
                    rtsp_url=f"{rtsp_base}/Streaming/Channels/{ch_num}01",
                    rtsp_url_sub=f"{rtsp_base}/Streaming/Channels/{ch_num}02",
                    snapshot_url=f"http://{ip}:{port}/ISAPI/Streaming/channels/{ch_num}01/picture",
                    has_ptz=False,  # Would need to check
                    has_audio=caps.get('has_audio', False),
                    resolution=caps.get('max_resolution'),
                    is_online=ch_data.get('enabled', True)
                ))

            client.close()

            return DeviceInfo(
                protocol=DeviceProtocol.HIKVISION,
                ip_address=ip,
                port=port,
                username=username,
                password=password,
                name=info.get('name', 'Hikvision Device'),
                model=info.get('model', 'Unknown'),
                manufacturer='Hikvision',
                serial_number=info.get('serial_number', ''),
                firmware_version=info.get('firmware_version', ''),
                channels=channels,
                capabilities=DeviceCapabilities(
                    live_view=True,
                    playback=True,
                    ptz=True,  # Most Hikvision support PTZ control
                    audio=True,
                    lpr=has_lpr,
                    motion_detection=True,
                    events=True
                ),
                rtsp_port=554,
                raw_info=info
            )

        except Exception as e:
            logger.debug(f"Hikvision detection failed: {e}")
            return None

    def _try_onvif(self, ip: str, port: int, username: str, password: str) -> Optional[DeviceInfo]:
        """Try to connect as ONVIF device."""
        try:
            client = ONVIFClient(ip, port, username, password)
            if not client.connect():
                return None

            onvif_info = client.get_device_info()
            if not onvif_info:
                client.disconnect()
                return None

            # Get profiles
            profiles = client.get_profiles()
            if not profiles:
                client.disconnect()
                return None

            # Build channels from profiles
            channels = []
            has_ptz = False
            has_audio = False

            for i, profile in enumerate(profiles):
                channels.append(ChannelInfo(
                    channel_number=i + 1,
                    name=profile.name,
                    rtsp_url=profile.stream_uri,
                    rtsp_url_sub=None,  # Would need to find sub-stream profile
                    snapshot_url=profile.snapshot_uri,
                    has_ptz=profile.has_ptz,
                    has_audio=profile.has_audio,
                    resolution=f"{profile.resolution[0]}x{profile.resolution[1]}",
                    encoding=profile.encoding,
                    is_online=True
                ))

                if profile.has_ptz:
                    has_ptz = True
                if profile.has_audio:
                    has_audio = True

            client.disconnect()

            return DeviceInfo(
                protocol=DeviceProtocol.ONVIF,
                ip_address=ip,
                port=port,
                username=username,
                password=password,
                name=f"{onvif_info.manufacturer} {onvif_info.model}",
                model=onvif_info.model,
                manufacturer=onvif_info.manufacturer,
                serial_number=onvif_info.serial_number,
                firmware_version=onvif_info.firmware_version,
                channels=channels,
                capabilities=DeviceCapabilities(
                    live_view=True,
                    playback=False,  # Depends on Profile G support
                    ptz=has_ptz,
                    audio=has_audio,
                    lpr=False,  # ONVIF doesn't have standard LPR
                    motion_detection=True,
                    events=True
                ),
                rtsp_port=554,
                raw_info={
                    'hardware_id': onvif_info.hardware_id,
                    'scopes': onvif_info.scopes
                }
            )

        except Exception as e:
            logger.debug(f"ONVIF detection failed: {e}")
            return None

    def _try_rtsp(self, ip: str, port: int, username: str, password: str) -> Optional[DeviceInfo]:
        """Try to connect as generic RTSP device."""
        import cv2

        # Common RTSP URL patterns to try
        rtsp_patterns = [
            f"rtsp://{username}:{password}@{ip}:554/stream1",
            f"rtsp://{username}:{password}@{ip}:554/live",
            f"rtsp://{username}:{password}@{ip}:554/cam/realmonitor",
            f"rtsp://{username}:{password}@{ip}:554/h264Preview_01_main",
            f"rtsp://{username}:{password}@{ip}:554/Streaming/Channels/101",
        ]

        for rtsp_url in rtsp_patterns:
            try:
                cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000)

                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        # Get resolution
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

                        cap.release()

                        return DeviceInfo(
                            protocol=DeviceProtocol.RTSP,
                            ip_address=ip,
                            port=554,
                            username=username,
                            password=password,
                            name=f"RTSP Camera ({ip})",
                            model="Generic RTSP",
                            manufacturer="Unknown",
                            serial_number="",
                            firmware_version="",
                            channels=[ChannelInfo(
                                channel_number=1,
                                name="Main Stream",
                                rtsp_url=rtsp_url,
                                resolution=f"{width}x{height}",
                                is_online=True
                            )],
                            capabilities=DeviceCapabilities(
                                live_view=True,
                                playback=False,
                                ptz=False,
                                audio=False,
                                lpr=False,
                                motion_detection=False,
                                events=False
                            ),
                            rtsp_port=554
                        )

                cap.release()

            except Exception as e:
                logger.debug(f"RTSP pattern {rtsp_url} failed: {e}")
                continue

        return None

    def shutdown(self):
        """Shutdown the device manager."""
        self._discovery.stop()

        for client in self._devices.values():
            client.disconnect()

        self._devices.clear()
        self._device_info.clear()
        self._executor.shutdown(wait=False)
