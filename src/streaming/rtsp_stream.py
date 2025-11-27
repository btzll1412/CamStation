"""
RTSP stream handler for live video.
"""

import cv2
import numpy as np
from threading import Thread, Event
from queue import Queue, Empty
from typing import Optional
import logging
import time

logger = logging.getLogger(__name__)


class RTSPStream:
    """
    RTSP stream handler with buffered frame reading.
    
    Runs video capture in a separate thread to prevent UI blocking.
    """
    
    def __init__(self, url: str, buffer_size: int = 2):
        """
        Initialize RTSP stream.
        
        Args:
            url: RTSP stream URL
            buffer_size: Number of frames to buffer
        """
        self.url = url
        self.buffer_size = buffer_size
        
        self._capture: Optional[cv2.VideoCapture] = None
        self._frame_queue: Queue = Queue(maxsize=buffer_size)
        self._stop_event: Event = Event()
        self._thread: Optional[Thread] = None
        self._connected: bool = False
        self._last_frame_time: float = 0
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 5
        self._reconnect_delay: float = 2.0
    
    def start(self):
        """Start the stream capture thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        
        self._stop_event.clear()
        self._thread = Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the stream capture thread."""
        self._stop_event.set()
        
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        
        self._connected = False
        
        # Clear the queue
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except Empty:
                break
    
    def get_frame(self) -> Optional[np.ndarray]:
        """
        Get the latest frame.
        
        Returns:
            numpy array of the frame in BGR format, or None if no frame available
        """
        try:
            # Get the most recent frame, discard older ones
            frame = None
            while True:
                try:
                    frame = self._frame_queue.get_nowait()
                except Empty:
                    break
            return frame
        except Exception:
            return None
    
    def is_connected(self) -> bool:
        """Check if stream is connected."""
        return self._connected
    
    def get_resolution(self) -> Optional[tuple]:
        """Get stream resolution (width, height)."""
        if self._capture is not None and self._capture.isOpened():
            width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return (width, height)
        return None
    
    def get_fps(self) -> float:
        """Get stream FPS."""
        if self._capture is not None and self._capture.isOpened():
            return self._capture.get(cv2.CAP_PROP_FPS)
        return 0.0
    
    def _capture_loop(self):
        """Main capture loop running in separate thread."""
        while not self._stop_event.is_set():
            if not self._connect():
                # Connection failed, wait before retry
                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    logger.error(f"Max reconnection attempts reached for {self.url}")
                    break
                
                self._reconnect_attempts += 1
                time.sleep(self._reconnect_delay)
                continue
            
            # Reset reconnect counter on successful connection
            self._reconnect_attempts = 0
            
            # Read frames
            while not self._stop_event.is_set():
                ret, frame = self._capture.read()
                
                if not ret:
                    logger.warning(f"Failed to read frame from {self.url}")
                    self._connected = False
                    break
                
                # Update frame in queue
                try:
                    # Remove old frame if queue is full
                    if self._frame_queue.full():
                        try:
                            self._frame_queue.get_nowait()
                        except Empty:
                            pass
                    
                    self._frame_queue.put_nowait(frame)
                    self._last_frame_time = time.time()
                except Exception as e:
                    logger.error(f"Error queuing frame: {e}")
            
            # Release capture for reconnection
            if self._capture is not None:
                self._capture.release()
                self._capture = None
    
    def _connect(self) -> bool:
        """Establish connection to RTSP stream."""
        try:
            logger.info(f"Connecting to {self.url}")
            
            # Configure capture
            self._capture = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            
            # Set capture properties for better performance
            self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Try to use TCP transport (more reliable than UDP)
            # This is set via the URL or environment variable
            
            if not self._capture.isOpened():
                logger.error(f"Failed to open stream: {self.url}")
                return False
            
            # Read a test frame
            ret, _ = self._capture.read()
            if not ret:
                logger.error(f"Failed to read initial frame from: {self.url}")
                self._capture.release()
                return False
            
            self._connected = True
            logger.info(f"Connected to {self.url}")
            return True
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False


class RTSPPlayback(RTSPStream):
    """
    RTSP playback stream for recorded video.
    
    Extends RTSPStream with playback controls.
    """
    
    def __init__(self, url: str, start_time: str = None):
        """
        Initialize playback stream.
        
        Args:
            url: RTSP playback URL
            start_time: Start time in format YYYYMMDDTHHMMSSZ
        """
        # Append start time to URL if provided
        if start_time and "?" not in url:
            url = f"{url}?starttime={start_time}"
        elif start_time:
            url = f"{url}&starttime={start_time}"
        
        super().__init__(url, buffer_size=5)
        
        self._paused = False
        self._playback_speed = 1.0
    
    def pause(self):
        """Pause playback."""
        self._paused = True
    
    def resume(self):
        """Resume playback."""
        self._paused = False
    
    def is_paused(self) -> bool:
        """Check if playback is paused."""
        return self._paused
    
    def set_speed(self, speed: float):
        """
        Set playback speed.
        
        Args:
            speed: Playback speed multiplier (0.5, 1.0, 2.0, 4.0, etc.)
        """
        self._playback_speed = speed
        # Note: Actual speed control depends on NVR support
        # May need to reconnect with different URL parameters
    
    def seek(self, timestamp: str):
        """
        Seek to a specific timestamp.
        
        Args:
            timestamp: Time in format YYYYMMDDTHHMMSSZ
        """
        # Stop current stream
        self.stop()
        
        # Update URL with new start time
        base_url = self.url.split("?")[0]
        self.url = f"{base_url}?starttime={timestamp}"
        
        # Restart stream
        self.start()
    
    def get_frame(self) -> Optional[np.ndarray]:
        """Get frame with pause support."""
        if self._paused:
            # Return the last frame when paused
            try:
                return self._frame_queue.queue[-1] if self._frame_queue.queue else None
            except Exception:
                return None
        
        return super().get_frame()
