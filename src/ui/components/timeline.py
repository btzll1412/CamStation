"""
Timeline widget for smooth scrubbing playback.

This is the UniFi Protect-style timeline with:
- Visual recording bars
- Motion/event markers
- Smooth drag-to-scrub
- Hover thumbnails
- Click-to-jump
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSizePolicy, QToolTip, QApplication
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QPoint, QRect, QSize,
    QPropertyAnimation, QEasingCurve
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QLinearGradient, QPainterPath, QImage, QPixmap,
    QMouseEvent, QWheelEvent, QPaintEvent, QResizeEvent
)

from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Callable
from dataclasses import dataclass
import numpy as np

from ui.styles import COLORS


@dataclass
class TimelineEvent:
    """Event to display on timeline."""
    start_time: datetime
    end_time: datetime
    event_type: str  # motion, line_crossing, intrusion, lpr, recording


class TimelineWidget(QWidget):
    """
    Smooth scrubbing timeline widget.

    Signals:
        position_changed: Emitted when user scrubs to new position
        zoom_changed: Emitted when zoom level changes
    """

    position_changed = pyqtSignal(datetime)  # User scrubbed to new time
    zoom_changed = pyqtSignal(float)  # Zoom level changed

    # Zoom levels in hours
    ZOOM_LEVELS = [1, 2, 6, 12, 24, 48, 168]  # 1h, 2h, 6h, 12h, 24h, 2 days, 1 week

    def __init__(self, parent=None):
        super().__init__(parent)

        # Time range
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
        self._current_time: Optional[datetime] = None
        self._visible_duration: timedelta = timedelta(hours=24)

        # View state
        self._zoom_index = 4  # Default 24h view
        self._pan_offset = 0.0  # Pixels offset from current position

        # Events and segments
        self._events: List[TimelineEvent] = []

        # Interaction state
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_time: Optional[datetime] = None
        self._hover_time: Optional[datetime] = None

        # Thumbnail callback
        self._thumbnail_callback: Optional[Callable[[datetime], Optional[np.ndarray]]] = None

        # Visual settings
        self._track_height = 40
        self._marker_height = 20
        self._padding = 16

        # Colors
        self._colors = {
            'background': QColor(COLORS['bg_dark']),
            'track': QColor(COLORS['bg_light']),
            'recording': QColor(COLORS['recording']),
            'motion': QColor(COLORS['motion']),
            'line_crossing': QColor(COLORS['accent_orange']),
            'intrusion': QColor(COLORS['accent_red']),
            'lpr': QColor(COLORS['accent_purple']),
            'playhead': QColor(COLORS['accent_blue']),
            'text': QColor(COLORS['text_secondary']),
            'text_primary': QColor(COLORS['text_primary']),
            'grid': QColor(COLORS['border']),
        }

        # Setup
        self.setMinimumHeight(80)
        self.setMaximumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Tooltip timer for thumbnail preview
        self._tooltip_timer = QTimer()
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_thumbnail_tooltip)

    def set_time_range(self, start: datetime, end: datetime):
        """Set the time range for the timeline."""
        self._start_time = start
        self._end_time = end
        if not self._current_time:
            self._current_time = start
        self.update()

    def set_current_time(self, time: datetime):
        """Set the current playback position."""
        self._current_time = time
        self.update()

    def set_events(self, events: List[TimelineEvent]):
        """Set events to display on timeline."""
        self._events = events
        self.update()

    def set_thumbnail_callback(self, callback: Callable[[datetime], Optional[np.ndarray]]):
        """Set callback for getting thumbnails."""
        self._thumbnail_callback = callback

    def get_current_time(self) -> Optional[datetime]:
        """Get current time position."""
        return self._current_time

    def zoom_in(self):
        """Zoom in (shorter time span)."""
        if self._zoom_index > 0:
            self._zoom_index -= 1
            self._visible_duration = timedelta(hours=self.ZOOM_LEVELS[self._zoom_index])
            self.zoom_changed.emit(self._visible_duration.total_seconds() / 3600)
            self.update()

    def zoom_out(self):
        """Zoom out (longer time span)."""
        if self._zoom_index < len(self.ZOOM_LEVELS) - 1:
            self._zoom_index += 1
            self._visible_duration = timedelta(hours=self.ZOOM_LEVELS[self._zoom_index])
            self.zoom_changed.emit(self._visible_duration.total_seconds() / 3600)
            self.update()

    def _time_to_x(self, time: datetime) -> float:
        """Convert time to x coordinate."""
        if not self._current_time or not self._visible_duration:
            return 0

        # Center on current time
        center_x = self.width() / 2
        visible_seconds = self._visible_duration.total_seconds()
        pixels_per_second = (self.width() - 2 * self._padding) / visible_seconds

        delta = (time - self._current_time).total_seconds()
        return center_x + delta * pixels_per_second

    def _x_to_time(self, x: float) -> Optional[datetime]:
        """Convert x coordinate to time."""
        if not self._current_time or not self._visible_duration:
            return None

        center_x = self.width() / 2
        visible_seconds = self._visible_duration.total_seconds()
        pixels_per_second = (self.width() - 2 * self._padding) / visible_seconds

        if pixels_per_second == 0:
            return None

        delta_seconds = (x - center_x) / pixels_per_second
        return self._current_time + timedelta(seconds=delta_seconds)

    def paintEvent(self, event: QPaintEvent):
        """Paint the timeline."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()

        # Background
        painter.fillRect(self.rect(), self._colors['background'])

        if not self._start_time or not self._end_time:
            self._draw_empty_state(painter)
            return

        # Draw components
        self._draw_time_grid(painter)
        self._draw_recording_track(painter)
        self._draw_events(painter)
        self._draw_playhead(painter)
        self._draw_time_labels(painter)

        # Hover indicator
        if self._hover_time and not self._dragging:
            self._draw_hover_indicator(painter)

    def _draw_empty_state(self, painter: QPainter):
        """Draw empty state when no recording is loaded."""
        painter.setPen(self._colors['text'])
        font = painter.font()
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "No recording loaded"
        )

    def _draw_time_grid(self, painter: QPainter):
        """Draw time grid lines and labels."""
        if not self._current_time:
            return

        visible_hours = self._visible_duration.total_seconds() / 3600

        # Determine grid interval based on zoom
        if visible_hours <= 2:
            interval = timedelta(minutes=15)
            label_format = "%H:%M"
        elif visible_hours <= 6:
            interval = timedelta(minutes=30)
            label_format = "%H:%M"
        elif visible_hours <= 24:
            interval = timedelta(hours=2)
            label_format = "%H:%M"
        else:
            interval = timedelta(hours=6)
            label_format = "%m/%d %H:%M"

        # Draw grid lines
        painter.setPen(QPen(self._colors['grid'], 1, Qt.PenStyle.DotLine))

        # Find first grid line
        start_visible = self._current_time - self._visible_duration / 2
        interval_seconds = interval.total_seconds()
        first_grid = datetime.fromtimestamp(
            (start_visible.timestamp() // interval_seconds + 1) * interval_seconds
        )

        end_visible = self._current_time + self._visible_duration / 2
        current = first_grid

        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)

        while current <= end_visible:
            x = self._time_to_x(current)
            if 0 <= x <= self.width():
                # Grid line
                painter.setPen(QPen(self._colors['grid'], 1, Qt.PenStyle.DotLine))
                painter.drawLine(int(x), 0, int(x), self.height() - 20)

                # Time label
                painter.setPen(self._colors['text'])
                label = current.strftime(label_format)
                painter.drawText(
                    int(x) - 30, self.height() - 5,
                    60, 20,
                    Qt.AlignmentFlag.AlignCenter,
                    label
                )

            current += interval

    def _draw_recording_track(self, painter: QPainter):
        """Draw the recording track background."""
        track_y = 20
        track_rect = QRect(
            self._padding,
            track_y,
            self.width() - 2 * self._padding,
            self._track_height
        )

        # Track background
        painter.fillRect(track_rect, self._colors['track'])

        # Draw recording segments
        for event in self._events:
            if event.event_type == 'recording':
                self._draw_segment(painter, event, track_y, self._track_height,
                                  self._colors['recording'].lighter(120))

    def _draw_events(self, painter: QPainter):
        """Draw event markers on the timeline."""
        track_y = 20
        event_height = 8

        for event in self._events:
            if event.event_type == 'recording':
                continue

            color = self._colors.get(event.event_type, self._colors['motion'])
            self._draw_segment(painter, event, track_y + 2, event_height, color)

    def _draw_segment(self, painter: QPainter, event: TimelineEvent,
                     y: int, height: int, color: QColor):
        """Draw a single segment on the timeline."""
        x1 = self._time_to_x(event.start_time)
        x2 = self._time_to_x(event.end_time)

        if x2 < 0 or x1 > self.width():
            return

        x1 = max(self._padding, x1)
        x2 = min(self.width() - self._padding, x2)
        width = max(2, x2 - x1)  # Minimum 2px width

        rect = QRect(int(x1), y, int(width), height)
        painter.fillRect(rect, color)

    def _draw_playhead(self, painter: QPainter):
        """Draw the current position playhead."""
        if not self._current_time:
            return

        x = self._time_to_x(self._current_time)

        # Playhead line
        pen = QPen(self._colors['playhead'], 2)
        painter.setPen(pen)
        painter.drawLine(int(x), 10, int(x), self.height() - 25)

        # Playhead handle (triangle)
        path = QPainterPath()
        path.moveTo(x - 8, 5)
        path.lineTo(x + 8, 5)
        path.lineTo(x, 15)
        path.closeSubpath()

        painter.fillPath(path, self._colors['playhead'])

    def _draw_time_labels(self, painter: QPainter):
        """Draw current time display."""
        if not self._current_time:
            return

        # Current time at center top
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(self._colors['text_primary'])

        time_str = self._current_time.strftime("%H:%M:%S")
        metrics = QFontMetrics(font)
        text_width = metrics.horizontalAdvance(time_str)

        x = (self.width() - text_width) // 2
        painter.drawText(x, self.height() - 25, time_str)

    def _draw_hover_indicator(self, painter: QPainter):
        """Draw hover time indicator."""
        if not self._hover_time:
            return

        x = self._time_to_x(self._hover_time)

        # Vertical line
        pen = QPen(self._colors['text'], 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(int(x), 15, int(x), self.height() - 25)

        # Time label
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(self._colors['text_primary'])

        time_str = self._hover_time.strftime("%H:%M:%S")
        painter.drawText(int(x) - 30, 5, 60, 15, Qt.AlignmentFlag.AlignCenter, time_str)

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for scrubbing."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_x = event.position().x()
            self._drag_start_time = self._current_time
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

            # Jump to clicked position
            click_time = self._x_to_time(event.position().x())
            if click_time:
                self._current_time = self._clamp_time(click_time)
                self.position_changed.emit(self._current_time)
                self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for scrubbing."""
        mouse_x = event.position().x()

        if self._dragging:
            # Scrub to new position
            new_time = self._x_to_time(mouse_x)
            if new_time:
                self._current_time = self._clamp_time(new_time)
                self.position_changed.emit(self._current_time)
                self.update()
        else:
            # Update hover time
            self._hover_time = self._x_to_time(mouse_x)
            self.update()

            # Start tooltip timer
            self._tooltip_timer.stop()
            self._tooltip_timer.start(500)  # Show after 500ms hover

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel for zooming."""
        delta = event.angleDelta().y()

        if delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def leaveEvent(self, event):
        """Handle mouse leave."""
        self._hover_time = None
        self._tooltip_timer.stop()
        self.update()

    def _clamp_time(self, time: datetime) -> datetime:
        """Clamp time to valid range."""
        if self._start_time and time < self._start_time:
            return self._start_time
        if self._end_time and time > self._end_time:
            return self._end_time
        return time

    def _show_thumbnail_tooltip(self):
        """Show thumbnail preview tooltip."""
        if not self._hover_time or not self._thumbnail_callback:
            return

        thumbnail = self._thumbnail_callback(self._hover_time)
        if thumbnail is None:
            return

        # Convert numpy array to QPixmap
        if len(thumbnail.shape) == 3:
            h, w, ch = thumbnail.shape
            if ch == 3:
                # BGR to RGB
                thumbnail = thumbnail[:, :, ::-1].copy()
                q_img = QImage(thumbnail.data, w, h, ch * w, QImage.Format.Format_RGB888)
            else:
                return
        else:
            return

        pixmap = QPixmap.fromImage(q_img)

        # Show as tooltip with image
        cursor_pos = self.mapToGlobal(QPoint(int(self._time_to_x(self._hover_time)), 0))

        # Create HTML tooltip with time and suggest looking at the thumbnail
        time_str = self._hover_time.strftime("%Y-%m-%d %H:%M:%S")
        QToolTip.showText(
            cursor_pos - QPoint(80, 100),
            f"<b>{time_str}</b>",
            self
        )
