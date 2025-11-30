"""
Unified camera cell that seamlessly switches between live and playback.

Digital Watchdog-style:
- Shows LIVE when timeline is at "now"
- Shows PLAYBACK when timeline is in the past
- Auto-syncs to timeline position
- X button to remove from layout
- Drag & drop support
"""

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QMenu, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QMimeData, QByteArray, QPoint
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QFont, QAction,
    QDragEnterEvent, QDropEvent, QDragLeaveEvent, QDrag, QMouseEvent
)

import cv2
import numpy as np
from typing import Optional, Callable
from threading import Lock
from datetime import datetime, timedelta
import json

from models.device import Camera, Device
from core.stream_manager import StreamManager
from core.playback_controller import PlaybackController
from ui.styles import COLORS


class UnifiedCameraCell(QFrame):
    """
    Camera cell that seamlessly switches between live and playback.

    When timeline is at "NOW" -> shows live stream
    When timeline is in past -> shows playback
    """

    # Signals
    clicked = pyqtSignal(int)  # cell_index
    double_clicked = pyqtSignal(int)  # cell_index
    camera_dropped = pyqtSignal(int, int)  # cell_index, camera_id
    camera_swapped = pyqtSignal(int, int)  # from_cell_index, to_cell_index
    close_requested = pyqtSignal(int)  # cell_index
    fullscreen_requested = pyqtSignal(int)  # camera_id

    def __init__(self, index: int, stream_manager: StreamManager, parent=None):
        super().__init__(parent)
        self.index = index
        self.stream_manager = stream_manager

        # Camera info
        self.camera: Optional[Camera] = None
        self.device: Optional[Device] = None

        # State
        self._mode = "empty"  # empty, live, playback
        self._status = "empty"  # empty, connecting, connected, playing, paused, error, no_recording
        self._is_selected = False
        self._is_drag_over = False
        self._current_time: Optional[datetime] = None
        self._target_time: Optional[datetime] = None  # Timeline position
        self._drag_start_pos: Optional[QPoint] = None  # For initiating drag

        # Frame data
        self._current_frame: Optional[np.ndarray] = None
        self._frame_lock = Lock()

        # Playback controller (for playback mode)
        self._playback_controller: Optional[PlaybackController] = None
        self._playback_start: Optional[datetime] = None
        self._playback_end: Optional[datetime] = None

        # Live threshold - within this many seconds of "now" = show live
        self._live_threshold_seconds = 5

        self._setup_ui()
        self.setAcceptDrops(True)

        # Update timer
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_display)

    def _setup_ui(self):
        """Setup UI."""
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        self._update_style()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(160, 90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Video display
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setScaledContents(False)
        layout.addWidget(self.video_label)

        self._show_empty_state()
        self.setMouseTracking(True)

    def _update_style(self, drag_over: bool = False, selected: bool = False):
        """Update cell styling."""
        if drag_over:
            border_color = COLORS['accent_blue']
            bg_color = COLORS['bg_secondary']
        elif selected:
            border_color = COLORS['accent_blue']
            bg_color = COLORS['bg_dark']
        else:
            border_color = COLORS['border']
            bg_color = COLORS['bg_dark']

        self.setStyleSheet(f"""
            UnifiedCameraCell {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 4px;
            }}
        """)

    def _show_empty_state(self):
        """Show empty cell."""
        self.video_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_secondary']};
                background-color: {COLORS['bg_dark']};
            }}
        """)
        self.video_label.setText(
            "<div style='text-align: center;'>"
            "<p style='font-size: 24px; margin: 0;'>📷</p>"
            "<p style='margin: 8px 0 0 0; color: #6e7681;'>Drop camera here</p>"
            "</div>"
        )

    def set_camera(self, camera: Camera, device: Device):
        """Set camera for this cell."""
        self.clear()

        self.camera = camera
        self.device = device
        self._status = "connecting"
        self.video_label.setText(f"Loading {camera.name}...")

        # Decide mode based on target time
        self._decide_mode()

        self.update()

    def set_timeline_position(self, position: datetime, start_time: datetime, end_time: datetime):
        """
        Set timeline position - this determines live vs playback.

        If position is within threshold of "now" -> live mode
        If position is in the past -> playback mode
        """
        self._target_time = position
        self._playback_start = start_time
        self._playback_end = end_time

        if self.camera:
            self._decide_mode()

    def _decide_mode(self):
        """Decide whether to show live or playback based on timeline position."""
        if not self.camera or not self.device:
            return

        now = datetime.now()

        # If no target time or target is very close to now -> live mode
        if self._target_time is None:
            self._switch_to_live()
        elif (now - self._target_time).total_seconds() <= self._live_threshold_seconds:
            self._switch_to_live()
        else:
            self._switch_to_playback()

    def _switch_to_live(self):
        """Switch to live stream mode."""
        if self._mode == "live":
            return

        # Stop playback if running
        if self._playback_controller:
            self._playback_controller.stop()
            self._playback_controller = None

        self._mode = "live"
        self._status = "connecting"

        # Start live stream
        stream_url = self.camera.rtsp_url_sub if hasattr(self.camera, 'rtsp_url_sub') and self.camera.rtsp_url_sub else self.camera.rtsp_url

        if stream_url:
            self.stream_manager.start_stream(
                camera_id=self.camera.id,
                url=stream_url,
                use_sub_stream=True,
                on_frame=self._on_live_frame,
                on_status=self._on_live_status
            )
            self._update_timer.start(33)  # 30fps

    def _switch_to_playback(self):
        """Switch to playback mode."""
        if self._mode == "playback" and self._playback_controller:
            # Just seek to new position
            if self._target_time:
                self._playback_controller.seek(self._target_time)
            return

        # Stop live stream
        if self._mode == "live" and self.camera:
            self.stream_manager.stop_stream(self.camera.id)

        self._mode = "playback"
        self._status = "connecting"

        # Create playback controller
        self._playback_controller = PlaybackController(
            on_frame=self._on_playback_frame,
            on_status=self._on_playback_status,
            on_position=self._on_playback_position
        )

        # Build playback URL
        rtsp_port = getattr(self.device, 'rtsp_port', 554) or 554
        base_url = f"rtsp://{self.device.username}:{self.device.password}@{self.device.ip_address}:{rtsp_port}"
        playback_url = f"{base_url}/Streaming/tracks/{self.camera.channel_number}01"

        try:
            start = self._playback_start or (datetime.now() - timedelta(hours=24))
            end = self._playback_end or datetime.now()

            self._playback_controller.load_recording(playback_url, start, end)

            # Seek to target time
            if self._target_time:
                self._playback_controller.seek(self._target_time)

            self._playback_controller.play()
            self._update_timer.start(33)

        except Exception as e:
            self._status = "no_recording"
            self.video_label.setText(
                f"<div style='text-align: center; color: {COLORS['text_muted']};'>"
                f"<p style='font-size: 24px; font-weight: 300;'>NO DATA</p>"
                f"</div>"
            )

    def seek(self, position: datetime):
        """Seek to position (for synchronized scrubbing)."""
        self._target_time = position

        if not self.camera:
            return

        now = datetime.now()

        # Check if we should switch modes
        if (now - position).total_seconds() <= self._live_threshold_seconds:
            self._switch_to_live()
        else:
            if self._mode == "playback" and self._playback_controller:
                self._playback_controller.seek(position)
            else:
                self._switch_to_playback()

    def play(self):
        """Play (for playback mode)."""
        if self._mode == "playback" and self._playback_controller:
            self._playback_controller.play()

    def pause(self):
        """Pause (for playback mode)."""
        if self._mode == "playback" and self._playback_controller:
            self._playback_controller.pause()

    def clear(self):
        """Clear camera and stop streams."""
        self._update_timer.stop()

        if self._mode == "live" and self.camera:
            self.stream_manager.stop_stream(self.camera.id)

        if self._playback_controller:
            self._playback_controller.stop()
            self._playback_controller = None

        self.camera = None
        self.device = None
        self._mode = "empty"
        self._status = "empty"
        self._current_frame = None
        self._target_time = None

        self.video_label.setPixmap(QPixmap())
        self._show_empty_state()
        self.update()

    def _on_live_frame(self, camera_id: int, frame: np.ndarray):
        """Handle live frame."""
        if self.camera and camera_id == self.camera.id and self._mode == "live":
            with self._frame_lock:
                self._current_frame = frame.copy()

    def _on_live_status(self, camera_id: int, status: str):
        """Handle live status."""
        if self.camera and camera_id == self.camera.id and self._mode == "live":
            self._status = status

    def _on_playback_frame(self, frame: np.ndarray, timestamp: datetime):
        """Handle playback frame."""
        if self._mode == "playback":
            with self._frame_lock:
                self._current_frame = frame.copy()
                self._current_time = timestamp

    def _on_playback_status(self, status: str):
        """Handle playback status."""
        if self._mode == "playback":
            if status == "playing":
                self._status = "playing"
            elif status == "paused":
                self._status = "paused"
            elif status == "error":
                self._status = "no_recording"
                self.video_label.setText(
                    f"<div style='text-align: center; color: {COLORS['text_muted']};'>"
                    f"<p style='font-size: 24px; font-weight: 300;'>NO DATA</p>"
                    f"</div>"
                )

    def _on_playback_position(self, position: datetime):
        """Handle playback position."""
        self._current_time = position

    def _update_display(self):
        """Update video display."""
        if self._mode == "live":
            frame = self.stream_manager.get_frame(self.camera.id) if self.camera else None
            if frame is not None:
                self._display_frame(frame)
                self._status = "connected"
        elif self._mode == "playback":
            with self._frame_lock:
                if self._current_frame is not None:
                    self._display_frame(self._current_frame)

    def _display_frame(self, frame: np.ndarray):
        """Display frame."""
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)

            pixmap = QPixmap.fromImage(img).scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
            self.video_label.setPixmap(pixmap)
        except:
            pass

    def paintEvent(self, event):
        """Paint overlays."""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Drop indicator
        if self._is_drag_over:
            painter.setPen(QColor(COLORS['accent_blue']))
            painter.setBrush(QColor(47, 129, 247, 30))
            painter.drawRect(self.rect().adjusted(2, 2, -2, -2))

        if not self.camera:
            return

        # Top-right X button area
        btn_size = 24
        btn_margin = 4
        btn_rect = self.rect().adjusted(
            self.width() - btn_size - btn_margin,
            btn_margin,
            -btn_margin,
            -(self.height() - btn_size - btn_margin)
        )

        # X button background
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(btn_rect, 4, 4)

        # X text
        painter.setPen(QColor(COLORS['text_primary']))
        font = painter.font()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "×")

        # Bottom overlay
        overlay_height = 32
        overlay_rect = self.rect().adjusted(0, self.height() - overlay_height, 0, 0)

        painter.fillRect(overlay_rect, QColor(0, 0, 0, 200))

        # Camera name
        painter.setPen(QColor(COLORS['text_primary']))
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(
            overlay_rect.adjusted(10, 0, -80, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.camera.name
        )

        # Mode indicator (LIVE or time)
        mode_x = overlay_rect.right() - 70
        mode_y = overlay_rect.center().y() - 8

        if self._mode == "live":
            # Red LIVE badge
            painter.setBrush(QColor("#e53935"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(mode_x, mode_y, 45, 16, 3, 3)

            painter.setPen(QColor("white"))
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(mode_x, mode_y, 45, 16, Qt.AlignmentFlag.AlignCenter, "● LIVE")
        else:
            # Show playback time
            time_str = self._current_time.strftime("%H:%M:%S") if self._current_time else "--:--:--"
            painter.setPen(QColor(COLORS['text_secondary']))
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(
                overlay_rect.adjusted(0, 0, -10, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                time_str
            )

    def set_selected(self, selected: bool):
        """Set selection state."""
        self._is_selected = selected
        self._update_style(selected=selected)

    # Mouse events
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicking X button
            btn_size = 24
            btn_margin = 4
            btn_x = self.width() - btn_size - btn_margin
            btn_y = btn_margin

            if self.camera and btn_x <= event.pos().x() <= btn_x + btn_size and btn_y <= event.pos().y() <= btn_y + btn_size:
                self.close_requested.emit(self.index)
                return

            # Store drag start position for potential drag
            self._drag_start_pos = event.pos()
            self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for drag initiation."""
        if not self._drag_start_pos:
            super().mouseMoveEvent(event)
            return

        # Check if we've moved far enough to start a drag
        if (event.pos() - self._drag_start_pos).manhattanLength() < 10:
            super().mouseMoveEvent(event)
            return

        # Only drag if we have a camera
        if not self.camera:
            self._drag_start_pos = None
            super().mouseMoveEvent(event)
            return

        # Start the drag
        drag = QDrag(self)
        mime_data = QMimeData()

        # Include cell index so we know where it came from
        camera_json = json.dumps({
            "camera_id": self.camera.id,
            "camera_name": self.camera.name,
            "device_id": self.device.id if self.device else None,
            "source_cell_index": self.index
        })
        mime_data.setData("application/x-camera", QByteArray(camera_json.encode()))
        mime_data.setText(self.camera.name)

        drag.setMimeData(mime_data)

        # Create drag preview pixmap
        pixmap = self._create_drag_pixmap()
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))

        # Execute drag
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start_pos = None

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Clear drag start position on release."""
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _create_drag_pixmap(self) -> QPixmap:
        """Create a preview pixmap for dragging."""
        pixmap = QPixmap(160, 90)
        pixmap.fill(QColor(COLORS['bg_dark']))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Border
        painter.setPen(QColor(COLORS['accent_blue']))
        painter.drawRect(0, 0, 159, 89)

        # Camera name
        painter.setPen(QColor(COLORS['text_primary']))
        painter.setFont(QFont("Segoe UI", 10))
        name = self.camera.name if self.camera else "Camera"
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, f"📷 {name}")

        painter.end()
        return pixmap

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.camera:
                self.fullscreen_requested.emit(self.camera.id)
            else:
                self.double_clicked.emit(self.index)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                color: {COLORS['text_primary']};
            }}
            QMenu::item:selected {{
                background-color: {COLORS['accent_blue']};
            }}
        """)

        if self.camera:
            fullscreen = QAction("🖥️ Fullscreen", self)
            fullscreen.triggered.connect(lambda: self.fullscreen_requested.emit(self.camera.id))
            menu.addAction(fullscreen)

            menu.addSeparator()

            snapshot = QAction("📸 Snapshot", self)
            snapshot.triggered.connect(self._take_snapshot)
            menu.addAction(snapshot)

            menu.addSeparator()

            remove = QAction("❌ Remove", self)
            remove.triggered.connect(lambda: self.close_requested.emit(self.index))
            menu.addAction(remove)

        menu.exec(event.globalPos())

    def _take_snapshot(self):
        """Take snapshot."""
        if self._current_frame is not None and self.camera:
            import os
            dir_path = os.path.expanduser("~/Pictures/CamStation")
            os.makedirs(dir_path, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(dir_path, f"{self.camera.name}_{ts}.jpg")
            cv2.imwrite(path, self._current_frame)

            parent = self.window()
            if hasattr(parent, 'statusbar'):
                parent.statusbar.showMessage(f"Saved: {path}", 3000)

    # Drag & drop
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat("application/x-camera"):
            event.acceptProposedAction()
            self._is_drag_over = True
            self._update_style(drag_over=True)
            self.update()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self._is_drag_over = False
        self._update_style(selected=self._is_selected)
        self.update()

    def dropEvent(self, event: QDropEvent):
        self._is_drag_over = False
        self._update_style(selected=self._is_selected)

        if event.mimeData().hasFormat("application/x-camera"):
            data = event.mimeData().data("application/x-camera")
            camera_data = json.loads(bytes(data).decode())
            camera_id = camera_data.get("camera_id")
            source_cell_index = camera_data.get("source_cell_index")

            if camera_id:
                # If dragged from another cell, emit swap signal
                if source_cell_index is not None and source_cell_index != self.index:
                    self.camera_swapped.emit(source_cell_index, self.index)
                else:
                    # Dropped from device tree
                    self.camera_dropped.emit(self.index, camera_id)
                event.acceptProposedAction()

        self.update()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_live(self) -> bool:
        return self._mode == "live"
