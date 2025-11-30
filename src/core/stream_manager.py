"""
Stream manager for efficient camera streaming.

Handles:
- Lazy loading (only stream when visible)
- Stream pooling (limit concurrent streams)
- Automatic quality switching (sub-stream for grid, main for fullscreen)
- Graceful reconnection
"""

import cv2
import numpy as np
from threading import Thread, Event, Lock
from queue import Queue, Empty
from typing import Optional, Dict, Callable, Tuple
from dataclasses import dataclass
from collections import OrderedDict
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class StreamInfo:
    """Information about an active stream."""
    camera_id: int
    url: str
    is_sub_stream: bool
    last_frame_time: float = 0
    frame_count: int = 0
    fps: float = 0
    resolution: Tuple[int, int] = (0, 0)


class CameraStream:
    """
    Individual camera stream with optimized frame handling.

    Features:
    - Non-blocking frame capture
    - Automatic reconnection
    - Frame dropping under load
    - FPS calculation
    """

    def __init__(self, camera_id: int, url: str,
                 on_frame: Optional[Callable] = None,
                 on_status: Optional[Callable] = None):
        self.camera_id = camera_id
        self.url = url
        self.on_frame = on_frame
        self.on_status = on_status

        self._capture: Optional[cv2.VideoCapture] = None
        self._thread: Optional[Thread] = None
        self._stop_event = Event()
        self._connected = False
        self._last_frame: Optional[np.ndarray] = None
        self._last_frame_time: float = 0
        self._frame_lock = Lock()

        # Performance tracking
        self._frame_count = 0
        self._fps_start_time = time.time()
        self._current_fps = 0.0

        # Reconnection
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._base_reconnect_delay = 1.0

    def start(self):
        """Start the stream capture thread."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = Thread(target=self._capture_loop, daemon=True,
                             name=f"Stream-{self.camera_id}")
        self._thread.start()

    def stop(self):
        """Stop the stream gracefully."""
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

        if self._capture:
            self._capture.release()
            self._capture = None

        self._connected = False
        self._emit_status("disconnected")

    def get_frame(self) -> Optional[np.ndarray]:
        """Get the most recent frame (non-blocking)."""
        with self._frame_lock:
            return self._last_frame.copy() if self._last_frame is not None else None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def fps(self) -> float:
        return self._current_fps

    @property
    def resolution(self) -> Tuple[int, int]:
        if self._capture and self._capture.isOpened():
            w = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return (w, h)
        return (0, 0)

    def _capture_loop(self):
        """Main capture loop."""
        while not self._stop_event.is_set():
            # Try to connect
            if not self._connect():
                self._handle_reconnect()
                continue

            self._reconnect_attempts = 0
            self._emit_status("connected")

            # Capture frames
            while not self._stop_event.is_set():
                try:
                    ret, frame = self._capture.read()

                    if not ret:
                        logger.warning(f"Stream {self.camera_id}: Frame read failed")
                        self._connected = False
                        self._emit_status("reconnecting")
                        break

                    # Update frame
                    with self._frame_lock:
                        self._last_frame = frame
                        self._last_frame_time = time.time()

                    # Update FPS
                    self._frame_count += 1
                    elapsed = time.time() - self._fps_start_time
                    if elapsed >= 1.0:
                        self._current_fps = self._frame_count / elapsed
                        self._frame_count = 0
                        self._fps_start_time = time.time()

                    # Emit frame callback
                    if self.on_frame:
                        self.on_frame(self.camera_id, frame)

                except Exception as e:
                    logger.error(f"Stream {self.camera_id}: Capture error: {e}")
                    break

            # Cleanup for reconnect
            if self._capture:
                self._capture.release()
                self._capture = None

    def _connect(self) -> bool:
        """Connect to the RTSP stream."""
        try:
            self._emit_status("connecting")

            # Create capture with optimized settings
            self._capture = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)

            # Optimize for low latency
            self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not self._capture.isOpened():
                logger.error(f"Stream {self.camera_id}: Failed to open")
                return False

            # Test read
            ret, frame = self._capture.read()
            if not ret:
                logger.error(f"Stream {self.camera_id}: Test read failed")
                self._capture.release()
                return False

            # Store first frame
            with self._frame_lock:
                self._last_frame = frame
                self._last_frame_time = time.time()

            self._connected = True
            logger.info(f"Stream {self.camera_id}: Connected")
            return True

        except Exception as e:
            logger.error(f"Stream {self.camera_id}: Connect error: {e}")
            return False

    def _handle_reconnect(self):
        """Handle reconnection with exponential backoff."""
        if self._stop_event.is_set():
            return

        self._reconnect_attempts += 1

        if self._reconnect_attempts > self._max_reconnect_attempts:
            logger.error(f"Stream {self.camera_id}: Max reconnects reached")
            self._emit_status("failed")
            self._stop_event.wait(10.0)  # Wait before trying again
            self._reconnect_attempts = 0
            return

        # Exponential backoff
        delay = min(self._base_reconnect_delay * (2 ** (self._reconnect_attempts - 1)), 30.0)
        logger.info(f"Stream {self.camera_id}: Reconnect in {delay:.1f}s (attempt {self._reconnect_attempts})")
        self._stop_event.wait(delay)

    def _emit_status(self, status: str):
        """Emit status update."""
        if self.on_status:
            try:
                self.on_status(self.camera_id, status)
            except Exception:
                pass


class StreamManager:
    """
    Manages multiple camera streams efficiently.

    Features:
    - Limits concurrent streams (prevents resource exhaustion)
    - LRU eviction when limit reached
    - Stream reuse (don't restart if already active)
    - Quality switching (sub vs main stream)
    """

    def __init__(self, max_streams: int = 16):
        self.max_streams = max_streams
        self._streams: OrderedDict[int, CameraStream] = OrderedDict()
        self._lock = Lock()
        self._frame_callbacks: Dict[int, Callable] = {}
        self._status_callbacks: Dict[int, Callable] = {}

    def start_stream(self, camera_id: int, url: str,
                     use_sub_stream: bool = True,
                     on_frame: Optional[Callable] = None,
                     on_status: Optional[Callable] = None) -> bool:
        """
        Start streaming from a camera.

        Args:
            camera_id: Unique camera identifier
            url: RTSP URL (main or sub stream)
            use_sub_stream: If True, prefer sub-stream for lower bandwidth
            on_frame: Callback for new frames (camera_id, frame)
            on_status: Callback for status changes (camera_id, status)

        Returns:
            True if stream started successfully
        """
        with self._lock:
            # Check if already streaming
            if camera_id in self._streams:
                # Move to end (most recently used)
                self._streams.move_to_end(camera_id)
                return True

            # Evict oldest stream if at limit
            while len(self._streams) >= self.max_streams:
                oldest_id, oldest_stream = self._streams.popitem(last=False)
                logger.info(f"StreamManager: Evicting stream {oldest_id}")
                oldest_stream.stop()

            # Create and start new stream
            stream = CameraStream(
                camera_id=camera_id,
                url=url,
                on_frame=on_frame,
                on_status=on_status
            )

            self._streams[camera_id] = stream
            stream.start()

            return True

    def stop_stream(self, camera_id: int):
        """Stop a specific stream."""
        with self._lock:
            if camera_id in self._streams:
                self._streams[camera_id].stop()
                del self._streams[camera_id]

    def stop_all(self):
        """Stop all streams."""
        with self._lock:
            for stream in self._streams.values():
                stream.stop()
            self._streams.clear()

    def get_frame(self, camera_id: int) -> Optional[np.ndarray]:
        """Get the latest frame from a stream."""
        with self._lock:
            if camera_id in self._streams:
                return self._streams[camera_id].get_frame()
        return None

    def is_streaming(self, camera_id: int) -> bool:
        """Check if a camera is currently streaming."""
        with self._lock:
            return camera_id in self._streams

    def get_stream_info(self, camera_id: int) -> Optional[StreamInfo]:
        """Get information about a stream."""
        with self._lock:
            if camera_id in self._streams:
                stream = self._streams[camera_id]
                return StreamInfo(
                    camera_id=camera_id,
                    url=stream.url,
                    is_sub_stream='02' in stream.url,
                    last_frame_time=stream._last_frame_time,
                    frame_count=stream._frame_count,
                    fps=stream.fps,
                    resolution=stream.resolution
                )
        return None

    def get_active_count(self) -> int:
        """Get number of active streams."""
        with self._lock:
            return len(self._streams)

    def touch_stream(self, camera_id: int):
        """Mark a stream as recently used (prevents eviction)."""
        with self._lock:
            if camera_id in self._streams:
                self._streams.move_to_end(camera_id)
