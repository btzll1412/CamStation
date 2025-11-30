"""
Live view widget for displaying camera streams in a grid.

Digital Watchdog-style features:
- Drag & drop cameras from device tree to grid cells
- Double-click for fullscreen
- Right-click context menu
- Visual drop indicators
- Smooth 32+ camera performance
"""

from PyQt6.QtWidgets import (
    QWidget, QGridLayout, QLabel, QFrame,
    QVBoxLayout, QMenu, QSizePolicy, QScrollArea,
    QApplication, QHBoxLayout, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QMimeData
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QFont, QAction,
    QDragEnterEvent, QDropEvent, QDragLeaveEvent
)

import cv2
import numpy as np
from typing import Optional, Dict, List
from threading import Lock
import json

from models.device import Camera
from core.stream_manager import StreamManager
from ui.styles import COLORS


class CameraViewCell(QFrame):
    """Single camera view cell in the grid with drag & drop support."""

    clicked = pyqtSignal(int)  # cell_index
    double_clicked = pyqtSignal(int)  # cell_index
    camera_dropped = pyqtSignal(int, int)  # cell_index, camera_id
    fullscreen_requested = pyqtSignal(int)  # camera_id
    close_requested = pyqtSignal(int)  # cell_index

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
        self._is_drag_over = False

        self._setup_ui()

        # Accept drops
        self.setAcceptDrops(True)

        # Frame update timer (30 fps target)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_frame)

    def _setup_ui(self):
        """Setup UI components."""
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        self.setLineWidth(1)
        self._update_style()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(160, 90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Video display label
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setScaledContents(False)
        layout.addWidget(self.video_label)

        # Set empty state
        self._show_empty_state()

        # Enable mouse tracking for hover effects
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
            CameraViewCell {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 4px;
            }}
        """)

    def _show_empty_state(self):
        """Show empty cell state."""
        self.video_label.setText("")
        self.video_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_secondary']};
                background-color: {COLORS['bg_dark']};
                font-size: 12px;
            }}
        """)

        # Create empty state widget
        self.video_label.setText(
            "<div style='text-align: center;'>"
            "<p style='font-size: 24px; margin: 0;'>📷</p>"
            "<p style='margin: 8px 0 0 0; color: #6e7681;'>Drop camera here</p>"
            "<p style='margin: 4px 0 0 0; color: #484f58; font-size: 10px;'>or double-click from device tree</p>"
            "</div>"
        )

    def set_camera(self, camera: Camera):
        """Set camera for this cell and start streaming."""
        self.stop_stream()

        self.camera = camera
        self._status = "connecting"
        self.video_label.setText(f"Connecting to {camera.name}...")
        self.video_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.update()

        # Start stream using stream manager
        # Use sub-stream for grid view (lower bandwidth)
        stream_url = camera.rtsp_url_sub if hasattr(camera, 'rtsp_url_sub') and camera.rtsp_url_sub else camera.rtsp_url

        if stream_url:
            self.stream_manager.start_stream(
                camera_id=camera.id,
                url=stream_url,
                use_sub_stream=True,
                on_frame=self._on_frame_received,
                on_status=self._on_status_changed
            )

            # Start frame update timer
            self.update_timer.start(33)  # ~30 fps
        else:
            self._status = "error"
            self.video_label.setText(f"No stream URL for {camera.name}")

    def stop_stream(self):
        """Stop current stream."""
        self.update_timer.stop()

        if self.camera:
            self.stream_manager.stop_stream(self.camera.id)

        self.camera = None
        self._status = "empty"
        self._last_frame = None
        self._pixmap = None
        self.video_label.setPixmap(QPixmap())
        self._show_empty_state()
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
                self.video_label.setText(f"Connecting to {self.camera.name}...")
            elif status == "reconnecting":
                self.video_label.setText("Reconnecting...")
            elif status == "error" or status == "failed":
                self.video_label.setText("Connection Failed\nClick to retry")
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
        self._update_style(selected=selected)

    def paintEvent(self, event):
        """Custom paint for overlay."""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw drop indicator
        if self._is_drag_over:
            painter.setPen(QColor(COLORS['accent_blue']))
            painter.setBrush(QColor(47, 129, 247, 30))
            painter.drawRect(self.rect().adjusted(2, 2, -2, -2))

        if not self.camera:
            return

        # Draw camera name overlay at bottom
        overlay_height = 28
        overlay_rect = self.rect().adjusted(0, self.height() - overlay_height, 0, 0)

        # Semi-transparent background
        painter.fillRect(overlay_rect, QColor(0, 0, 0, 180))

        # Camera name
        painter.setPen(QColor(COLORS['text_primary']))
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        painter.drawText(
            overlay_rect.adjusted(10, 0, -40, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.camera.name
        )

        # Status indicator (green = connected, red = error)
        indicator_x = overlay_rect.right() - 20
        indicator_y = overlay_rect.center().y() - 5

        if self._status == "connected":
            painter.setBrush(QColor(COLORS['online']))
        elif self._status in ("error", "failed", "disconnected"):
            painter.setBrush(QColor(COLORS['offline']))
        else:
            painter.setBrush(QColor(COLORS['warning']))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(indicator_x, indicator_y, 10, 10)

    # Drag & Drop handlers
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter."""
        if event.mimeData().hasFormat("application/x-camera"):
            event.acceptProposedAction()
            self._is_drag_over = True
            self._update_style(drag_over=True)
            self.update()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        """Handle drag leave."""
        self._is_drag_over = False
        self._update_style(selected=self.is_selected)
        self.update()

    def dropEvent(self, event: QDropEvent):
        """Handle drop."""
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
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double-click for fullscreen."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.camera:
                self.fullscreen_requested.emit(self.camera.id)
            else:
                self.double_clicked.emit(self.index)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        """Show context menu."""
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
                border-radius: 2px;
            }}
            QMenu::separator {{
                height: 1px;
                background: {COLORS['border']};
                margin: 4px 8px;
            }}
        """)

        if self.camera:
            fullscreen_action = QAction("🖥️ Fullscreen", self)
            fullscreen_action.triggered.connect(lambda: self.fullscreen_requested.emit(self.camera.id))
            menu.addAction(fullscreen_action)

            menu.addSeparator()

            snapshot_action = QAction("📸 Take Snapshot", self)
            snapshot_action.triggered.connect(self._take_snapshot)
            menu.addAction(snapshot_action)

            menu.addSeparator()

            playback_action = QAction("⏪ Playback", self)
            playback_action.triggered.connect(self._open_playback)
            menu.addAction(playback_action)

            if hasattr(self.camera, 'has_ptz') and self.camera.has_ptz:
                ptz_action = QAction("🎮 PTZ Control", self)
                ptz_action.triggered.connect(self._open_ptz)
                menu.addAction(ptz_action)

            menu.addSeparator()

            close_action = QAction("❌ Close Stream", self)
            close_action.triggered.connect(lambda: self.close_requested.emit(self.index))
            menu.addAction(close_action)
        else:
            # Empty cell
            paste_action = QAction("📋 Paste Camera", self)
            paste_action.setEnabled(False)  # TODO: Implement clipboard
            menu.addAction(paste_action)

        menu.exec(event.globalPos())

    def _take_snapshot(self):
        """Take a snapshot of current frame."""
        if self._last_frame is not None and self.camera:
            from datetime import datetime
            import os

            # Create snapshots directory
            snapshot_dir = os.path.expanduser("~/Pictures/CamStation")
            os.makedirs(snapshot_dir, exist_ok=True)

            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.camera.name}_{timestamp}.jpg"
            filepath = os.path.join(snapshot_dir, filename)

            # Save snapshot
            cv2.imwrite(filepath, self._last_frame)

            # Show notification
            parent = self.window()
            if hasattr(parent, 'statusbar'):
                parent.statusbar.showMessage(f"Snapshot saved: {filepath}", 3000)

    def _open_playback(self):
        """Open playback for this camera."""
        if self.camera:
            parent = self.window()
            if hasattr(parent, '_switch_to_playback') and hasattr(parent, '_start_playback_for_camera'):
                parent._switch_to_playback()
                parent._start_playback_for_camera(self.camera)

    def _open_ptz(self):
        """Open PTZ control for this camera."""
        if self.camera:
            parent = self.window()
            if hasattr(parent, '_show_ptz_controls'):
                parent._show_ptz_controls(self.camera.id)


