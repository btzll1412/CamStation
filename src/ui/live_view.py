"""
Live view widget for displaying camera streams in a grid.

Optimized for 32+ cameras without freezing.
"""

from PyQt6.QtWidgets import (
    QWidget, QGridLayout, QLabel, QFrame,
    QVBoxLayout, QMenu, QSizePolicy, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QAction

import cv2
import numpy as np
from typing import Optional, Dict, List
from threading import Lock

from models.device import Camera
from core.stream_manager import StreamManager
from ui.styles import COLORS, get_camera_cell_style


class CameraViewCell(QFrame):
    """Single camera view cell in the grid."""

    clicked = pyqtSignal(int)  # cell_index
    double_clicked = pyqtSignal(int)  # cell_index
    context_menu_requested = pyqtSignal(int, object)  # cell_index, position

    def __init__(self, index: int, stream_manager: StreamManager, parent=None):
        super().__init__(parent)
        self.index = index
        self.stream_manager = stream_manager
        self.camera: Optional[Camera] = None
        self.is_selected = False
        self._status = "empty"  # empty, connecting, connected, error
        self._last_frame: Optional[np.ndarray] = None
        self._pixmap: Optional[QPixmap] = None
        self._frame_lock = Lock()

        self._setup_ui()

        # Frame update timer (30 fps target)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_frame)

    def _setup_ui(self):
        """Setup UI components."""
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        self.setLineWidth(1)
        self.setStyleSheet(get_camera_cell_style())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(160, 90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Video display label
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        self.video_label.setText("No Camera")
        self.video_label.setScaledContents(False)
        layout.addWidget(self.video_label)

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)

    def set_camera(self, camera: Camera):
        """Set camera for this cell and start streaming."""
        self.stop_stream()

        self.camera = camera
        self._status = "connecting"
        self.video_label.setText("Connecting...")
        self.update()

        # Start stream using stream manager
        # Use sub-stream for grid view (lower bandwidth)
        stream_url = camera.rtsp_url_sub if camera.rtsp_url_sub else camera.rtsp_url

        self.stream_manager.start_stream(
            camera_id=camera.id,
            url=stream_url,
            use_sub_stream=True,
            on_frame=self._on_frame_received,
            on_status=self._on_status_changed
        )

        # Start frame update timer
        self.update_timer.start(33)  # ~30 fps

    def stop_stream(self):
        """Stop current stream."""
        self.update_timer.stop()

        if self.camera:
            self.stream_manager.stop_stream(self.camera.id)

        self.camera = None
        self._status = "empty"
        self._last_frame = None
        self._pixmap = None
        self.video_label.setText("No Camera")
        self.video_label.setPixmap(QPixmap())
        self.update()

    def _on_frame_received(self, camera_id: int, frame: np.ndarray):
        """Handle frame received from stream manager."""
        if self.camera and camera_id == self.camera.id:
            with self._frame_lock:
                self._last_frame = frame

    def _on_status_changed(self, camera_id: int, status: str):
        """Handle status change from stream manager."""
        if self.camera and camera_id == self.camera.id:
            self._status = status
            if status == "connected":
                pass  # Will show frame
            elif status == "connecting":
                self.video_label.setText("Connecting...")
            elif status == "reconnecting":
                self.video_label.setText("Reconnecting...")
            elif status == "error" or status == "failed":
                self.video_label.setText("Connection Failed")
            elif status == "disconnected":
                self.video_label.setText("Disconnected")

    def _update_frame(self):
        """Update the displayed frame from stream."""
        if not self.camera:
            return

        # Get frame from stream manager
        frame = self.stream_manager.get_frame(self.camera.id)

        if frame is not None:
            self._display_frame(frame)
            self._status = "connected"
        elif self._status == "connecting":
            # Still connecting, show loading animation
            pass

    def _display_frame(self, frame: np.ndarray):
        """Display a frame on the video label."""
        try:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w

            # Create QImage
            q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

            # Scale to fit label while maintaining aspect ratio
            label_size = self.video_label.size()
            scaled_pixmap = QPixmap.fromImage(q_img).scaled(
                label_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation  # Use fast scaling for performance
            )

            self.video_label.setPixmap(scaled_pixmap)
        except Exception as e:
            pass  # Ignore frame display errors

    def set_selected(self, selected: bool):
        """Set selection state."""
        self.is_selected = selected
        self.setStyleSheet(get_camera_cell_style(selected=selected))

    def paintEvent(self, event):
        """Custom paint for overlay."""
        super().paintEvent(event)

        if not self.camera:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw camera name overlay at bottom
        overlay_height = 24
        overlay_rect = self.rect().adjusted(0, self.height() - overlay_height, 0, 0)

        # Semi-transparent background
        painter.fillRect(overlay_rect, QColor(0, 0, 0, 150))

        # Camera name
        painter.setPen(QColor(COLORS['text_primary']))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        painter.drawText(
            overlay_rect.adjusted(8, 0, -8, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.camera.name
        )

        # Status indicator (green = connected, red = error)
        indicator_x = overlay_rect.right() - 16
        indicator_y = overlay_rect.center().y() - 4

        if self._status == "connected":
            painter.setBrush(QColor(COLORS['online']))
        elif self._status in ("error", "failed", "disconnected"):
            painter.setBrush(QColor(COLORS['offline']))
        else:
            painter.setBrush(QColor(COLORS['warning']))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(indicator_x, indicator_y, 8, 8)

    def mousePressEvent(self, event):
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double-click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.index)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        """Show context menu."""
        menu = QMenu(self)

        if self.camera:
            snapshot_action = QAction("Take Snapshot", self)
            snapshot_action.triggered.connect(self._take_snapshot)
            menu.addAction(snapshot_action)

            menu.addSeparator()

            playback_action = QAction("Playback", self)
            menu.addAction(playback_action)

            if self.camera.has_ptz:
                ptz_action = QAction("PTZ Control", self)
                menu.addAction(ptz_action)

            menu.addSeparator()

            fullscreen_action = QAction("Fullscreen", self)
            fullscreen_action.triggered.connect(self._toggle_fullscreen)
            menu.addAction(fullscreen_action)

            menu.addSeparator()

            close_action = QAction("Close Stream", self)
            close_action.triggered.connect(self.stop_stream)
            menu.addAction(close_action)

        menu.exec(event.globalPos())

    def _take_snapshot(self):
        """Take a snapshot of current frame."""
        if self._last_frame is not None:
            # TODO: Save snapshot
            pass

    def _toggle_fullscreen(self):
        """Toggle fullscreen for this cell."""
        # TODO: Implement fullscreen
        pass


class LiveViewWidget(QWidget):
    """Widget containing grid of camera views."""

    camera_fullscreen_requested = pyqtSignal(int)  # camera_id

    def __init__(self, config, stream_manager: StreamManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.stream_manager = stream_manager
        self.cells: List[CameraViewCell] = []
        self.selected_cell: int = -1
        self.rows = 2
        self.cols = 2

        self._setup_ui()
        self.set_grid_layout(2, 2)

    def _setup_ui(self):
        """Setup UI components."""
        self.setStyleSheet(f"background-color: {COLORS['bg_dark']};")

        self.layout = QGridLayout(self)
        self.layout.setSpacing(2)
        self.layout.setContentsMargins(2, 2, 2, 2)

    def set_grid_layout(self, rows: int, cols: int):
        """Set the grid layout dimensions."""
        self.rows = rows
        self.cols = cols

        # Store cameras from existing cells
        existing_cameras = []
        for cell in self.cells:
            if cell.camera:
                existing_cameras.append(cell.camera)
            cell.stop_stream()
            cell.deleteLater()

        self.cells.clear()

        # Clear layout
        while self.layout.count():
            self.layout.takeAt(0)

        # Create new cells
        cell_index = 0
        for row in range(rows):
            for col in range(cols):
                cell = CameraViewCell(cell_index, self.stream_manager)
                cell.clicked.connect(self._on_cell_clicked)
                cell.double_clicked.connect(self._on_cell_double_clicked)

                self.layout.addWidget(cell, row, col)
                self.cells.append(cell)
                cell_index += 1

        # Set equal stretch factors
        for i in range(rows):
            self.layout.setRowStretch(i, 1)
        for i in range(cols):
            self.layout.setColumnStretch(i, 1)

        # Restore cameras to new cells
        for i, camera in enumerate(existing_cameras):
            if i < len(self.cells):
                self.cells[i].set_camera(camera)

    def add_camera_to_view(self, camera: Camera):
        """Add a camera to the next available cell or selected cell."""
        # Check if camera is already displayed
        for cell in self.cells:
            if cell.camera and cell.camera.id == camera.id:
                # Camera already shown, select that cell
                self._on_cell_clicked(cell.index)
                return

        # If a cell is selected, use that
        if 0 <= self.selected_cell < len(self.cells):
            self.cells[self.selected_cell].set_camera(camera)
            return

        # Otherwise find first empty cell
        for cell in self.cells:
            if cell.camera is None:
                cell.set_camera(camera)
                return

        # All cells full, replace first cell
        if self.cells:
            self.cells[0].set_camera(camera)

    def stop_all_streams(self):
        """Stop all active streams."""
        for cell in self.cells:
            cell.stop_stream()

    def _on_cell_clicked(self, index: int):
        """Handle cell click."""
        # Deselect previous
        if 0 <= self.selected_cell < len(self.cells):
            self.cells[self.selected_cell].set_selected(False)

        # Select new
        self.selected_cell = index
        if 0 <= index < len(self.cells):
            self.cells[index].set_selected(True)

            # Touch stream to prevent eviction
            cell = self.cells[index]
            if cell.camera:
                self.stream_manager.touch_stream(cell.camera.id)

    def _on_cell_double_clicked(self, index: int):
        """Handle cell double-click (fullscreen toggle)."""
        if 0 <= index < len(self.cells):
            cell = self.cells[index]
            if cell.camera:
                self.camera_fullscreen_requested.emit(cell.camera.id)

    def get_active_camera_count(self) -> int:
        """Get count of cells with active cameras."""
        return sum(1 for cell in self.cells if cell.camera is not None)
