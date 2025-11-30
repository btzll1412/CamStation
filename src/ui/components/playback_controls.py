"""
Playback controls for video playback.

Clean, minimal controls like UniFi Protect.
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QComboBox, QSlider, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QFont

from datetime import datetime, timedelta
from typing import Optional

from ui.styles import COLORS, get_playback_controls_style


class PlaybackControls(QWidget):
    """
    Playback control bar.

    Signals:
        play_clicked: Play button clicked
        pause_clicked: Pause button clicked
        stop_clicked: Stop button clicked
        step_forward: Step forward one frame
        step_backward: Step backward one frame
        skip_forward: Skip forward (10 seconds)
        skip_backward: Skip backward (10 seconds)
        speed_changed: Playback speed changed (float)
        volume_changed: Volume changed (0-100)
    """

    play_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    step_forward = pyqtSignal()
    step_backward = pyqtSignal()
    skip_forward = pyqtSignal()
    skip_backward = pyqtSignal()
    speed_changed = pyqtSignal(float)
    volume_changed = pyqtSignal(int)
    next_event_clicked = pyqtSignal()
    prev_event_clicked = pyqtSignal()

    SPEEDS = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0]

    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_playing = False
        self._current_time: Optional[datetime] = None
        self._total_duration: Optional[timedelta] = None

        self._setup_ui()
        self.setStyleSheet(get_playback_controls_style())

    def _setup_ui(self):
        """Setup the control UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        # Left section: Time display
        time_layout = QVBoxLayout()
        time_layout.setSpacing(0)

        self.current_time_label = QLabel("--:--:--")
        self.current_time_label.setStyleSheet(f"""
            font-size: 16px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """)
        time_layout.addWidget(self.current_time_label)

        self.duration_label = QLabel("/ --:--:--")
        self.duration_label.setStyleSheet(f"""
            font-size: 12px;
            color: {COLORS['text_secondary']};
        """)
        time_layout.addWidget(self.duration_label)

        layout.addLayout(time_layout)
        layout.addSpacing(24)

        # Center section: Playback controls
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(4)

        # Previous event
        self.prev_event_btn = self._create_control_button("", "Previous event")
        self.prev_event_btn.clicked.connect(self.prev_event_clicked)
        controls_layout.addWidget(self.prev_event_btn)

        # Step backward
        self.step_back_btn = self._create_control_button("", "Step backward")
        self.step_back_btn.clicked.connect(self.step_backward)
        controls_layout.addWidget(self.step_back_btn)

        # Skip backward
        self.skip_back_btn = self._create_control_button("", "Skip 10s back")
        self.skip_back_btn.clicked.connect(self.skip_backward)
        controls_layout.addWidget(self.skip_back_btn)

        # Play/Pause (larger)
        self.play_btn = QPushButton("")
        self.play_btn.setObjectName("play_btn")
        self.play_btn.setFixedSize(48, 48)
        self.play_btn.setToolTip("Play / Pause (Space)")
        self.play_btn.clicked.connect(self._on_play_pause)
        controls_layout.addWidget(self.play_btn)

        # Skip forward
        self.skip_fwd_btn = self._create_control_button("", "Skip 10s forward")
        self.skip_fwd_btn.clicked.connect(self.skip_forward)
        controls_layout.addWidget(self.skip_fwd_btn)

        # Step forward
        self.step_fwd_btn = self._create_control_button("", "Step forward")
        self.step_fwd_btn.clicked.connect(self.step_forward)
        controls_layout.addWidget(self.step_fwd_btn)

        # Next event
        self.next_event_btn = self._create_control_button("", "Next event")
        self.next_event_btn.clicked.connect(self.next_event_clicked)
        controls_layout.addWidget(self.next_event_btn)

        layout.addLayout(controls_layout)
        layout.addSpacing(24)

        # Speed selector
        speed_layout = QHBoxLayout()
        speed_layout.setSpacing(4)

        speed_label = QLabel("Speed:")
        speed_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        speed_layout.addWidget(speed_label)

        self.speed_combo = QComboBox()
        self.speed_combo.setObjectName("speed_selector")
        for speed in self.SPEEDS:
            self.speed_combo.addItem(f"{speed}x", speed)
        self.speed_combo.setCurrentIndex(1)  # 1.0x default
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        speed_layout.addWidget(self.speed_combo)

        layout.addLayout(speed_layout)

        # Spacer
        layout.addStretch()

        # Right section: Volume and actions
        # Volume slider
        volume_layout = QHBoxLayout()
        volume_layout.setSpacing(4)

        self.mute_btn = self._create_control_button("", "Mute")
        volume_layout.addWidget(self.mute_btn)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.valueChanged.connect(self.volume_changed)
        volume_layout.addWidget(self.volume_slider)

        layout.addLayout(volume_layout)
        layout.addSpacing(16)

        # Action buttons
        self.snapshot_btn = self._create_control_button("", "Take snapshot")
        layout.addWidget(self.snapshot_btn)

        self.export_btn = self._create_control_button("", "Export clip")
        layout.addWidget(self.export_btn)

        # Update button text (using unicode symbols as placeholder for icons)
        self._update_button_symbols()

    def _create_control_button(self, text: str, tooltip: str) -> QPushButton:
        """Create a control button."""
        btn = QPushButton(text)
        btn.setObjectName("playback_btn")
        btn.setFixedSize(40, 40)
        btn.setToolTip(tooltip)
        return btn

    def _update_button_symbols(self):
        """Update button symbols (placeholder for icons)."""
        # Using Unicode symbols as placeholders
        self.prev_event_btn.setText("\u23ee")  # ⏮
        self.step_back_btn.setText("\u23f4")  # ⏴ (frame back)
        self.skip_back_btn.setText("\u23ea")  # ⏪
        self.play_btn.setText("\u25b6")  # ▶
        self.skip_fwd_btn.setText("\u23e9")  # ⏩
        self.step_fwd_btn.setText("\u23f5")  # ⏵ (frame forward)
        self.next_event_btn.setText("\u23ed")  # ⏭
        self.mute_btn.setText("\U0001F50A")  # 🔊
        self.snapshot_btn.setText("\U0001F4F7")  # 📷
        self.export_btn.setText("\U0001F4BE")  # 💾

    def set_playing(self, is_playing: bool):
        """Set playing state."""
        self._is_playing = is_playing
        if is_playing:
            self.play_btn.setText("\u23f8")  # ⏸ Pause
        else:
            self.play_btn.setText("\u25b6")  # ▶ Play

    def set_current_time(self, time: datetime):
        """Set current time display."""
        self._current_time = time
        self.current_time_label.setText(time.strftime("%H:%M:%S"))

    def set_duration(self, duration: timedelta):
        """Set total duration."""
        self._total_duration = duration
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            self.duration_label.setText(f"/ {hours}:{minutes:02d}:{seconds:02d}")
        else:
            self.duration_label.setText(f"/ {minutes}:{seconds:02d}")

    def set_speed(self, speed: float):
        """Set speed display."""
        index = self.speed_combo.findData(speed)
        if index >= 0:
            self.speed_combo.blockSignals(True)
            self.speed_combo.setCurrentIndex(index)
            self.speed_combo.blockSignals(False)

    def _on_play_pause(self):
        """Handle play/pause button click."""
        if self._is_playing:
            self.pause_clicked.emit()
        else:
            self.play_clicked.emit()

    def _on_speed_changed(self, index: int):
        """Handle speed change."""
        speed = self.speed_combo.currentData()
        if speed:
            self.speed_changed.emit(speed)