class FullscreenWindow(QWidget):
    """Fullscreen window for single camera view."""

    closed = pyqtSignal()

    def __init__(self, camera: Camera, stream_manager: StreamManager, parent=None):
        super().__init__(parent)
        self.camera = camera
        self.stream_manager = stream_manager

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(f"background-color: {COLORS['bg_dark']};")

        self._setup_ui()

        # Start stream
        self._start_stream()

    def _setup_ui(self):
        """Setup fullscreen UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Video label
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black;")
        layout.addWidget(self.video_label)

        # Controls overlay (bottom)
        self.controls = QWidget()
        self.controls.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(0, 0, 0, 180);
            }}
        """)
        controls_layout = QHBoxLayout(self.controls)
        controls_layout.setContentsMargins(20, 10, 20, 10)

        # Camera name
        name_label = QLabel(self.camera.name)
        name_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 16px; font-weight: bold;")
        controls_layout.addWidget(name_label)

        controls_layout.addStretch()

        # Exit button
        exit_btn = QPushButton("Exit Fullscreen (Esc)")
        exit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_tertiary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                color: {COLORS['text_primary']};
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_blue']};
            }}
        """)
        exit_btn.clicked.connect(self.close)
        controls_layout.addWidget(exit_btn)

        self.controls.setFixedHeight(60)
        layout.addWidget(self.controls)

        # Hide controls after timeout
        self._controls_timer = QTimer()
        self._controls_timer.timeout.connect(self._hide_controls)
        self._controls_timer.setSingleShot(True)

        # Frame update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_frame)

    def _start_stream(self):
        """Start fullscreen stream (main stream for quality)."""
        stream_url = self.camera.rtsp_url  # Use main stream for fullscreen

        if stream_url:
            self.stream_manager.start_stream(
                camera_id=self.camera.id,
                url=stream_url,
                use_sub_stream=False,
                on_frame=self._on_frame,
                on_status=self._on_status
            )
            self.update_timer.start(33)

    def _on_frame(self, camera_id: int, frame: np.ndarray):
        """Handle frame."""
        pass  # Frame retrieved in update

    def _on_status(self, camera_id: int, status: str):
        """Handle status."""
        if status == "error":
            self.video_label.setText("Connection Error")

    def _update_frame(self):
        """Update frame display."""
        frame = self.stream_manager.get_frame(self.camera.id)
        if frame is not None:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            q_img = QImage(rgb_frame.data, w, h, ch * w, QImage.Format.Format_RGB888)

            scaled = QPixmap.fromImage(q_img).scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.video_label.setPixmap(scaled)

    def _hide_controls(self):
        """Hide controls overlay."""
        self.controls.hide()

    def _show_controls(self):
        """Show controls overlay."""
        self.controls.show()
        self._controls_timer.start(3000)

    def mouseMoveEvent(self, event):
        """Show controls on mouse move."""
        self._show_controls()
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        """Handle key press."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)

    def closeEvent(self, event):
        """Handle close."""
        self.update_timer.stop()
        self.closed.emit()
        super().closeEvent(event)


