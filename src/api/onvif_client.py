"""
ONVIF client for communicating with ONVIF-compatible cameras.

Supports:
- Device discovery (WS-Discovery)
- Profile S (Live streaming)
- Profile T (PTZ control)
- Profile G (Recording/playback)
- Event subscription
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import threading

logger = logging.getLogger(__name__)

# Try to import ONVIF libraries
try:
    from onvif import ONVIFCamera, ONVIFError
    ONVIF_AVAILABLE = True
except ImportError:
    ONVIF_AVAILABLE = False
    logger.warning("ONVIF library not available. Install with: pip install onvif-zeep")

try:
    from wsdiscovery.discovery import ThreadedWSDiscovery
    from wsdiscovery import QName, Scope
    WSDISCOVERY_AVAILABLE = True
except ImportError:
    WSDISCOVERY_AVAILABLE = False
    logger.warning("WSDiscovery not available. Install with: pip install WSDiscovery")


@dataclass
class ONVIFDeviceInfo:
    """Information about an ONVIF device."""
    ip_address: str
    port: int
    manufacturer: str
    model: str
    firmware_version: str
    serial_number: str
    hardware_id: str
    scopes: List[str]


@dataclass
class ONVIFProfile:
    """ONVIF media profile."""
    token: str
    name: str
    stream_uri: str
    snapshot_uri: Optional[str]
    resolution: Tuple[int, int]
    encoding: str
    has_ptz: bool
    has_audio: bool


@dataclass
class DiscoveredDevice:
    """Device found via network discovery."""
    ip_address: str
    port: int
    device_type: str  # onvif, hikvision, dahua, etc.
    name: str
    scopes: List[str]
    xaddrs: List[str]


class ONVIFClient:
    """
    Client for ONVIF camera communication.

    Usage:
        client = ONVIFClient("192.168.1.100", 80, "admin", "password")
        if client.connect():
            info = client.get_device_info()
            profiles = client.get_profiles()
            stream_uri = client.get_stream_uri(profiles[0].token)
    """

    def __init__(self, ip: str, port: int, username: str, password: str):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password

        self._camera: Optional['ONVIFCamera'] = None
        self._device_service = None
        self._media_service = None
        self._ptz_service = None
        self._events_service = None
        self._recording_service = None

        self._profiles: List[ONVIFProfile] = []
        self._connected = False

    def connect(self) -> bool:
        """
        Connect to the ONVIF camera.

        Returns:
            True if connection successful
        """
        if not ONVIF_AVAILABLE:
            logger.error("ONVIF library not available")
            return False

        try:
            logger.info(f"Connecting to ONVIF device at {self.ip}:{self.port}")

            self._camera = ONVIFCamera(
                self.ip,
                self.port,
                self.username,
                self.password
            )

            # Get services
            self._device_service = self._camera.create_devicemgmt_service()
            self._media_service = self._camera.create_media_service()

            # Try to get PTZ service (may not be available)
            try:
                self._ptz_service = self._camera.create_ptz_service()
            except Exception:
                self._ptz_service = None
                logger.debug("PTZ service not available")

            # Try to get recording service (Profile G)
            try:
                self._recording_service = self._camera.create_recording_service()
            except Exception:
                self._recording_service = None
                logger.debug("Recording service not available")

            self._connected = True
            logger.info(f"Connected to ONVIF device at {self.ip}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to ONVIF device: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from the camera."""
        self._camera = None
        self._device_service = None
        self._media_service = None
        self._ptz_service = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_device_info(self) -> Optional[ONVIFDeviceInfo]:
        """Get device information."""
        if not self._connected or not self._device_service:
            return None

        try:
            info = self._device_service.GetDeviceInformation()

            # Get scopes
            scopes = []
            try:
                scope_response = self._device_service.GetScopes()
                scopes = [s.ScopeItem for s in scope_response if hasattr(s, 'ScopeItem')]
            except Exception:
                pass

            return ONVIFDeviceInfo(
                ip_address=self.ip,
                port=self.port,
                manufacturer=getattr(info, 'Manufacturer', 'Unknown'),
                model=getattr(info, 'Model', 'Unknown'),
                firmware_version=getattr(info, 'FirmwareVersion', ''),
                serial_number=getattr(info, 'SerialNumber', ''),
                hardware_id=getattr(info, 'HardwareId', ''),
                scopes=scopes
            )
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            return None

    def get_profiles(self) -> List[ONVIFProfile]:
        """Get media profiles."""
        if not self._connected or not self._media_service:
            return []

        try:
            profiles = self._media_service.GetProfiles()
            result = []

            for profile in profiles:
                token = profile.token
                name = getattr(profile, 'Name', token)

                # Get resolution
                resolution = (0, 0)
                encoding = "H264"
                if hasattr(profile, 'VideoEncoderConfiguration'):
                    vec = profile.VideoEncoderConfiguration
                    if hasattr(vec, 'Resolution'):
                        resolution = (
                            getattr(vec.Resolution, 'Width', 0),
                            getattr(vec.Resolution, 'Height', 0)
                        )
                    encoding = getattr(vec, 'Encoding', 'H264')

                # Check for PTZ
                has_ptz = hasattr(profile, 'PTZConfiguration') and profile.PTZConfiguration is not None

                # Check for audio
                has_audio = hasattr(profile, 'AudioEncoderConfiguration') and profile.AudioEncoderConfiguration is not None

                # Get stream URI
                stream_uri = self._get_stream_uri(token)

                # Get snapshot URI
                snapshot_uri = self._get_snapshot_uri(token)

                result.append(ONVIFProfile(
                    token=token,
                    name=name,
                    stream_uri=stream_uri or "",
                    snapshot_uri=snapshot_uri,
                    resolution=resolution,
                    encoding=encoding,
                    has_ptz=has_ptz,
                    has_audio=has_audio
                ))

            self._profiles = result
            return result

        except Exception as e:
            logger.error(f"Failed to get profiles: {e}")
            return []

    def _get_stream_uri(self, profile_token: str) -> Optional[str]:
        """Get RTSP stream URI for a profile."""
        if not self._media_service:
            return None

        try:
            stream_setup = self._media_service.create_type('GetStreamUri')
            stream_setup.ProfileToken = profile_token
            stream_setup.StreamSetup = {
                'Stream': 'RTP-Unicast',
                'Transport': {'Protocol': 'RTSP'}
            }

            response = self._media_service.GetStreamUri(stream_setup)
            uri = getattr(response, 'Uri', None)

            # Inject credentials into URI if not present
            if uri and '@' not in uri:
                uri = uri.replace('rtsp://', f'rtsp://{self.username}:{self.password}@')

            return uri

        except Exception as e:
            logger.error(f"Failed to get stream URI: {e}")
            return None

    def _get_snapshot_uri(self, profile_token: str) -> Optional[str]:
        """Get snapshot URI for a profile."""
        if not self._media_service:
            return None

        try:
            response = self._media_service.GetSnapshotUri({'ProfileToken': profile_token})
            return getattr(response, 'Uri', None)
        except Exception:
            return None

    def get_stream_uri(self, profile_token: str) -> Optional[str]:
        """Get stream URI for a specific profile."""
        return self._get_stream_uri(profile_token)

    # === PTZ Control ===

    def ptz_move(self, profile_token: str, pan: float = 0, tilt: float = 0, zoom: float = 0):
        """
        Continuous PTZ move.

        Args:
            profile_token: Media profile token
            pan: -1.0 to 1.0 (left to right)
            tilt: -1.0 to 1.0 (down to up)
            zoom: -1.0 to 1.0 (wide to tele)
        """
        if not self._ptz_service:
            logger.warning("PTZ service not available")
            return False

        try:
            request = self._ptz_service.create_type('ContinuousMove')
            request.ProfileToken = profile_token
            request.Velocity = {
                'PanTilt': {'x': pan, 'y': tilt},
                'Zoom': {'x': zoom}
            }

            self._ptz_service.ContinuousMove(request)
            return True

        except Exception as e:
            logger.error(f"PTZ move failed: {e}")
            return False

    def ptz_stop(self, profile_token: str):
        """Stop PTZ movement."""
        if not self._ptz_service:
            return False

        try:
            self._ptz_service.Stop({'ProfileToken': profile_token})
            return True
        except Exception as e:
            logger.error(f"PTZ stop failed: {e}")
            return False

    def ptz_goto_preset(self, profile_token: str, preset_token: str):
        """Go to a PTZ preset."""
        if not self._ptz_service:
            return False

        try:
            request = self._ptz_service.create_type('GotoPreset')
            request.ProfileToken = profile_token
            request.PresetToken = preset_token

            self._ptz_service.GotoPreset(request)
            return True

        except Exception as e:
            logger.error(f"PTZ goto preset failed: {e}")
            return False

    def get_ptz_presets(self, profile_token: str) -> List[Dict]:
        """Get PTZ presets."""
        if not self._ptz_service:
            return []

        try:
            presets = self._ptz_service.GetPresets({'ProfileToken': profile_token})
            return [
                {
                    'token': p.token,
                    'name': getattr(p, 'Name', p.token)
                }
                for p in presets
            ]
        except Exception as e:
            logger.error(f"Failed to get PTZ presets: {e}")
            return []

    # === Recording/Playback (Profile G) ===

    def get_recordings(self) -> List[Dict]:
        """Get available recordings."""
        if not self._recording_service:
            return []

        try:
            recordings = self._recording_service.GetRecordings()
            return [
                {
                    'token': r.RecordingToken,
                    'source': getattr(r, 'Source', {})
                }
                for r in recordings
            ]
        except Exception as e:
            logger.error(f"Failed to get recordings: {e}")
            return []

    def search_recordings(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Search for recordings in time range."""
        if not self._recording_service:
            # Fallback: Try to construct playback URL directly
            return []

        try:
            # This is simplified - actual implementation depends on device
            search_request = {
                'Scope': {
                    'IncludedSources': [],
                    'RecordingInformationFilter': ''
                },
                'StartPoint': start_time.isoformat() + 'Z',
                'EndPoint': end_time.isoformat() + 'Z',
                'MaxMatches': 100
            }

            results = self._recording_service.FindRecordings(search_request)
            return results

        except Exception as e:
            logger.error(f"Recording search failed: {e}")
            return []


class ONVIFDiscovery:
    """
    Network discovery for ONVIF devices.

    Uses WS-Discovery to find cameras on the local network.
    """

    def __init__(self):
        self._discovered_devices: List[DiscoveredDevice] = []
        self._discovery_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def discover(self, timeout: float = 5.0, callback=None) -> List[DiscoveredDevice]:
        """
        Discover ONVIF devices on the network.

        Args:
            timeout: Discovery timeout in seconds
            callback: Optional callback for each device found (device: DiscoveredDevice)

        Returns:
            List of discovered devices
        """
        if not WSDISCOVERY_AVAILABLE:
            logger.error("WSDiscovery not available")
            return []

        self._discovered_devices = []

        try:
            wsd = ThreadedWSDiscovery()
            wsd.start()

            # Search for ONVIF devices
            services = wsd.searchServices(
                types=[QName('http://www.onvif.org/ver10/network/wsdl', 'NetworkVideoTransmitter')],
                timeout=timeout
            )

            for service in services:
                try:
                    device = self._parse_service(service)
                    if device:
                        self._discovered_devices.append(device)
                        if callback:
                            callback(device)
                except Exception as e:
                    logger.debug(f"Failed to parse service: {e}")

            wsd.stop()

        except Exception as e:
            logger.error(f"Discovery failed: {e}")

        return self._discovered_devices

    def _parse_service(self, service) -> Optional[DiscoveredDevice]:
        """Parse a WS-Discovery service into a DiscoveredDevice."""
        try:
            xaddrs = service.getXAddrs()
            if not xaddrs:
                return None

            # Parse IP and port from first xaddr
            xaddr = xaddrs[0]
            # Format: http://192.168.1.100:80/onvif/device_service
            import re
            match = re.search(r'http[s]?://([^:/]+):?(\d+)?', xaddr)
            if not match:
                return None

            ip = match.group(1)
            port = int(match.group(2)) if match.group(2) else 80

            # Get scopes
            scopes = [str(s) for s in service.getScopes()]

            # Determine device type from scopes
            device_type = "onvif"
            name = "ONVIF Camera"

            for scope in scopes:
                scope_lower = scope.lower()
                if 'hikvision' in scope_lower:
                    device_type = "hikvision"
                elif 'dahua' in scope_lower:
                    device_type = "dahua"
                elif 'axis' in scope_lower:
                    device_type = "axis"

                # Try to get name from scope
                if 'name/' in scope_lower:
                    name = scope.split('/')[-1]

            return DiscoveredDevice(
                ip_address=ip,
                port=port,
                device_type=device_type,
                name=name,
                scopes=scopes,
                xaddrs=xaddrs
            )

        except Exception as e:
            logger.debug(f"Failed to parse service: {e}")
            return None

    def discover_async(self, timeout: float = 5.0, callback=None, on_complete=None):
        """
        Start asynchronous discovery.

        Args:
            timeout: Discovery timeout
            callback: Called for each device found
            on_complete: Called when discovery finishes
        """
        def _discover_thread():
            devices = self.discover(timeout, callback)
            if on_complete:
                on_complete(devices)

        self._stop_event.clear()
        self._discovery_thread = threading.Thread(target=_discover_thread, daemon=True)
        self._discovery_thread.start()

    def stop(self):
        """Stop ongoing discovery."""
        self._stop_event.set()
        if self._discovery_thread:
            self._discovery_thread.join(timeout=1.0)


def test_onvif_connection(ip: str, port: int, username: str, password: str) -> Tuple[bool, Optional[ONVIFDeviceInfo], str]:
    """
    Test ONVIF connection to a device.

    Returns:
        Tuple of (success, device_info, error_message)
    """
    client = ONVIFClient(ip, port, username, password)

    if not client.connect():
        return False, None, "Failed to connect to device"

    info = client.get_device_info()
    if not info:
        return False, None, "Connected but failed to get device info"

    profiles = client.get_profiles()
    if not profiles:
        return False, None, "Connected but no media profiles found"

    client.disconnect()
    return True, info, f"Found {len(profiles)} profile(s)"