class CompactPlaybackControls(QWidget):
    """
    Compact playback controls for overlay display.

    Smaller version that fades in on hover.
    """

    play_pause_clicked = pyqtSignal()
    position_changed = pyqtSignal(float)  # 0.0 to 1.0

    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_playing = False
        self._progress = 0.0

        self._setup_ui()

    def _setup_ui(self):
        """Setup compact UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Play/Pause
        self.play_btn = QPushButton("\u25b6")
        self.play_btn.setFixedSize(32, 32)
        self.play_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['accent_blue']};
                border: none;
                border-radius: 16px;
                color: white;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: #388bfd;
            }}
        """)
        self.play_btn.clicked.connect(self.play_pause_clicked)
        layout.addWidget(self.play_btn)

        # Progress slider
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.progress_slider)

        # Time label
        self.time_label = QLabel("0:00")
        self.time_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 12px;")
        layout.addWidget(self.time_label)

        # Background style
        self.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(13, 17, 23, 200);
                border-radius: 8px;
            }}
        """)

    def set_playing(self, is_playing: bool):
        """Set playing state."""
        self._is_playing = is_playing
        self.play_btn.setText("\u23f8" if is_playing else "\u25b6")

    def set_progress(self, progress: float, time_str: str = ""):
        """Set progress (0.0 to 1.0)."""
        self._progress = progress
        self.progress_slider.blockSignals(True)
        self.progress_slider.setValue(int(progress * 1000))
        self.progress_slider.blockSignals(False)

        if time_str:
            self.time_label.setText(time_str)

    def _on_slider_changed(self, value: int):
        """Handle slider change."""
        progress = value / 1000.0
        self.position_changed.emit(progress)
