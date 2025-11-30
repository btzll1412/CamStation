"""
Playback controller for smooth timeline scrubbing.

This is the core component for UniFi Protect-style smooth playback.

Features:
- Smooth scrubbing with frame caching
- Thumbnail generation for timeline hover
- Keyframe seeking for instant jumps
- Speed control (0.5x to 16x)
- Frame-by-frame stepping
"""

import cv2
import numpy as np
from threading import Thread, Event, Lock
from queue import Queue, PriorityQueue
from typing import Optional, Dict, List, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import OrderedDict
import logging
import time
import bisect

logger = logging.getLogger(__name__)


@dataclass
class TimelineSegment:
    """A segment of recording on the timeline."""
    start_time: datetime
    end_time: datetime
    event_type: str = "recording"  # recording, motion, line_crossing, intrusion, lpr


@dataclass
class CachedFrame:
    """A cached frame with timestamp."""
    timestamp: datetime
    frame: np.ndarray
    is_keyframe: bool = False


@dataclass(order=True)
class ThumbnailRequest:
    """Request for thumbnail generation."""
    priority: int
    timestamp: datetime = field(compare=False)
    callback: Callable = field(compare=False)


class FrameCache:
    """
    LRU cache for decoded frames.

    Enables smooth scrubbing by keeping recent frames in memory.
    """

    def __init__(self, max_frames: int = 300):  # ~10 seconds at 30fps
        self.max_frames = max_frames
        self._cache: OrderedDict[int, CachedFrame] = OrderedDict()  # timestamp_ms -> frame
        self._lock = Lock()

    def put(self, timestamp: datetime, frame: np.ndarray, is_keyframe: bool = False):
        """Add a frame to the cache."""
        ts_ms = int(timestamp.timestamp() * 1000)

        with self._lock:
            if ts_ms in self._cache:
                self._cache.move_to_end(ts_ms)
                return

            # Evict oldest if full
            while len(self._cache) >= self.max_frames:
                self._cache.popitem(last=False)

            self._cache[ts_ms] = CachedFrame(
                timestamp=timestamp,
                frame=frame.copy(),
                is_keyframe=is_keyframe
            )

    def get(self, timestamp: datetime) -> Optional[np.ndarray]:
        """Get a frame from cache."""
        ts_ms = int(timestamp.timestamp() * 1000)

        with self._lock:
            if ts_ms in self._cache:
                self._cache.move_to_end(ts_ms)
                return self._cache[ts_ms].frame.copy()
        return None

    def get_nearest(self, timestamp: datetime, max_delta_ms: int = 100) -> Optional[Tuple[datetime, np.ndarray]]:
        """Get the nearest cached frame within tolerance."""
        ts_ms = int(timestamp.timestamp() * 1000)

        with self._lock:
            if not self._cache:
                return None

            keys = list(self._cache.keys())
            idx = bisect.bisect_left(keys, ts_ms)

            candidates = []
            if idx > 0:
                candidates.append(keys[idx - 1])
            if idx < len(keys):
                candidates.append(keys[idx])

            for key in candidates:
                if abs(key - ts_ms) <= max_delta_ms:
                    cached = self._cache[key]
                    return (cached.timestamp, cached.frame.copy())

        return None

    def clear(self):
        """Clear the cache."""
        with self._lock:
            self._cache.clear()

    def get_range(self) -> Optional[Tuple[datetime, datetime]]:
        """Get the time range of cached frames."""
        with self._lock:
            if not self._cache:
                return None

            keys = list(self._cache.keys())
            start = datetime.fromtimestamp(keys[0] / 1000)
            end = datetime.fromtimestamp(keys[-1] / 1000)
            return (start, end)


