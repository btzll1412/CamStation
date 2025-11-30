"""
Multi-camera playback view with synchronized timeline.

Features:
- Grid-based playback (like live view)
- Drag & drop cameras from device tree
- Synchronized timeline scrubbing across all cameras
- Independent playback per camera if needed
- Cross-site support (different NVRs/IPs)
"""

from PyQt6.QtWidgets import (
    QWidget, QGridLayout, QLabel, QFrame,
    QVBoxLayout, QHBoxLayout, QMenu, QSizePolicy,
    QPushButton, QComboBox, QSlider
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QMimeData
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QFont, QAction,
    QDragEnterEvent, QDropEvent, QDragLeaveEvent
)

import cv2
import numpy as np
from typing import Optional, Dict, List, Callable
from threading import Lock
from datetime import datetime, timedelta
from dataclasses import dataclass
import json

from models.device import Camera, Device
from core.playback_controller import PlaybackController
from ui.styles import COLORS


@dataclass
class PlaybackStreamInfo:
    """Information about a playback stream."""
    camera: Camera
    device: Device
    controller: PlaybackController
    start_time: datetime
    end_time: datetime
    has_recording: bool = True


class PlaybackCell(QFrame):
    """Single playback cell in the grid."""

    clicked = pyqtSignal(int)  # cell_index
    double_clicked = pyqtSignal(int)  # cell_index
    camera_dropped = pyqtSignal(int, int)  # cell_index, camera_id
    close_requested = pyqtSignal(int)  # cell_index
    recording_status = pyqtSignal(int, bool)  # cell_index, has_recording

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.camera: Optional[Camera] = None
        self.device: Optional[Device] = None
        self.controller: Optional[PlaybackController] = None
        self.is_selected = False
        self._status = "empty"  # empty, loading, playing, paused, no_recording, error
        self._current_frame: Optional[np.ndarray] = None
        self._current_time: Optional[datetime] = None
        self._frame_lock = Lock()
        self._is_drag_over = False
        self._has_recording = False

        self._setup_ui()
        self.setAcceptDrops(True)

        # Frame update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_display)

    def _setup_ui(self):
        """Setup UI components."""
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
            border_color = "#a371f7"  # Purple for playback
            bg_color = COLORS['bg_dark']
        else:
            border_color = COLORS['border']
            bg_color = COLORS['bg_dark']

        self.setStyleSheet(f"""
            PlaybackCell {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 4px;
            }}
        """)

    def _show_empty_state(self):
        """Show empty cell state."""
        self.video_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_secondary']};
                background-color: {COLORS['bg_dark']};
            }}
        """)
        self.video_label.setText(
            "<div style='text-align: center;'>"
            "<p style='font-size: 24px; margin: 0;'>⏪</p>"
            "<p style='margin: 8px 0 0 0; color: #6e7681;'>Drop camera for playback</p>"
            "<p style='margin: 4px 0 0 0; color: #484f58; font-size: 10px;'>Recordings sync across all cameras</p>"
            "</div>"
        )

    def set_camera(self, camera: Camera, device: Device, start_time: datetime, end_time: datetime):
        """Set camera for playback."""
        self.stop_playback()

        self.camera = camera
        self.device = device
        self._status = "loading"
        self.video_label.setText(f"Loading recordings for\n{camera.name}...")

        # Create playback controller
        self.controller = PlaybackController(
            on_frame=self._on_frame,
            on_status=self._on_status,
            on_position=self._on_position
        )

        # Build playback URL
        rtsp_port = getattr(device, 'rtsp_port', 554) or 554
        base_url = f"rtsp://{device.username}:{device.password}@{device.ip_address}:{rtsp_port}"
        playback_url = f"{base_url}/Streaming/tracks/{camera.channel_number}01"

        try:
            # Load recording
            self.controller.load_recording(playback_url, start_time, end_time)
            self._has_recording = True
            self.recording_status.emit(self.index, True)

            # Start update timer
            self.update_timer.start(33)  # ~30fps

        except Exception as e:
            self._status = "error"
            self._has_recording = False
            self.recording_status.emit(self.index, False)
            self.video_label.setText(
                f"<div style='text-align: center; color: {COLORS['offline']};'>"
                f"<p style='font-size: 18px;'>No Recording</p>"
                f"<p style='font-size: 11px; color: {COLORS['text_secondary']};'>{camera.name}</p>"
                f"</div>"
            )

    def play(self):
        """Start/resume playback."""
        if self.controller:
            self.controller.play()
            self._status = "playing"

    def pause(self):
        """Pause playback."""
        if self.controller:
            self.controller.pause()
            self._status = "paused"

    def seek(self, target_time: datetime):
        """Seek to specific time."""
        if self.controller:
            self.controller.seek(target_time)

    def stop_playback(self):
        """Stop playback and clear."""
        self.update_timer.stop()

        if self.controller:
            self.controller.stop()
            self.controller = None

        self.camera = None
        self.device = None
        self._status = "empty"
        self._current_frame = None
        self._has_recording = False
        self.video_label.setPixmap(QPixmap())
        self._show_empty_state()
        self.update()

    def _on_frame(self, frame: np.ndarray, timestamp: datetime):
        """Handle frame from controller."""
        with self._frame_lock:
            self._current_frame = frame.copy()
            self._current_time = timestamp

    def _on_status(self, status: str):
        """Handle status change."""
        if status == "playing":
            self._status = "playing"
        elif status == "paused":
            self._status = "paused"
        elif status == "error":
            self._status = "error"
            self._has_recording = False
            self.recording_status.emit(self.index, False)

    def _on_position(self, position: datetime):
        """Handle position update."""
        self._current_time = position

    def _update_display(self):
        """Update video display."""
        with self._frame_lock:
            if self._current_frame is not None:
                self._display_frame(self._current_frame)

    def _display_frame(self, frame: np.ndarray):
        """Display a frame."""
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w

            q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

            scaled_pixmap = QPixmap.fromImage(q_img).scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )

            self.video_label.setPixmap(scaled_pixmap)
        except Exception:
            pass

    def paintEvent(self, event):
        """Custom paint for overlays."""
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

        # Camera name and time overlay
        overlay_height = 32
        overlay_rect = self.rect().adjusted(0, self.height() - overlay_height, 0, 0)

        painter.fillRect(overlay_rect, QColor(0, 0, 0, 200))

        painter.setPen(QColor(COLORS['text_primary']))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        # Camera name
        painter.drawText(
            overlay_rect.adjusted(8, 0, -80, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.camera.name
        )

        # Current time
        if self._current_time:
            time_str = self._current_time.strftime("%H:%M:%S")
            font.setBold(False)
            font.setPointSize(8)
            painter.setFont(font)
            painter.setPen(QColor(COLORS['text_secondary']))
            painter.drawText(
                overlay_rect.adjusted(0, 0, -8, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                time_str
            )

        # Status indicator
        indicator_x = overlay_rect.right() - 75
        indicator_y = overlay_rect.center().y() - 4

        if self._status == "playing":
            painter.setBrush(QColor(COLORS['online']))
        elif self._status == "paused":
            painter.setBrush(QColor(COLORS['warning']))
        elif not self._has_recording:
            painter.setBrush(QColor(COLORS['offline']))
        else:
            painter.setBrush(QColor(COLORS['text_secondary']))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(indicator_x, indicator_y, 8, 8)

    def set_selected(self, selected: bool):
        """Set selection state."""
        self.is_selected = selected
        self._update_style(selected=selected)

    # Drag & Drop
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat("application/x-camera"):
            event.acceptProposedAction()
            self._is_drag_over = True
            self._update_style(drag_over=True)
            self.update()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self._is_drag_over = False
        self._update_style(selected=self.is_selected)
        self.update()

    def dropEvent(self, event: QDropEvent):
        self._is_drag_over = False
        self._update_style(selected=self.is_selected)

        if event.mimeData().hasFormat("application/x-camera"):
            data = event.mimeData().data("application/x-camera")
            camera_data = json.loads(bytes(data).decode())
            camera_id = camera_data.get("camera_id")

            if camera_id:
                self.camera_dropped.emit(self.index, camera_id)
                event.acceptProposedAction()

        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.index)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                color: {COLORS['text_primary']};
            }}
            QMenu::item:selected {{
                background-color: {COLORS['accent_blue']};
            }}
        """)

        if self.camera and self.controller:
            if self._status == "playing":
                pause_action = QAction("⏸️ Pause", self)
                pause_action.triggered.connect(self.pause)
                menu.addAction(pause_action)
            else:
                play_action = QAction("▶️ Play", self)
                play_action.triggered.connect(self.play)
                menu.addAction(play_action)

            menu.addSeparator()

            snapshot_action = QAction("📸 Snapshot", self)
            snapshot_action.triggered.connect(self._take_snapshot)
            menu.addAction(snapshot_action)

            menu.addSeparator()

            close_action = QAction("❌ Remove", self)
            close_action.triggered.connect(lambda: self.close_requested.emit(self.index))
            menu.addAction(close_action)

        menu.exec(event.globalPos())

    def _take_snapshot(self):
        """Take snapshot of current frame."""
        if self._current_frame is not None and self.camera:
            import os
            snapshot_dir = os.path.expanduser("~/Pictures/CamStation")
            os.makedirs(snapshot_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.camera.name}_playback_{timestamp}.jpg"
            filepath = os.path.join(snapshot_dir, filename)

            cv2.imwrite(filepath, self._current_frame)

            parent = self.window()
            if hasattr(parent, 'statusbar'):
                parent.statusbar.showMessage(f"Snapshot saved: {filepath}", 3000)