class LiveViewWidget(QWidget):
    """Widget containing grid of camera views with drag & drop."""

    camera_fullscreen_requested = pyqtSignal(int)  # camera_id

    def __init__(self, config, stream_manager: StreamManager, db=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.stream_manager = stream_manager
        self.db = db
        self.cells: List[CameraViewCell] = []
        self.selected_cell: int = -1
        self.rows = 2
        self.cols = 2
        self._fullscreen_window: Optional[FullscreenWindow] = None

        self._setup_ui()
        self.set_grid_layout(2, 2)

    def _setup_ui(self):
        """Setup UI components."""
        self.setStyleSheet(f"background-color: {COLORS['bg_dark']};")
        self.setAcceptDrops(True)

        self.layout = QGridLayout(self)
        self.layout.setSpacing(4)
        self.layout.setContentsMargins(4, 4, 4, 4)

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
                cell.camera_dropped.connect(self._on_camera_dropped)
                cell.fullscreen_requested.connect(self._on_fullscreen_requested)
                cell.close_requested.connect(self._on_close_requested)

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

    def add_camera_to_view(self, camera: Camera, cell_index: int = -1):
        """Add a camera to a specific cell or next available."""
        # Check if camera is already displayed
        for cell in self.cells:
            if cell.camera and cell.camera.id == camera.id:
                # Camera already shown, select that cell
                self._on_cell_clicked(cell.index)
                return

        # Use specified cell index
        if 0 <= cell_index < len(self.cells):
            self.cells[cell_index].set_camera(camera)
            return

        # If a cell is selected, use that
        if 0 <= self.selected_cell < len(self.cells):
            if self.cells[self.selected_cell].camera is None:
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

    def add_camera_by_id(self, camera_id: int, cell_index: int = -1):
        """Add camera by ID (for drag & drop)."""
        if self.db:
            camera = self.db.get_camera(camera_id)
            if camera:
                self.add_camera_to_view(camera, cell_index)

    def open_fullscreen(self, camera_id: int):
        """Open camera in fullscreen window."""
        if self.db:
            camera = self.db.get_camera(camera_id)
            if camera:
                self._show_fullscreen(camera)

    def _show_fullscreen(self, camera: Camera):
        """Show fullscreen window for camera."""
        if self._fullscreen_window:
            self._fullscreen_window.close()

        self._fullscreen_window = FullscreenWindow(camera, self.stream_manager)
        self._fullscreen_window.closed.connect(self._on_fullscreen_closed)
        self._fullscreen_window.showFullScreen()

    def _on_fullscreen_closed(self):
        """Handle fullscreen window closed."""
        self._fullscreen_window = None

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
        """Handle cell double-click (open camera picker or fullscreen)."""
        if 0 <= index < len(self.cells):
            cell = self.cells[index]
            if cell.camera:
                self._show_fullscreen(cell.camera)

    def _on_camera_dropped(self, cell_index: int, camera_id: int):
        """Handle camera dropped on cell."""
        self.add_camera_by_id(camera_id, cell_index)

    def _on_fullscreen_requested(self, camera_id: int):
        """Handle fullscreen request."""
        if self.db:
            camera = self.db.get_camera(camera_id)
            if camera:
                self._show_fullscreen(camera)

    def _on_close_requested(self, cell_index: int):
        """Handle close stream request."""
        if 0 <= cell_index < len(self.cells):
            self.cells[cell_index].stop_stream()

    def get_active_camera_count(self) -> int:
        """Get count of cells with active cameras."""
        return sum(1 for cell in self.cells if cell.camera is not None)

    # Handle drops on the widget itself (not on cells)
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter on main widget."""
        if event.mimeData().hasFormat("application/x-camera"):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """Handle drop on main widget - add to first empty cell."""
        if event.mimeData().hasFormat("application/x-camera"):
            data = event.mimeData().data("application/x-camera")
            camera_data = json.loads(bytes(data).decode())
            camera_id = camera_data.get("camera_id")

            if camera_id:
                self.add_camera_by_id(camera_id)
                event.acceptProposedAction()