class ThumbnailCache:
    """
    Cache for timeline thumbnails.

    Stores small preview images for timeline hover.
    """

    def __init__(self, max_thumbnails: int = 500, thumbnail_size: Tuple[int, int] = (160, 90)):
        self.max_thumbnails = max_thumbnails
        self.thumbnail_size = thumbnail_size
        self._cache: OrderedDict[int, np.ndarray] = OrderedDict()  # timestamp_ms -> thumbnail
        self._lock = Lock()

    def put(self, timestamp: datetime, frame: np.ndarray):
        """Add a thumbnail (will be resized)."""
        ts_ms = int(timestamp.timestamp() * 1000)

        # Resize to thumbnail
        thumbnail = cv2.resize(frame, self.thumbnail_size, interpolation=cv2.INTER_AREA)

        with self._lock:
            if ts_ms in self._cache:
                return

            while len(self._cache) >= self.max_thumbnails:
                self._cache.popitem(last=False)

            self._cache[ts_ms] = thumbnail

    def get(self, timestamp: datetime) -> Optional[np.ndarray]:
        """Get a thumbnail."""
        ts_ms = int(timestamp.timestamp() * 1000)

        with self._lock:
            if ts_ms in self._cache:
                return self._cache[ts_ms].copy()
        return None

    def get_nearest(self, timestamp: datetime, max_delta_ms: int = 5000) -> Optional[np.ndarray]:
        """Get the nearest thumbnail."""
        ts_ms = int(timestamp.timestamp() * 1000)

        with self._lock:
            if not self._cache:
                return None

            keys = list(self._cache.keys())
            idx = bisect.bisect_left(keys, ts_ms)

            best_key = None
            best_delta = float('inf')

            for i in [idx - 1, idx]:
                if 0 <= i < len(keys):
                    delta = abs(keys[i] - ts_ms)
                    if delta < best_delta and delta <= max_delta_ms:
                        best_delta = delta
                        best_key = keys[i]

            if best_key is not None:
                return self._cache[best_key].copy()

        return None


