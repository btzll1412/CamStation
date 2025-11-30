"""
PTZ Controls overlay for camera pan/tilt/zoom control.

Modern, floating overlay design with directional pad and zoom controls.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QSlider, QLabel, QFrame, QComboBox,
    QGraphicsDropShadowEffect, QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QPoint, QSize,
    QPropertyAnimation, QEasingCurve
)
from PyQt6.QtGui import (
    QColor, QPainter, QPainterPath, QBrush, QPen,
    QMouseEvent, QFont, QLinearGradient
)

from typing import Optional, List, Callable
from dataclasses import dataclass
from enum import Enum

from ui.styles import COLORS


class PTZDirection(Enum):
    """PTZ movement directions."""
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    UP_LEFT = "up_left"
    UP_RIGHT = "up_right"
    DOWN_LEFT = "down_left"
    DOWN_RIGHT = "down_right"
    STOP = "stop"


@dataclass
class PTZPreset:
    """PTZ preset position."""
    id: int
    name: str
    token: Optional[str] = None  # For ONVIF


class DirectionalPad(QWidget):
    """
    Circular directional pad for PTZ control.

    Features:
    - 8 directions + center stop button
    - Visual feedback on press
    - Continuous movement while pressed
    """

    direction_pressed = pyqtSignal(PTZDirection)
    direction_released = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(160, 160)
        self._pressed_direction: Optional[PTZDirection] = None
        self._hovered_direction: Optional[PTZDirection] = None

        # Colors
        self._bg_color = QColor(COLORS['bg_secondary'])
        self._btn_color = QColor(COLORS['bg_tertiary'])
        self._btn_hover = QColor(COLORS['accent_blue'])
        self._btn_pressed = QColor(COLORS['accent_blue']).darker(120)
        self._arrow_color = QColor(COLORS['text_primary'])

        self.setMouseTracking(True)

    def paintEvent(self, event):
        """Paint the directional pad."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = self.rect().center()
        radius = min(self.width(), self.height()) // 2 - 5

        # Outer circle (background)
        painter.setBrush(self._bg_color)
        painter.setPen(QPen(QColor(COLORS['border']), 2))
        painter.drawEllipse(center, radius, radius)

        # Direction segments
        directions = [
            (PTZDirection.UP, -90),
            (PTZDirection.UP_RIGHT, -45),
            (PTZDirection.RIGHT, 0),
            (PTZDirection.DOWN_RIGHT, 45),
            (PTZDirection.DOWN, 90),
            (PTZDirection.DOWN_LEFT, 135),
            (PTZDirection.LEFT, 180),
            (PTZDirection.UP_LEFT, -135),
        ]

        inner_radius = radius * 0.35
        outer_radius = radius * 0.9

        for direction, angle in directions:
            self._draw_direction_button(
                painter, center, inner_radius, outer_radius,
                angle, direction
            )

        # Center stop button
        is_center_hovered = self._hovered_direction == PTZDirection.STOP
        is_center_pressed = self._pressed_direction == PTZDirection.STOP

        center_color = self._btn_pressed if is_center_pressed else (
            self._btn_hover if is_center_hovered else self._btn_color
        )

        painter.setBrush(center_color)
        painter.setPen(QPen(QColor(COLORS['border']), 1))
        painter.drawEllipse(center, int(inner_radius - 5), int(inner_radius - 5))

        # Stop icon (square)
        stop_size = int(inner_radius * 0.5)
        stop_rect = QPoint(center.x() - stop_size // 2, center.y() - stop_size // 2)
        painter.setBrush(self._arrow_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(stop_rect.x(), stop_rect.y(), stop_size, stop_size)

    def _draw_direction_button(
        self, painter: QPainter, center: QPoint,
        inner_r: float, outer_r: float, angle: float,
        direction: PTZDirection
    ):
        """Draw a direction button segment."""
        import math

        is_hovered = self._hovered_direction == direction
        is_pressed = self._pressed_direction == direction

        color = self._btn_pressed if is_pressed else (
            self._btn_hover if is_hovered else self._btn_color
        )

        # Draw arc segment
        start_angle = angle - 22.5
        span_angle = 45

        path = QPainterPath()

        # Calculate points for the segment
        angle_rad = math.radians(angle)
        mid_r = (inner_r + outer_r) / 2

        # Arrow point
        arrow_x = center.x() + mid_r * math.cos(angle_rad)
        arrow_y = center.y() + mid_r * math.sin(angle_rad)

        # Draw a pie segment
        painter.setBrush(color)
        painter.setPen(QPen(QColor(COLORS['border']), 1))

        # Create segment path
        path = QPainterPath()
        path.moveTo(center.x() + inner_r * math.cos(math.radians(start_angle)),
                   center.y() + inner_r * math.sin(math.radians(start_angle)))

        # Outer arc
        for a in range(int(start_angle), int(start_angle + span_angle) + 1, 5):
            rad = math.radians(a)
            path.lineTo(center.x() + outer_r * math.cos(rad),
                       center.y() + outer_r * math.sin(rad))

        # Inner arc (reverse)
        for a in range(int(start_angle + span_angle), int(start_angle) - 1, -5):
            rad = math.radians(a)
            path.lineTo(center.x() + inner_r * math.cos(rad),
                       center.y() + inner_r * math.sin(rad))

        path.closeSubpath()
        painter.drawPath(path)

        # Draw arrow
        arrow_size = 8
        painter.setBrush(self._arrow_color)
        painter.setPen(Qt.PenStyle.NoPen)

        # Triangle pointing in direction
        arrow_path = QPainterPath()

        # Calculate arrow points
        perp_angle = angle_rad + math.pi / 2
        tip_x = center.x() + (mid_r + 5) * math.cos(angle_rad)
        tip_y = center.y() + (mid_r + 5) * math.sin(angle_rad)

        base_x = center.x() + (mid_r - 10) * math.cos(angle_rad)
        base_y = center.y() + (mid_r - 10) * math.sin(angle_rad)

        left_x = base_x + arrow_size * math.cos(perp_angle)
        left_y = base_y + arrow_size * math.sin(perp_angle)

        right_x = base_x - arrow_size * math.cos(perp_angle)
        right_y = base_y - arrow_size * math.sin(perp_angle)

        arrow_path.moveTo(tip_x, tip_y)
        arrow_path.lineTo(left_x, left_y)
        arrow_path.lineTo(right_x, right_y)
        arrow_path.closeSubpath()

        painter.drawPath(arrow_path)

    def _get_direction_at(self, pos: QPoint) -> Optional[PTZDirection]:
        """Get direction at mouse position."""
        import math

        center = self.rect().center()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()

        distance = math.sqrt(dx * dx + dy * dy)
        radius = min(self.width(), self.height()) // 2 - 5
        inner_radius = radius * 0.35

        # Check if in center (stop button)
        if distance < inner_radius - 5:
            return PTZDirection.STOP

        # Check if outside the pad
        if distance > radius:
            return None

        # Calculate angle
        angle = math.degrees(math.atan2(dy, dx))

        # Map angle to direction
        if -22.5 <= angle < 22.5:
            return PTZDirection.RIGHT
        elif 22.5 <= angle < 67.5:
            return PTZDirection.DOWN_RIGHT
        elif 67.5 <= angle < 112.5:
            return PTZDirection.DOWN
        elif 112.5 <= angle < 157.5:
            return PTZDirection.DOWN_LEFT
        elif angle >= 157.5 or angle < -157.5:
            return PTZDirection.LEFT
        elif -157.5 <= angle < -112.5:
            return PTZDirection.UP_LEFT
        elif -112.5 <= angle < -67.5:
            return PTZDirection.UP
        elif -67.5 <= angle < -22.5:
            return PTZDirection.UP_RIGHT

        return None

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.LeftButton:
            direction = self._get_direction_at(event.pos())
            if direction:
                self._pressed_direction = direction
                self.direction_pressed.emit(direction)
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release."""
        if self._pressed_direction:
            self._pressed_direction = None
            self.direction_released.emit()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move."""
        direction = self._get_direction_at(event.pos())
        if direction != self._hovered_direction:
            self._hovered_direction = direction
            self.update()

    def leaveEvent(self, event):
        """Handle mouse leave."""
        self._hovered_direction = None
        self.update()


class ZoomControl(QWidget):
    """
    Vertical zoom slider with + / - buttons.
    """

    zoom_in_pressed = pyqtSignal()
    zoom_out_pressed = pyqtSignal()
    zoom_released = pyqtSignal()
    zoom_level_changed = pyqtSignal(int)  # 0-100

    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_ui()

    def _setup_ui(self):
        """Setup zoom control UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Zoom in button
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFixedSize(36, 36)
        self.zoom_in_btn.setStyleSheet(self._get_button_style())
        self.zoom_in_btn.pressed.connect(self.zoom_in_pressed)
        self.zoom_in_btn.released.connect(self.zoom_released)
        layout.addWidget(self.zoom_in_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Zoom slider
        self.zoom_slider = QSlider(Qt.Orientation.Vertical)
        self.zoom_slider.setRange(0, 100)
        self.zoom_slider.setValue(50)
        self.zoom_slider.setFixedHeight(80)
        self.zoom_slider.valueChanged.connect(self.zoom_level_changed)
        self.zoom_slider.setStyleSheet(f"""
            QSlider::groove:vertical {{
                background: {COLORS['bg_tertiary']};
                width: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:vertical {{
                background: {COLORS['accent_blue']};
                height: 16px;
                margin: 0 -5px;
                border-radius: 8px;
            }}
            QSlider::handle:vertical:hover {{
                background: #388bfd;
            }}
        """)
        layout.addWidget(self.zoom_slider, alignment=Qt.AlignmentFlag.AlignCenter)

        # Zoom out button
        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.setFixedSize(36, 36)
        self.zoom_out_btn.setStyleSheet(self._get_button_style())
        self.zoom_out_btn.pressed.connect(self.zoom_out_pressed)
        self.zoom_out_btn.released.connect(self.zoom_released)
        layout.addWidget(self.zoom_out_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Label
        label = QLabel("ZOOM")
        label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 10px;
            font-weight: bold;
        """)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

    def _get_button_style(self) -> str:
        """Get button stylesheet."""
        return f"""
            QPushButton {{
                background-color: {COLORS['bg_tertiary']};
                border: 1px solid {COLORS['border']};
                border-radius: 18px;
                color: {COLORS['text_primary']};
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_blue']};
                border-color: {COLORS['accent_blue']};
            }}
            QPushButton:pressed {{
                background-color: #1a5cc7;
            }}
        """


class PTZControlsOverlay(QWidget):
    """
    Floating PTZ controls overlay.

    Features:
    - Directional pad for pan/tilt
    - Zoom controls
    - Preset positions
    - Speed control
    - Draggable positioning
    - Semi-transparent dark theme
    """

    # Movement signals
    move_start = pyqtSignal(str, float)  # direction, speed
    move_stop = pyqtSignal()
    zoom_start = pyqtSignal(str)  # "in" or "out"
    zoom_stop = pyqtSignal()

    # Preset signals
    goto_preset = pyqtSignal(int)  # preset_id
    set_preset = pyqtSignal(int, str)  # preset_id, name

    # Control signals
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._camera_id: Optional[int] = None
        self._presets: List[PTZPreset] = []
        self._speed: float = 0.5  # 0.0 to 1.0
        self._is_dragging = False
        self._drag_offset = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._setup_ui()
        self._setup_shadow()

    def _setup_ui(self):
        """Setup the UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Container frame with rounded corners
        self.container = QFrame()
        self.container.setObjectName("ptz_container")
        self.container.setStyleSheet(f"""
            QFrame#ptz_container {{
                background-color: rgba(22, 27, 34, 240);
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 8, 12, 12)
        container_layout.setSpacing(12)

        # Header with title and close button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("PTZ Control")
        title.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 13px;
            font-weight: 600;
        """)
        header_layout.addWidget(title)

        header_layout.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {COLORS['text_secondary']};
                font-size: 18px;
            }}
            QPushButton:hover {{
                color: {COLORS['text_primary']};
                background-color: {COLORS['bg_tertiary']};
                border-radius: 12px;
            }}
        """)
        close_btn.clicked.connect(self.close_requested)
        header_layout.addWidget(close_btn)

        container_layout.addLayout(header_layout)

        # Main controls area
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(16)

        # Directional pad
        self.dpad = DirectionalPad()
        self.dpad.direction_pressed.connect(self._on_direction_pressed)
        self.dpad.direction_released.connect(self._on_direction_released)
        controls_layout.addWidget(self.dpad)

        # Zoom control
        self.zoom_control = ZoomControl()
        self.zoom_control.zoom_in_pressed.connect(lambda: self.zoom_start.emit("in"))
        self.zoom_control.zoom_out_pressed.connect(lambda: self.zoom_start.emit("out"))
        self.zoom_control.zoom_released.connect(self.zoom_stop)
        controls_layout.addWidget(self.zoom_control)

        container_layout.addLayout(controls_layout)

        # Speed control
        speed_layout = QHBoxLayout()
        speed_layout.setSpacing(8)

        speed_label = QLabel("Speed:")
        speed_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        speed_layout.addWidget(speed_label)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 100)
        self.speed_slider.setValue(50)
        self.speed_slider.setFixedWidth(100)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        self.speed_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {COLORS['bg_tertiary']};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {COLORS['accent_blue']};
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
        """)
        speed_layout.addWidget(self.speed_slider)

        self.speed_value_label = QLabel("50%")
        self.speed_value_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 11px;")
        self.speed_value_label.setFixedWidth(35)
        speed_layout.addWidget(self.speed_value_label)

        speed_layout.addStretch()

        container_layout.addLayout(speed_layout)

        # Presets section
        presets_label = QLabel("Presets")
        presets_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 11px;
            font-weight: 600;
            margin-top: 4px;
        """)
        container_layout.addWidget(presets_label)

        # Preset buttons grid
        self.presets_layout = QGridLayout()
        self.presets_layout.setSpacing(4)

        # Default presets 1-8
        for i in range(8):
            btn = QPushButton(str(i + 1))
            btn.setFixedSize(32, 28)
            btn.setStyleSheet(self._get_preset_button_style())
            btn.clicked.connect(lambda checked, pid=i+1: self.goto_preset.emit(pid))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, pid=i+1, b=btn: self._show_preset_menu(pid, b, pos)
            )
            self.presets_layout.addWidget(btn, i // 4, i % 4)

        container_layout.addLayout(self.presets_layout)

        # Home button
        home_layout = QHBoxLayout()
        home_layout.setSpacing(8)

        home_btn = QPushButton("⌂ Home")
        home_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_tertiary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                color: {COLORS['text_primary']};
                padding: 6px 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_blue']};
                border-color: {COLORS['accent_blue']};
            }}
        """)
        home_btn.clicked.connect(lambda: self.goto_preset.emit(0))
        home_layout.addWidget(home_btn)

        home_layout.addStretch()

        container_layout.addLayout(home_layout)

        main_layout.addWidget(self.container)

        self.setFixedSize(240, 360)

    def _get_preset_button_style(self) -> str:
        """Get preset button stylesheet."""
        return f"""
            QPushButton {{
                background-color: {COLORS['bg_tertiary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                color: {COLORS['text_primary']};
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_blue']};
                border-color: {COLORS['accent_blue']};
            }}
            QPushButton:pressed {{
                background-color: #1a5cc7;
            }}
        """

    def _setup_shadow(self):
        """Setup drop shadow effect."""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)

    def set_camera(self, camera_id: int, presets: List[PTZPreset] = None):
        """Set the camera for PTZ control."""
        self._camera_id = camera_id

        if presets:
            self._presets = presets
            self._update_preset_buttons()

    def _update_preset_buttons(self):
        """Update preset button labels with names."""
        for i in range(self.presets_layout.count()):
            widget = self.presets_layout.itemAt(i).widget()
            if isinstance(widget, QPushButton):
                preset_id = i + 1
                preset = next((p for p in self._presets if p.id == preset_id), None)
                if preset and preset.name:
                    widget.setToolTip(preset.name)

    def _on_direction_pressed(self, direction: PTZDirection):
        """Handle direction pad press."""
        if direction == PTZDirection.STOP:
            self.move_stop.emit()
        else:
            self.move_start.emit(direction.value, self._speed)

    def _on_direction_released(self):
        """Handle direction pad release."""
        self.move_stop.emit()

    def _on_speed_changed(self, value: int):
        """Handle speed slider change."""
        self._speed = value / 100.0
        self.speed_value_label.setText(f"{value}%")

    def _show_preset_menu(self, preset_id: int, button: QPushButton, pos: QPoint):
        """Show preset context menu."""
        from PyQt6.QtWidgets import QMenu, QInputDialog

        menu = QMenu(self)

        go_action = menu.addAction(f"Go to Preset {preset_id}")
        go_action.triggered.connect(lambda: self.goto_preset.emit(preset_id))

        set_action = menu.addAction(f"Set Current Position as Preset {preset_id}")
        set_action.triggered.connect(lambda: self._set_preset_dialog(preset_id))

        menu.exec(button.mapToGlobal(pos))

    def _set_preset_dialog(self, preset_id: int):
        """Show dialog to set preset name."""
        from PyQt6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(
            self,
            "Set Preset",
            f"Name for Preset {preset_id}:",
            text=f"Preset {preset_id}"
        )

        if ok and name:
            self.set_preset.emit(preset_id, name)

    # Dragging support
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicking on header area (top 30 pixels)
            if event.pos().y() < 35:
                self._is_dragging = True
                self._drag_offset = event.pos()

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for dragging."""
        if self._is_dragging:
            new_pos = self.mapToParent(event.pos() - self._drag_offset)
            self.move(new_pos)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release."""
        self._is_dragging = False


class PTZMiniControls(QWidget):
    """
    Minimal PTZ controls that appear on camera hover.

    Just basic direction arrows in a compact horizontal layout.
    """

    direction_clicked = pyqtSignal(str)  # up, down, left, right
    expand_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_ui()

    def _setup_ui(self):
        """Setup minimal UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        buttons = [
            ("←", "left"),
            ("↑", "up"),
            ("↓", "down"),
            ("→", "right"),
        ]

        btn_style = f"""
            QPushButton {{
                background-color: rgba(22, 27, 34, 200);
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                color: {COLORS['text_primary']};
                font-size: 12px;
                padding: 4px;
                min-width: 24px;
                min-height: 24px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_blue']};
            }}
        """

        for icon, direction in buttons:
            btn = QPushButton(icon)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda checked, d=direction: self.direction_clicked.emit(d))
            layout.addWidget(btn)

        # Expand button
        expand_btn = QPushButton("⛶")
        expand_btn.setStyleSheet(btn_style)
        expand_btn.setToolTip("Open full PTZ controls")
        expand_btn.clicked.connect(self.expand_requested)
        layout.addWidget(expand_btn)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(22, 27, 34, 180);
                border-radius: 6px;
            }}
        """)
