"""
Camera cell widget for displaying a single camera stream.

Optimized for performance with 32+ cameras.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QMenu,
    QSizePolicy, QGraphicsOpacityEffect
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QPropertyAnimation,
    QEasingCurve, QSize, QPoint
)
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QFont, QPen,
    QAction, QMouseEvent, QPaintEvent, QResizeEvent
)

import cv2
import numpy as np
from typing import Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from ui.styles import COLORS, get_camera_cell_style


@dataclass
class CameraInfo:
    """Information about the camera."""
    id: int
    name: str
    device_name: str
    has_ptz: bool = False
    has_audio: bool = False
    is_recording: bool = False


class CameraCell(QWidget):
    """
    Single camera display cell.

    Features:
    - Efficient frame rendering (direct paint, no intermediate widgets)
    - Status overlays (connecting, offline, recording)
    - Hover actions (quick buttons)
    - Click/double-click handling
    """

    # Signals
    clicked = pyqtSignal(int)  # camera_id
    double_clicked = pyqtSignal(int)  # camera_id
    context_menu_requested = pyqtSignal(int, QPoint)  # camera_id, position

    # Actions
    snapshot_requested = pyqtSignal(int)
    playback_requested = pyqtSignal(int)
    ptz_requested = pyqtSignal(int)
    fullscreen_requested = pyqtSignal(int)

    def __init__(self, index: int = 0, parent=None):
        super().__init__(parent)

        self.index = index
        self._camera_info: Optional[CameraInfo] = None
        self._frame: Optional[np.ndarray] = None
        self._pixmap: Optional[QPixmap] = None
        self._status: str = "empty"  # empty, connecting, connected, error, offline
        self._is_selected: bool = False
        self._is_hovered: bool = False
        self._show_overlay: bool = True

        # Performance: cache scaled pixmap
        self._cached_size: QSize = QSize(0, 0)

        # Setup
        self.setMinimumSize(160, 90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        # Hover animation
        self._overlay_opacity = 0.0
        self._opacity_animation = QPropertyAnimation(self, b"")
        self._opacity_animation.setDuration(150)
        self._opacity_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Colors
        self._bg_color = QColor(COLORS['bg_dark'])
        self._border_color = QColor(COLORS['border'])
        self._selected_color = QColor(COLORS['accent_blue'])
        self._text_color = QColor(COLORS['text_primary'])
        self._overlay_bg = QColor(0, 0, 0, 150)

        # Context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def set_camera(self, camera_info: CameraInfo):
        """Set camera info for this cell."""
        self._camera_info = camera_info
        self._status = "connecting"
        self.update()

    def clear_camera(self):
        """Clear camera from this cell."""
        self._camera_info = None
        self._frame = None
        self._pixmap = None
        self._status = "empty"
        self.update()

    def set_frame(self, frame: np.ndarray):
        """Set a new frame to display."""
        self._frame = frame
        self._status = "connected"

        # Convert BGR to RGB
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        else:
            rgb_frame = frame

        h, w = rgb_frame.shape[:2]
        ch = rgb_frame.shape[2] if len(rgb_frame.shape) == 3 else 1

        if ch == 3:
            bytes_per_line = ch * w
            q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            self._pixmap = QPixmap.fromImage(q_img)
            self._cached_size = QSize(0, 0)  # Invalidate cache

        self.update()

    def set_status(self, status: str):
        """Set connection status."""
        self._status = status
        self.update()

    def set_selected(self, selected: bool):
        """Set selection state."""
        self._is_selected = selected
        self.update()

    @property
    def camera_id(self) -> Optional[int]:
        """Get camera ID."""
        return self._camera_info.id if self._camera_info else None

    @property
    def has_camera(self) -> bool:
        """Check if cell has a camera assigned."""
        return self._camera_info is not None

    def paintEvent(self, event: QPaintEvent):
        """Paint the cell."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()

        # Background
        painter.fillRect(rect, self._bg_color)

        # Draw frame or status
        if self._pixmap and not self._pixmap.isNull():
            self._draw_frame(painter, rect)
        else:
            self._draw_status(painter, rect)

        # Overlay (camera name, status icons)
        if self._show_overlay and self._camera_info:
            self._draw_overlay(painter, rect)

        # Border
        border_color = self._selected_color if self._is_selected else self._border_color
        border_width = 2 if self._is_selected else 1
        painter.setPen(QPen(border_color, border_width))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)

        # Hover effect
        if self._is_hovered and self._camera_info:
            self._draw_hover_actions(painter, rect)

    def _draw_frame(self, painter: QPainter, rect):
        """Draw the video frame."""
        # Scale pixmap to fit while maintaining aspect ratio
        if self._cached_size != rect.size() or self._pixmap is None:
            self._cached_size = rect.size()

        scaled = self._pixmap.scaled(
            rect.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        # Center the frame
        x = (rect.width() - scaled.width()) // 2
        y = (rect.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

    def _draw_status(self, painter: QPainter, rect):
        """Draw status message."""
        painter.setPen(self._text_color)
        font = painter.font()
        font.setPointSize(11)
        painter.setFont(font)

        status_text = {
            "empty": "No Camera",
            "connecting": "Connecting...",
            "error": "Connection Error",
            "offline": "Camera Offline",
            "connected": ""
        }.get(self._status, self._status)

        if status_text:
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, status_text)

        # Loading animation for connecting
        if self._status == "connecting":
            self._draw_loading_indicator(painter, rect)

    def _draw_loading_indicator(self, painter: QPainter, rect):
        """Draw a simple loading indicator."""
        center = rect.center()

        # Draw spinning dots
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS['accent_blue']))

        import time
        angle = (time.time() * 360) % 360

        for i in range(8):
            dot_angle = angle + i * 45
            import math
            x = center.x() + 20 * math.cos(math.radians(dot_angle))
            y = center.y() + 20 * math.sin(math.radians(dot_angle))

            opacity = (8 - i) / 8.0
            color = QColor(COLORS['accent_blue'])
            color.setAlphaF(opacity)
            painter.setBrush(color)
            painter.drawEllipse(QPoint(int(x), int(y)), 3, 3)

        # Schedule repaint for animation
        QTimer.singleShot(50, self.update)

    def _draw_overlay(self, painter: QPainter, rect):
        """Draw camera name and status overlay."""
        # Bottom overlay bar
        overlay_height = 28
        overlay_rect = rect.adjusted(0, rect.height() - overlay_height, 0, 0)

        # Semi-transparent background
        painter.fillRect(overlay_rect, self._overlay_bg)

        # Camera name
        painter.setPen(self._text_color)
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        name = self._camera_info.name if self._camera_info else ""
        painter.drawText(
            overlay_rect.adjusted(8, 0, -8, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            name
        )

        # Status indicators on right
        indicator_x = overlay_rect.right() - 12

        # Recording indicator
        if self._camera_info and self._camera_info.is_recording:
            painter.setBrush(QColor(COLORS['accent_red']))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(indicator_x - 8, overlay_rect.center().y() - 4, 8, 8)
            indicator_x -= 16

        # PTZ indicator
        if self._camera_info and self._camera_info.has_ptz:
            painter.setPen(QColor(COLORS['text_secondary']))
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(indicator_x - 20, overlay_rect.center().y() + 4, "PTZ")

    def _draw_hover_actions(self, painter: QPainter, rect):
        """Draw hover action buttons."""
        # Quick action bar at top
        action_height = 32
        action_rect = rect.adjusted(0, 0, 0, -(rect.height() - action_height))

        # Semi-transparent background
        painter.fillRect(action_rect, self._overlay_bg)

        # Action buttons (icons as text placeholders)
        buttons = [
            ("\U0001F4F7", "Snapshot"),   # 📷
            ("\u25b6", "Playback"),        # ▶
            ("\u2316", "PTZ"),             # ⌖
            ("\u26f6", "Fullscreen"),      # ⛶
        ]

        button_width = 32
        start_x = rect.center().x() - (len(buttons) * button_width) // 2

        painter.setPen(QColor(COLORS['text_primary']))
        font = painter.font()
        font.setPointSize(12)
        painter.setFont(font)

        for i, (icon, _) in enumerate(buttons):
            x = start_x + i * button_width
            painter.drawText(
                x, 0, button_width, action_height,
                Qt.AlignmentFlag.AlignCenter,
                icon
            )

    def enterEvent(self, event):
        """Handle mouse enter."""
        self._is_hovered = True
        self.update()

    def leaveEvent(self, event):
        """Handle mouse leave."""
        self._is_hovered = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._camera_info:
                self.clicked.emit(self._camera_info.id)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double click."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._camera_info:
                self.double_clicked.emit(self._camera_info.id)

    def _show_context_menu(self, position):
        """Show context menu."""
        if not self._camera_info:
            return

        menu = QMenu(self)

        # Snapshot
        snapshot_action = menu.addAction("\U0001F4F7 Take Snapshot")
        snapshot_action.triggered.connect(
            lambda: self.snapshot_requested.emit(self._camera_info.id)
        )

        menu.addSeparator()

        # Playback
        playback_action = menu.addAction("\u25b6 Playback")
        playback_action.triggered.connect(
            lambda: self.playback_requested.emit(self._camera_info.id)
        )

        # PTZ (if available)
        if self._camera_info.has_ptz:
            ptz_action = menu.addAction("\u2316 PTZ Control")
            ptz_action.triggered.connect(
                lambda: self.ptz_requested.emit(self._camera_info.id)
            )

        menu.addSeparator()

        # Fullscreen
        fullscreen_action = menu.addAction("\u26f6 Fullscreen")
        fullscreen_action.triggered.connect(
            lambda: self.fullscreen_requested.emit(self._camera_info.id)
        )

        menu.addSeparator()

        # Close
        close_action = menu.addAction("\u2715 Close Stream")
        close_action.triggered.connect(self.clear_camera)

        menu.exec(self.mapToGlobal(position))