class PlaybackController:
    """
    Main playback controller for smooth timeline scrubbing.

    Usage:
        controller = PlaybackController()
        controller.load_recording(camera, device, start_time, end_time)
        controller.play()

        # Smooth scrubbing
        controller.seek(target_time)  # Instant jump with cached frames

        # Get current frame for display
        frame = controller.get_current_frame()
    """

    def __init__(self,
                 on_frame: Optional[Callable[[np.ndarray, datetime], None]] = None,
                 on_status: Optional[Callable[[str], None]] = None,
                 on_position: Optional[Callable[[datetime], None]] = None):
        """
        Initialize playback controller.

        Args:
            on_frame: Callback when new frame is ready (frame, timestamp)
            on_status: Callback for status changes ("playing", "paused", "buffering", etc.)
            on_position: Callback for position updates (current_time)
        """
        self.on_frame = on_frame
        self.on_status = on_status
        self.on_position = on_position

        # Playback state
        self._playing = False
        self._speed = 1.0
        self._current_time: Optional[datetime] = None
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None

        # Stream
        self._capture: Optional[cv2.VideoCapture] = None
        self._rtsp_url: Optional[str] = None
        self._stream_fps: float = 30.0

        # Caches
        self._frame_cache = FrameCache(max_frames=300)
        self._thumbnail_cache = ThumbnailCache(max_thumbnails=500)

        # Threading
        self._playback_thread: Optional[Thread] = None
        self._prefetch_thread: Optional[Thread] = None
        self._thumbnail_thread: Optional[Thread] = None
        self._stop_event = Event()
        self._seek_event = Event()
        self._seek_target: Optional[datetime] = None
        self._lock = Lock()

        # Current frame
        self._current_frame: Optional[np.ndarray] = None
        self._current_frame_time: Optional[datetime] = None

        # Timeline data
        self._segments: List[TimelineSegment] = []
        self._events: List[TimelineSegment] = []  # Motion, LPR events etc.

    def load_recording(self, rtsp_url: str, start_time: datetime, end_time: datetime,
                      segments: Optional[List[TimelineSegment]] = None,
                      events: Optional[List[TimelineSegment]] = None):
        """
        Load a recording for playback.

        Args:
            rtsp_url: Base RTSP URL for playback
            start_time: Recording start time
            end_time: Recording end time
            segments: List of recording segments
            events: List of motion/LPR events for timeline markers
        """
        self.stop()

        self._rtsp_url = rtsp_url
        self._start_time = start_time
        self._end_time = end_time
        self._current_time = start_time
        self._segments = segments or []
        self._events = events or []

        # Clear caches
        self._frame_cache.clear()
        self._thumbnail_cache.clear()

        # Start prefetch thread for thumbnails
        self._start_thumbnail_prefetch()

        self._emit_status("loaded")

    def play(self):
        """Start or resume playback."""
        if not self._rtsp_url:
            return

        if self._playing:
            return

        self._playing = True
        self._stop_event.clear()

        # Start playback thread
        self._playback_thread = Thread(target=self._playback_loop, daemon=True)
        self._playback_thread.start()

        self._emit_status("playing")

    def pause(self):
        """Pause playback."""
        self._playing = False
        self._emit_status("paused")

    def stop(self):
        """Stop playback completely."""
        self._playing = False
        self._stop_event.set()

        if self._playback_thread:
            self._playback_thread.join(timeout=2.0)
            self._playback_thread = None

        if self._prefetch_thread:
            self._prefetch_thread.join(timeout=2.0)
            self._prefetch_thread = None

        if self._capture:
            self._capture.release()
            self._capture = None

        self._emit_status("stopped")

    def seek(self, target_time: datetime):
        """
        Seek to a specific time.

        This is optimized for smooth scrubbing:
        1. First check frame cache for instant display
        2. If not cached, start background seek
        3. Show thumbnail while seeking
        """
        if not self._start_time or not self._end_time:
            return

        # Clamp to valid range
        target_time = max(self._start_time, min(target_time, self._end_time))

        with self._lock:
            self._current_time = target_time

        # Try cache first (instant)
        cached = self._frame_cache.get_nearest(target_time, max_delta_ms=100)
        if cached:
            ts, frame = cached
            self._current_frame = frame
            self._current_frame_time = ts
            self._emit_frame(frame, ts)
            self._emit_position(ts)
            return

        # Show thumbnail while seeking
        thumbnail = self._thumbnail_cache.get_nearest(target_time)
        if thumbnail:
            # Upscale thumbnail for display
            if self._current_frame is not None:
                h, w = self._current_frame.shape[:2]
                display_frame = cv2.resize(thumbnail, (w, h), interpolation=cv2.INTER_LINEAR)
            else:
                display_frame = thumbnail
            self._emit_frame(display_frame, target_time)

        # Trigger seek in playback thread
        self._seek_target = target_time
        self._seek_event.set()

        self._emit_position(target_time)

    def seek_relative(self, delta_seconds: float):
        """Seek relative to current position."""
        if self._current_time:
            target = self._current_time + timedelta(seconds=delta_seconds)
            self.seek(target)

    def set_speed(self, speed: float):
        """Set playback speed (0.5 to 16.0)."""
        self._speed = max(0.5, min(16.0, speed))

    def step_forward(self):
        """Step one frame forward."""
        if self._current_time and self._stream_fps > 0:
            delta = timedelta(seconds=1.0 / self._stream_fps)
            self.seek(self._current_time + delta)

    def step_backward(self):
        """Step one frame backward."""
        if self._current_time and self._stream_fps > 0:
            delta = timedelta(seconds=1.0 / self._stream_fps)
            self.seek(self._current_time - delta)

    def next_event(self):
        """Jump to next event."""
        if not self._current_time or not self._events:
            return

        for event in sorted(self._events, key=lambda e: e.start_time):
            if event.start_time > self._current_time:
                self.seek(event.start_time)
                return

    def prev_event(self):
        """Jump to previous event."""
        if not self._current_time or not self._events:
            return

        for event in sorted(self._events, key=lambda e: e.start_time, reverse=True):
            if event.start_time < self._current_time - timedelta(seconds=1):
                self.seek(event.start_time)
                return

    def get_current_frame(self) -> Optional[np.ndarray]:
        """Get the current frame for display."""
        return self._current_frame.copy() if self._current_frame is not None else None

    def get_current_time(self) -> Optional[datetime]:
        """Get current playback position."""
        return self._current_time

    def get_duration(self) -> Optional[timedelta]:
        """Get total duration."""
        if self._start_time and self._end_time:
            return self._end_time - self._start_time
        return None

    def get_progress(self) -> float:
        """Get playback progress (0.0 to 1.0)."""
        if not self._start_time or not self._end_time or not self._current_time:
            return 0.0

        total = (self._end_time - self._start_time).total_seconds()
        current = (self._current_time - self._start_time).total_seconds()

        if total <= 0:
            return 0.0

        return max(0.0, min(1.0, current / total))

    def get_thumbnail(self, timestamp: datetime) -> Optional[np.ndarray]:
        """Get thumbnail for timeline hover."""
        return self._thumbnail_cache.get_nearest(timestamp)

    def get_segments(self) -> List[TimelineSegment]:
        """Get recording segments for timeline display."""
        return self._segments.copy()

    def get_events(self) -> List[TimelineSegment]:
        """Get events for timeline markers."""
        return self._events.copy()

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def speed(self) -> float:
        return self._speed

    def _playback_loop(self):
        """Main playback loop."""
        while not self._stop_event.is_set():
            # Handle seek requests
            if self._seek_event.is_set():
                self._seek_event.clear()
                if self._seek_target:
                    self._do_seek(self._seek_target)
                    self._seek_target = None

            # If paused, just wait
            if not self._playing:
                time.sleep(0.01)
                continue

            # Read and display frames
            if self._capture and self._capture.isOpened():
                ret, frame = self._capture.read()

                if ret:
                    # Update current time
                    if self._current_time:
                        frame_delta = timedelta(seconds=1.0 / self._stream_fps * self._speed)
                        self._current_time += frame_delta

                        # Check end of recording
                        if self._end_time and self._current_time >= self._end_time:
                            self._current_time = self._end_time
                            self._playing = False
                            self._emit_status("ended")
                            continue

                    # Cache frame
                    if self._current_time:
                        self._frame_cache.put(self._current_time, frame)

                    # Update current frame
                    self._current_frame = frame
                    self._current_frame_time = self._current_time

                    # Emit
                    self._emit_frame(frame, self._current_time)
                    self._emit_position(self._current_time)

                    # Frame timing
                    frame_time = 1.0 / (self._stream_fps * self._speed)
                    time.sleep(max(0.001, frame_time))
                else:
                    # Stream error, try reconnect
                    self._emit_status("buffering")
                    time.sleep(0.1)
            else:
                # Need to connect
                self._connect_stream()

    def _connect_stream(self):
        """Connect to RTSP stream."""
        if not self._rtsp_url or not self._current_time:
            return

        self._emit_status("connecting")

        # Build URL with start time
        start_str = self._current_time.strftime("%Y%m%dT%H%M%SZ")
        url = f"{self._rtsp_url}?starttime={start_str}"

        try:
            self._capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 3)

            if self._capture.isOpened():
                self._stream_fps = self._capture.get(cv2.CAP_PROP_FPS) or 30.0
                logger.info(f"Playback connected: {url}")
                self._emit_status("playing" if self._playing else "paused")
            else:
                logger.error("Failed to open playback stream")
                self._emit_status("error")
                time.sleep(1.0)
        except Exception as e:
            logger.error(f"Playback connect error: {e}")
            self._emit_status("error")
            time.sleep(1.0)

    def _do_seek(self, target_time: datetime):
        """Perform actual seek operation."""
        if self._capture:
            self._capture.release()
            self._capture = None

        self._current_time = target_time
        self._connect_stream()

    def _start_thumbnail_prefetch(self):
        """Start background thumbnail generation."""
        if not self._start_time or not self._end_time:
            return

        def prefetch_thumbnails():
            duration = (self._end_time - self._start_time).total_seconds()
            interval = max(10, duration / 100)  # ~100 thumbnails max

            current = self._start_time
            while current < self._end_time and not self._stop_event.is_set():
                # Skip if already cached
                if self._thumbnail_cache.get(current) is None:
                    self._generate_thumbnail(current)

                current += timedelta(seconds=interval)

        self._prefetch_thread = Thread(target=prefetch_thumbnails, daemon=True)
        self._prefetch_thread.start()

    def _generate_thumbnail(self, timestamp: datetime):
        """Generate a single thumbnail."""
        if not self._rtsp_url:
            return

        try:
            start_str = timestamp.strftime("%Y%m%dT%H%M%SZ")
            url = f"{self._rtsp_url}?starttime={start_str}"

            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    self._thumbnail_cache.put(timestamp, frame)

            cap.release()
        except Exception as e:
            logger.debug(f"Thumbnail generation failed for {timestamp}: {e}")

    def _emit_frame(self, frame: np.ndarray, timestamp: Optional[datetime]):
        """Emit frame callback."""
        if self.on_frame and frame is not None:
            try:
                self.on_frame(frame, timestamp)
            except Exception:
                pass

    def _emit_status(self, status: str):
        """Emit status callback."""
        if self.on_status:
            try:
                self.on_status(status)
            except Exception:
                pass

    def _emit_position(self, position: Optional[datetime]):
        """Emit position callback."""
        if self.on_position and position:
            try:
                self.on_position(position)
            except Exception:
                pass
