"""
ISAPI client for communicating with Hikvision devices.

ISAPI (Intelligent Security API) is Hikvision's HTTP-based API for device
configuration, event retrieval, and control.
"""

import requests
from requests.auth import HTTPDigestAuth
import xmltodict
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ISAPIClient:
    """Client for Hikvision ISAPI communication."""
    
    def __init__(self, ip: str, port: int, username: str, password: str, timeout: int = 10):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        
        self.base_url = f"http://{ip}:{port}"
        self.auth = HTTPDigestAuth(username, password)
        self.session = requests.Session()
        self.session.auth = self.auth
    
    def _request(self, method: str, endpoint: str, data: Optional[str] = None, 
                 params: Optional[Dict] = None) -> Optional[Dict]:
        """Make an ISAPI request."""
        url = f"{self.base_url}{endpoint}"
        
        headers = {"Content-Type": "application/xml"} if data else {}
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                data=data,
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 401:
                logger.error("Authentication failed")
                return None
            
            response.raise_for_status()
            
            # Parse XML response
            if response.content:
                return xmltodict.parse(response.content)
            return {}
            
        except requests.exceptions.Timeout:
            logger.error(f"Request timeout: {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return None
    
    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make a GET request."""
        return self._request("GET", endpoint, params=params)
    
    def _put(self, endpoint: str, data: str) -> Optional[Dict]:
        """Make a PUT request."""
        return self._request("PUT", endpoint, data=data)
    
    def _post(self, endpoint: str, data: str) -> Optional[Dict]:
        """Make a POST request."""
        return self._request("POST", endpoint, data=data)
    
    # === Device Information ===
    
    def get_device_info(self) -> Optional[Dict]:
        """Get basic device information."""
        response = self._get("/ISAPI/System/deviceInfo")
        if not response:
            return None
        
        info = response.get("DeviceInfo", {})
        return {
            "name": info.get("deviceName", "Unknown"),
            "model": info.get("model", "Unknown"),
            "serial_number": info.get("serialNumber", ""),
            "mac_address": info.get("macAddress", ""),
            "firmware_version": info.get("firmwareVersion", ""),
            "device_type": info.get("deviceType", "unknown"),
            "channel_count": int(info.get("channelNumber", 1))
        }
    
    def get_device_status(self) -> Optional[Dict]:
        """Get device status information."""
        response = self._get("/ISAPI/System/status")
        if not response:
            return None
        
        status = response.get("DeviceStatus", {})
        return {
            "cpu_usage": status.get("CPUList", {}).get("CPU", {}).get("cpuUsage", 0),
            "memory_usage": status.get("MemoryList", {}).get("Memory", {}).get("memoryUsage", 0)
        }
    
    # === Channel Discovery ===
    
    def get_channels(self) -> List[Dict]:
        """Get all camera channels."""
        channels = []
        
        # Try streaming channels first (works for NVRs and cameras)
        response = self._get("/ISAPI/Streaming/channels")
        if response:
            channel_list = response.get("StreamingChannelList", {}).get("StreamingChannel", [])
            if isinstance(channel_list, dict):
                channel_list = [channel_list]
            
            for ch in channel_list:
                channel_id = ch.get("id", "101")
                # Channel ID format: XXYY where XX is channel, YY is stream (01=main, 02=sub)
                channel_num = int(channel_id[:len(channel_id)-2]) if len(channel_id) > 2 else int(channel_id)
                stream_type = channel_id[-2:] if len(channel_id) > 2 else "01"
                
                if stream_type == "01":  # Main stream only
                    channels.append({
                        "channel_number": channel_num,
                        "name": ch.get("channelName", f"Channel {channel_num}"),
                        "enabled": ch.get("enabled", "true") == "true",
                        "stream_id": channel_id
                    })
        
        # Also try input channels (for NVRs)
        response = self._get("/ISAPI/ContentMgmt/InputProxy/channels")
        if response:
            input_list = response.get("InputProxyChannelList", {}).get("InputProxyChannel", [])
            if isinstance(input_list, dict):
                input_list = [input_list]
            
            for inp in input_list:
                channel_num = int(inp.get("id", 1))
                existing = next((c for c in channels if c["channel_number"] == channel_num), None)
                
                if not existing:
                    channels.append({
                        "channel_number": channel_num,
                        "name": inp.get("name", f"Channel {channel_num}"),
                        "enabled": inp.get("enabled", "true") == "true",
                        "stream_id": f"{channel_num}01"
                    })
        
        return channels
    
    def get_channel_capabilities(self, channel: int) -> Optional[Dict]:
        """Get capabilities for a specific channel."""
        response = self._get(f"/ISAPI/Streaming/channels/{channel}01/capabilities")
        if not response:
            return None
        
        caps = response.get("StreamingChannel", {})
        video = caps.get("Video", {})
        
        return {
            "has_audio": caps.get("Audio", {}).get("enabled", "false") == "true",
            "max_resolution": f"{video.get('videoResolutionWidth', 0)}x{video.get('videoResolutionHeight', 0)}",
            "codec": video.get("videoCodecType", "unknown")
        }
    
    # === PTZ Control ===
    
    def ptz_move(self, channel: int, pan: int = 0, tilt: int = 0, zoom: int = 0):
        """
        Send PTZ continuous move command.
        
        Args:
            channel: Camera channel number
            pan: -100 to 100 (negative=left, positive=right, 0=stop)
            tilt: -100 to 100 (negative=down, positive=up, 0=stop)
            zoom: -100 to 100 (negative=wide, positive=tele, 0=stop)
        """
        data = f"""<?xml version="1.0" encoding="UTF-8"?>
        <PTZData>
            <pan>{pan}</pan>
            <tilt>{tilt}</tilt>
            <zoom>{zoom}</zoom>
        </PTZData>"""
        
        return self._put(f"/ISAPI/PTZCtrl/channels/{channel}/continuous", data)
    
    def ptz_stop(self, channel: int):
        """Stop PTZ movement."""
        return self.ptz_move(channel, 0, 0, 0)
    
    def ptz_goto_preset(self, channel: int, preset: int):
        """Go to a PTZ preset."""
        data = f"""<?xml version="1.0" encoding="UTF-8"?>
        <PTZPreset>
            <id>{preset}</id>
        </PTZPreset>"""
        
        return self._put(f"/ISAPI/PTZCtrl/channels/{channel}/presets/{preset}/goto", data)
    
    # === Recording Search ===
    
    def search_recordings(self, channel: int, start_time: datetime, 
                         end_time: datetime, record_type: str = "all") -> List[Dict]:
        """
        Search for recordings.
        
        Args:
            channel: Camera channel number
            start_time: Search start time
            end_time: Search end time
            record_type: all, motion, alarm, manual
        """
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        track_id = f"{channel}01"  # Main stream track
        
        data = f"""<?xml version="1.0" encoding="UTF-8"?>
        <CMSearchDescription>
            <searchID>1</searchID>
            <trackList>
                <trackID>{track_id}</trackID>
            </trackList>
            <timeSpanList>
                <timeSpan>
                    <startTime>{start_str}</startTime>
                    <endTime>{end_str}</endTime>
                </timeSpan>
            </timeSpanList>
            <maxResults>100</maxResults>
            <searchResultPostion>0</searchResultPostion>
            <metadataList>
                <metadataDescriptor>//recordType.meta.std-cgi.com</metadataDescriptor>
            </metadataList>
        </CMSearchDescription>"""
        
        response = self._post("/ISAPI/ContentMgmt/search", data)
        if not response:
            return []
        
        results = []
        matches = response.get("CMSearchResult", {}).get("matchList", {}).get("searchMatchItem", [])
        
        if isinstance(matches, dict):
            matches = [matches]
        
        for match in matches:
            timespan = match.get("timeSpan", {})
            results.append({
                "start_time": timespan.get("startTime"),
                "end_time": timespan.get("endTime"),
                "source_id": match.get("sourceID"),
                "track_id": match.get("trackID"),
                "playback_uri": match.get("mediaSegmentDescriptor", {}).get("playbackURI")
            })
        
        return results
    
    # === Event Search ===
    
    def search_motion_events(self, channel: int, start_time: datetime, 
                            end_time: datetime) -> List[Dict]:
        """Search for motion detection events."""
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        data = f"""<?xml version="1.0" encoding="UTF-8"?>
        <CMSearchDescription>
            <searchID>2</searchID>
            <trackList>
                <trackID>{channel}01</trackID>
            </trackList>
            <timeSpanList>
                <timeSpan>
                    <startTime>{start_str}</startTime>
                    <endTime>{end_str}</endTime>
                </timeSpan>
            </timeSpanList>
            <contentTypeList>
                <contentType>metadata</contentType>
            </contentTypeList>
            <maxResults>100</maxResults>
            <metadataList>
                <metadataDescriptor>//recordType.meta.std-cgi.com/VMD</metadataDescriptor>
            </metadataList>
        </CMSearchDescription>"""
        
        response = self._post("/ISAPI/ContentMgmt/search", data)
        if not response:
            return []
        
        results = []
        matches = response.get("CMSearchResult", {}).get("matchList", {}).get("searchMatchItem", [])
        
        if isinstance(matches, dict):
            matches = [matches]
        
        for match in matches:
            timespan = match.get("timeSpan", {})
            results.append({
                "start_time": timespan.get("startTime"),
                "end_time": timespan.get("endTime"),
                "event_type": "motion"
            })
        
        return results
    
    # === LPR (License Plate Recognition) ===
    
    def search_lpr_events(self, start_time: datetime, end_time: datetime,
                         plate_number: Optional[str] = None) -> List[Dict]:
        """
        Search for LPR (license plate recognition) events.
        
        Args:
            start_time: Search start time
            end_time: Search end time
            plate_number: Optional plate number to filter (supports wildcards)
        """
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        plate_filter = ""
        if plate_number:
            plate_filter = f"<plateNumber>{plate_number}</plateNumber>"
        
        data = f"""<?xml version="1.0" encoding="UTF-8"?>
        <AfterTime>
            <picTime>{start_str}</picTime>
        </AfterTime>"""
        
        # Try traffic data endpoint
        response = self._post("/ISAPI/Traffic/ContentMgmt/search", data)
        
        if not response:
            # Try alternative LPR endpoint
            data = f"""<?xml version="1.0" encoding="UTF-8"?>
            <searchDescription>
                <searchID>lpr_search</searchID>
                <timeSpanList>
                    <timeSpan>
                        <startTime>{start_str}</startTime>
                        <endTime>{end_str}</endTime>
                    </timeSpan>
                </timeSpanList>
                {plate_filter}
                <maxResults>100</maxResults>
            </searchDescription>"""
            
            response = self._post("/ISAPI/Traffic/channels/1/vehicleDetect/plates", data)
        
        if not response:
            return []
        
        results = []
        # Parse response based on device type
        plates = response.get("Plates", {}).get("Plate", [])
        if isinstance(plates, dict):
            plates = [plates]
        
        for plate in plates:
            results.append({
                "plate_number": plate.get("plateNumber", ""),
                "timestamp": plate.get("capTime", ""),
                "confidence": float(plate.get("confidence", 0)),
                "plate_color": plate.get("plateColor", ""),
                "vehicle_color": plate.get("vehicleColor", ""),
                "vehicle_type": plate.get("vehicleType", ""),
                "direction": plate.get("direction", ""),
                "picture_url": plate.get("pictureURL", "")
            })
        
        return results
    
    # === Snapshot ===
    
    def get_snapshot(self, channel: int) -> Optional[bytes]:
        """Get a snapshot image from a channel."""
        url = f"{self.base_url}/ISAPI/Streaming/channels/{channel}01/picture"
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Failed to get snapshot: {e}")
            return None
    
    # === Configuration ===
    
    def get_video_settings(self, channel: int) -> Optional[Dict]:
        """Get video settings for a channel."""
        response = self._get(f"/ISAPI/Image/channels/{channel}")
        if not response:
            return None
        
        settings = response.get("ImageChannel", {})
        return {
            "brightness": int(settings.get("brightness", 50)),
            "contrast": int(settings.get("contrast", 50)),
            "saturation": int(settings.get("saturation", 50)),
            "sharpness": int(settings.get("sharpness", 50))
        }
    
    def set_video_settings(self, channel: int, brightness: int = None, 
                          contrast: int = None, saturation: int = None,
                          sharpness: int = None) -> bool:
        """Set video settings for a channel."""
        # Get current settings first
        current = self.get_video_settings(channel)
        if not current:
            return False
        
        # Update with new values
        if brightness is not None:
            current["brightness"] = brightness
        if contrast is not None:
            current["contrast"] = contrast
        if saturation is not None:
            current["saturation"] = saturation
        if sharpness is not None:
            current["sharpness"] = sharpness
        
        data = f"""<?xml version="1.0" encoding="UTF-8"?>
        <ImageChannel>
            <brightness>{current['brightness']}</brightness>
            <contrast>{current['contrast']}</contrast>
            <saturation>{current['saturation']}</saturation>
            <sharpness>{current['sharpness']}</sharpness>
        </ImageChannel>"""
        
        response = self._put(f"/ISAPI/Image/channels/{channel}", data)
        return response is not None
    
    def close(self):
        """Close the session."""
        self.session.close()