class PlaybackViewWidget(QWidget):
    """
    Multi-camera playback grid with synchronized timeline.

    Features:
    - Drag & drop cameras from device tree
    - Synchronized seeking across all cameras
    - Independent play/pause per camera
    - Visual indicators for recording availability
    """

    # Signals
    position_changed = pyqtSignal(datetime)  # Current playback position
    playback_started = pyqtSignal()
    playback_paused = pyqtSignal()
    cameras_changed = pyqtSignal(int)  # Number of active cameras

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.cells: List[PlaybackCell] = []
        self.selected_cell: int = -1
        self.rows = 2
        self.cols = 2

        # Playback state
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
        self._current_time: Optional[datetime] = None
        self._is_playing = False
        self._sync_enabled = True  # Synchronized scrubbing

        self._setup_ui()
        self.set_grid_layout(2, 2)

        # Position update timer
        self._position_timer = QTimer()
        self._position_timer.timeout.connect(self._update_position)
        self._position_timer.start(100)

    def _setup_ui(self):
        """Setup UI."""
        self.setStyleSheet(f"background-color: {COLORS['bg_dark']};")
        self.setAcceptDrops(True)

        self.layout = QGridLayout(self)
        self.layout.setSpacing(4)
        self.layout.setContentsMargins(4, 4, 4, 4)

    def set_grid_layout(self, rows: int, cols: int):
        """Set grid dimensions."""
        self.rows = rows
        self.cols = cols

        # Store existing cameras
        existing = []
        for cell in self.cells:
            if cell.camera and cell.device:
                existing.append((cell.camera, cell.device))
            cell.stop_playback()
            cell.deleteLater()

        self.cells.clear()

        while self.layout.count():
            self.layout.takeAt(0)

        # Create new cells
        idx = 0
        for row in range(rows):
            for col in range(cols):
                cell = PlaybackCell(idx)
                cell.clicked.connect(self._on_cell_clicked)
                cell.double_clicked.connect(self._on_cell_double_clicked)
                cell.camera_dropped.connect(self._on_camera_dropped)
                cell.close_requested.connect(self._on_close_requested)
                cell.recording_status.connect(self._on_recording_status)

                self.layout.addWidget(cell, row, col)
                self.cells.append(cell)
                idx += 1

        for i in range(rows):
            self.layout.setRowStretch(i, 1)
        for i in range(cols):
            self.layout.setColumnStretch(i, 1)

        # Restore cameras
        if self._start_time and self._end_time:
            for i, (camera, device) in enumerate(existing):
                if i < len(self.cells):
                    self.cells[i].set_camera(camera, device, self._start_time, self._end_time)

    def set_time_range(self, start_time: datetime, end_time: datetime):
        """Set playback time range for all cameras."""
        self._start_time = start_time
        self._end_time = end_time
        self._current_time = start_time

    def add_camera(self, camera_id: int, cell_index: int = -1):
        """Add camera to playback."""
        camera = self.db.get_camera(camera_id)
        if not camera:
            return

        device = self.db.get_device(camera.device_id)
        if not device:
            return

        # Set default time range if not set
        if not self._start_time or not self._end_time:
            self._end_time = datetime.now()
            self._start_time = self._end_time - timedelta(hours=24)

        # Find target cell
        if 0 <= cell_index < len(self.cells):
            target = self.cells[cell_index]
        elif 0 <= self.selected_cell < len(self.cells) and not self.cells[self.selected_cell].camera:
            target = self.cells[self.selected_cell]
        else:
            target = next((c for c in self.cells if not c.camera), None)
            if not target and self.cells:
                target = self.cells[0]

        if target:
            target.set_camera(camera, device, self._start_time, self._end_time)
            self.cameras_changed.emit(self.get_active_count())

    def play_all(self):
        """Start playback on all cameras."""
        self._is_playing = True
        for cell in self.cells:
            if cell.camera and cell.controller:
                cell.play()
        self.playback_started.emit()

    def pause_all(self):
        """Pause playback on all cameras."""
        self._is_playing = False
        for cell in self.cells:
            if cell.camera and cell.controller:
                cell.pause()
        self.playback_paused.emit()

    def seek_all(self, target_time: datetime):
        """Synchronized seek across all cameras."""
        self._current_time = target_time
        for cell in self.cells:
            if cell.camera and cell.controller:
                cell.seek(target_time)
        self.position_changed.emit(target_time)

    def seek_relative(self, delta_seconds: float):
        """Seek relative to current position."""
        if self._current_time:
            target = self._current_time + timedelta(seconds=delta_seconds)
            if self._start_time:
                target = max(self._start_time, target)
            if self._end_time:
                target = min(self._end_time, target)
            self.seek_all(target)

    def stop_all(self):
        """Stop all playback."""
        self._is_playing = False
        for cell in self.cells:
            cell.stop_playback()
        self.cameras_changed.emit(0)

    def get_active_count(self) -> int:
        """Get number of active playback streams."""
        return sum(1 for c in self.cells if c.camera)

    def get_current_time(self) -> Optional[datetime]:
        """Get current playback position."""
        return self._current_time

    def _update_position(self):
        """Update position from first active cell."""
        for cell in self.cells:
            if cell.camera and cell.controller and cell._current_time:
                if cell._current_time != self._current_time:
                    self._current_time = cell._current_time
                    self.position_changed.emit(self._current_time)
                break

    def _on_cell_clicked(self, index: int):
        """Handle cell click."""
        if 0 <= self.selected_cell < len(self.cells):
            self.cells[self.selected_cell].set_selected(False)

        self.selected_cell = index
        if 0 <= index < len(self.cells):
            self.cells[index].set_selected(True)

    def _on_cell_double_clicked(self, index: int):
        """Handle double-click - toggle play/pause."""
        if 0 <= index < len(self.cells):
            cell = self.cells[index]
            if cell.camera and cell.controller:
                if cell._status == "playing":
                    cell.pause()
                else:
                    cell.play()

    def _on_camera_dropped(self, cell_index: int, camera_id: int):
        """Handle camera drop."""
        self.add_camera(camera_id, cell_index)

    def _on_close_requested(self, cell_index: int):
        """Handle close request."""
        if 0 <= cell_index < len(self.cells):
            self.cells[cell_index].stop_playback()
            self.cameras_changed.emit(self.get_active_count())

    def _on_recording_status(self, cell_index: int, has_recording: bool):
        """Handle recording status update."""
        # Could show notification if camera has no recordings
        pass

    # Drag & drop on widget
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat("application/x-camera"):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasFormat("application/x-camera"):
            data = event.mimeData().data("application/x-camera")
            camera_data = json.loads(bytes(data).decode())
            camera_id = camera_data.get("camera_id")

            if camera_id:
                self.add_camera(camera_id)
                event.acceptProposedAction()

    @property
    def is_playing(self) -> bool:
        return self._is_playing
