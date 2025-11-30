"""
Unified camera view - Digital Watchdog style.

Single view for both live and playback:
- Timeline at bottom controls live vs playback
- All cameras sync to timeline position
- Drag & drop cameras
- X to remove
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QComboBox, QFrame, QSizePolicy,
    QCalendarWidget, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QDate
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent

from typing import Optional, List
from datetime import datetime, timedelta
import json
import logging

from models.device import Camera, Device
from core.stream_manager import StreamManager
from ui.components.unified_camera_cell import UnifiedCameraCell
from ui.components.timeline import TimelineWidget
from ui.styles import COLORS

logger = logging.getLogger(__name__)


class DatePickerDialog(QDialog):
    """Calendar dialog for date selection."""

    def __init__(self, current_date: datetime, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Date")
        self.setModal(True)

        layout = QVBoxLayout(self)

        self.calendar = QCalendarWidget()
        self.calendar.setSelectedDate(QDate(current_date.year, current_date.month, current_date.day))
        self.calendar.setMaximumDate(QDate.currentDate())
        layout.addWidget(self.calendar)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_date(self) -> datetime:
        """Get selected date."""
        qdate = self.calendar.selectedDate()
        return datetime(qdate.year(), qdate.month(), qdate.day())


class UnifiedGridView(QWidget):
    """
    Unified camera grid with timeline control.

    - Timeline position determines live vs playback
    - All cameras sync to timeline
    - Seamless transition between modes
    """

    # Signals
    camera_count_changed = pyqtSignal(int)
    mode_changed = pyqtSignal(str)  # "live" or "playback"

    def __init__(self, stream_manager: StreamManager, db, config=None, parent=None):
        super().__init__(parent)
        self.stream_manager = stream_manager
        self.db = db
        self.config = config

        self.cells: List[UnifiedCameraCell] = []
        self.selected_cell: int = -1
        self.rows = 2
        self.cols = 2

        # Time range
        self._selected_date = datetime.now().date()
        self._start_time = datetime.combine(self._selected_date, datetime.min.time())
        self._end_time = datetime.now()
        self._current_position = self._end_time  # Start at "now" (live)
        self._is_live = True

        # Live threshold (seconds from now to be considered "live")
        self._live_threshold = 5

        self._setup_ui()

        # Load saved layout from config
        saved_grid = [2, 2]
        if self.config:
            saved_grid = self.config.get("layout.grid", [2, 2])
        self.set_grid_layout(saved_grid[0], saved_grid[1])

        # Load saved cameras
        self._load_layout()

        # Position update timer
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._check_live_status)
        self._update_timer.start(1000)

    def _setup_ui(self):
        """Setup UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Camera grid container
        self.grid_container = QWidget()
        self.grid_container.setStyleSheet(f"background-color: {COLORS['bg_dark']};")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(4)
        self.grid_layout.setContentsMargins(4, 4, 4, 4)
        self.grid_container.setAcceptDrops(True)
        layout.addWidget(self.grid_container, 1)

        # Bottom control bar
        self._setup_control_bar(layout)

        # Timeline
        self._setup_timeline(layout)

    def _setup_control_bar(self, parent_layout):
        """Setup playback control bar."""
        control_bar = QFrame()
        control_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_secondary']};
                border-top: 1px solid {COLORS['border']};
            }}
        """)
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(12, 8, 12, 8)
        control_layout.setSpacing(12)

        # Date picker button
        self.date_btn = QPushButton(f"📅 {datetime.now().strftime('%b %d, %Y')}")
        self.date_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_tertiary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px 12px;
                color: {COLORS['text_primary']};
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_blue']};
            }}
        """)
        self.date_btn.clicked.connect(self._show_date_picker)
        control_layout.addWidget(self.date_btn)

        control_layout.addSpacing(20)

        # Playback controls
        btn_style = f"""
            QPushButton {{
                background-color: {COLORS['bg_tertiary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px 10px;
                color: {COLORS['text_primary']};
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_blue']};
            }}
        """

        # Skip back 1min
        skip_back_btn = QPushButton("⏮")
        skip_back_btn.setToolTip("Back 1 minute")
        skip_back_btn.setStyleSheet(btn_style)
        skip_back_btn.clicked.connect(lambda: self._seek_relative(-60))
        control_layout.addWidget(skip_back_btn)

        # Step back
        step_back_btn = QPushButton("◀◀")
        step_back_btn.setToolTip("Back 10 seconds")
        step_back_btn.setStyleSheet(btn_style)
        step_back_btn.clicked.connect(lambda: self._seek_relative(-10))
        control_layout.addWidget(step_back_btn)

        # Play/Pause
        self.play_btn = QPushButton("▶")
        self.play_btn.setToolTip("Play/Pause")
        self.play_btn.setStyleSheet(btn_style)
        self.play_btn.clicked.connect(self._toggle_play)
        control_layout.addWidget(self.play_btn)

        # Step forward
        step_fwd_btn = QPushButton("▶▶")
        step_fwd_btn.setToolTip("Forward 10 seconds")
        step_fwd_btn.setStyleSheet(btn_style)
        step_fwd_btn.clicked.connect(lambda: self._seek_relative(10))
        control_layout.addWidget(step_fwd_btn)

        # Skip forward 1min
        skip_fwd_btn = QPushButton("⏭")
        skip_fwd_btn.setToolTip("Forward 1 minute")
        skip_fwd_btn.setStyleSheet(btn_style)
        skip_fwd_btn.clicked.connect(lambda: self._seek_relative(60))
        control_layout.addWidget(skip_fwd_btn)

        control_layout.addSpacing(20)

        # Speed selector
        speed_label = QLabel("Speed:")
        speed_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        control_layout.addWidget(speed_label)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "1x", "2x", "4x", "8x", "16x"])
        self.speed_combo.setCurrentText("1x")
        self.speed_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS['bg_tertiary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 4px 8px;
                color: {COLORS['text_primary']};
            }}
        """)
        control_layout.addWidget(self.speed_combo)

        control_layout.addStretch()

        # Live indicator / Go Live button
        self.live_indicator = QPushButton("● LIVE")
        self.live_indicator.setStyleSheet(f"""
            QPushButton {{
                background-color: #e53935;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                color: white;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #c62828;
            }}
        """)
        self.live_indicator.clicked.connect(self._go_live)
        control_layout.addWidget(self.live_indicator)

        parent_layout.addWidget(control_bar)

    def _setup_timeline(self, parent_layout):
        """Setup timeline widget."""
        self.timeline = TimelineWidget()
        self.timeline.position_changed.connect(self._on_timeline_seek)
        self.timeline.setFixedHeight(80)

        # Set initial time range
        self._update_time_range()

        parent_layout.addWidget(self.timeline)

    def set_grid_layout(self, rows: int, cols: int):
        """Set grid dimensions."""
        self.rows = rows
        self.cols = cols

        # Store existing cameras
        existing = []
        for cell in self.cells:
            if cell.camera and cell.device:
                existing.append((cell.camera, cell.device))
            cell.clear()
            cell.deleteLater()

        self.cells.clear()

        while self.grid_layout.count():
            self.grid_layout.takeAt(0)

        # Create cells
        idx = 0
        for row in range(rows):
            for col in range(cols):
                cell = UnifiedCameraCell(idx, self.stream_manager)
                cell.clicked.connect(self._on_cell_clicked)
                cell.double_clicked.connect(self._on_cell_double_clicked)
                cell.camera_dropped.connect(self._on_camera_dropped)
                cell.camera_swapped.connect(self._on_camera_swapped)
                cell.close_requested.connect(self._on_cell_close)
                cell.fullscreen_requested.connect(self._on_fullscreen)

                self.grid_layout.addWidget(cell, row, col)
                self.cells.append(cell)
                idx += 1

        for i in range(rows):
            self.grid_layout.setRowStretch(i, 1)
        for i in range(cols):
            self.grid_layout.setColumnStretch(i, 1)

        # Restore cameras
        for i, (camera, device) in enumerate(existing):
            if i < len(self.cells):
                self.cells[i].set_camera(camera, device)
                # Use NOW if we're in live mode
                if self._is_live:
                    self.cells[i].set_timeline_position(datetime.now(), self._start_time, datetime.now())
                else:
                    self.cells[i].set_timeline_position(self._current_position, self._start_time, self._end_time)

        self.camera_count_changed.emit(self.get_camera_count())
        self._save_layout()  # Persist grid change

    def add_camera(self, camera_id: int, cell_index: int = -1):
        """Add camera to grid."""
        camera = self.db.get_camera(camera_id)
        if not camera:
            return

        device = self.db.get_device(camera.device_id)
        if not device:
            return

        # Find target cell
        if 0 <= cell_index < len(self.cells):
            target = self.cells[cell_index]
        else:
            # Find first empty or use selected
            if 0 <= self.selected_cell < len(self.cells) and not self.cells[self.selected_cell].camera:
                target = self.cells[self.selected_cell]
            else:
                target = next((c for c in self.cells if not c.camera), None)
                if not target and self.cells:
                    target = self.cells[0]

        if target:
            target.set_camera(camera, device)
            # Sync to current timeline position - use NOW if we're in live mode
            if self._is_live:
                target.set_timeline_position(datetime.now(), self._start_time, datetime.now())
            else:
                target.set_timeline_position(self._current_position, self._start_time, self._end_time)
            self.camera_count_changed.emit(self.get_camera_count())
            self._save_layout()  # Persist layout change

    def get_camera_count(self) -> int:
        """Get number of active cameras."""
        return sum(1 for c in self.cells if c.camera)

    def _update_time_range(self):
        """Update time range for timeline."""
        # Use selected date, from midnight to now (or end of day if past)
        self._start_time = datetime.combine(self._selected_date, datetime.min.time())

        if self._selected_date == datetime.now().date():
            self._end_time = datetime.now()
        else:
            self._end_time = datetime.combine(self._selected_date, datetime.max.time().replace(microsecond=0))

        self.timeline.set_time_range(self._start_time, self._end_time)
        self.timeline.set_current_time(self._current_position)

    def _show_date_picker(self):
        """Show date picker dialog."""
        dialog = DatePickerDialog(datetime.combine(self._selected_date, datetime.min.time()), self)
        if dialog.exec():
            selected = dialog.get_date()
            self._selected_date = selected.date()
            self.date_btn.setText(f"📅 {selected.strftime('%b %d, %Y')}")

            # Update time range
            self._update_time_range()

            # If selected today, position at now; else at start
            if self._selected_date == datetime.now().date():
                self._go_live()
            else:
                self._current_position = self._start_time
                self._is_live = False
                self._seek_all(self._current_position)
                self._update_live_indicator()

    def _on_timeline_seek(self, position: datetime):
        """Handle timeline drag/click."""
        self._current_position = position
        self._check_live_status()
        self._seek_all(position)

    def _seek_all(self, position: datetime):
        """Seek all cameras to position."""
        for cell in self.cells:
            if cell.camera:
                cell.seek(position)

        self.timeline.set_current_time(position)

    def _seek_relative(self, seconds: int):
        """Seek relative to current position."""
        new_pos = self._current_position + timedelta(seconds=seconds)
        new_pos = max(self._start_time, min(self._end_time, new_pos))
        self._current_position = new_pos
        self._check_live_status()
        self._seek_all(new_pos)

    def _toggle_play(self):
        """Toggle play/pause."""
        # If live, no action needed
        if self._is_live:
            return

        # Toggle playback on all cells
        for cell in self.cells:
            if cell.camera and cell.mode == "playback":
                if cell._status == "playing":
                    cell.pause()
                else:
                    cell.play()

    def _go_live(self):
        """Jump to live (now)."""
        self._current_position = datetime.now()
        self._is_live = True
        self._seek_all(self._current_position)
        self._update_live_indicator()
        self.mode_changed.emit("live")

    def _check_live_status(self):
        """Check if we're at live position."""
        now = datetime.now()
        was_live = self._is_live
        self._is_live = (now - self._current_position).total_seconds() <= self._live_threshold

        if was_live != self._is_live:
            self._update_live_indicator()
            self.mode_changed.emit("live" if self._is_live else "playback")

        # If live, update end time
        if self._is_live and self._selected_date == datetime.now().date():
            self._end_time = now
            self._current_position = now
            self.timeline.set_time_range(self._start_time, self._end_time)
            self.timeline.set_current_time(self._current_position)

    def _update_live_indicator(self):
        """Update live indicator button."""
        if self._is_live:
            self.live_indicator.setText("● LIVE")
            self.live_indicator.setStyleSheet(f"""
                QPushButton {{
                    background-color: #e53935;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 16px;
                    color: white;
                    font-weight: bold;
                }}
            """)
        else:
            self.live_indicator.setText("Go Live")
            self.live_indicator.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg_tertiary']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 4px;
                    padding: 6px 16px;
                    color: {COLORS['text_primary']};
                }}
                QPushButton:hover {{
                    background-color: #e53935;
                    color: white;
                }}
            """)

    def _on_cell_clicked(self, index: int):
        """Handle cell click."""
        if 0 <= self.selected_cell < len(self.cells):
            self.cells[self.selected_cell].set_selected(False)
        self.selected_cell = index
        if 0 <= index < len(self.cells):
            self.cells[index].set_selected(True)

    def _on_cell_double_clicked(self, index: int):
        """Handle double click on empty cell."""
        pass  # Could show camera picker

    def _on_camera_dropped(self, cell_index: int, camera_id: int):
        """Handle camera drop."""
        self.add_camera(camera_id, cell_index)

    def _on_camera_swapped(self, from_index: int, to_index: int):
        """Handle camera swap between cells."""
        if not (0 <= from_index < len(self.cells) and 0 <= to_index < len(self.cells)):
            return

        from_cell = self.cells[from_index]
        to_cell = self.cells[to_index]

        # Store camera info from both cells
        from_camera = from_cell.camera
        from_device = from_cell.device
        to_camera = to_cell.camera
        to_device = to_cell.device

        # Clear both cells
        from_cell.clear()
        to_cell.clear()

        # Swap cameras
        if from_camera and from_device:
            to_cell.set_camera(from_camera, from_device)
            if self._is_live:
                to_cell.set_timeline_position(datetime.now(), self._start_time, datetime.now())
            else:
                to_cell.set_timeline_position(self._current_position, self._start_time, self._end_time)

        if to_camera and to_device:
            from_cell.set_camera(to_camera, to_device)
            if self._is_live:
                from_cell.set_timeline_position(datetime.now(), self._start_time, datetime.now())
            else:
                from_cell.set_timeline_position(self._current_position, self._start_time, self._end_time)

        self._save_layout()  # Persist layout change

    def _on_cell_close(self, index: int):
        """Handle cell close (X button)."""
        if 0 <= index < len(self.cells):
            camera_name = self.cells[index].camera.name if self.cells[index].camera else "unknown"
            self.cells[index].clear()
            self.camera_count_changed.emit(self.get_camera_count())
            self._save_layout()  # Persist layout change
            logger.info(f"Removed camera '{camera_name}' from cell {index}")

    def _on_fullscreen(self, camera_id: int):
        """Handle fullscreen request."""
        # Emit to parent to handle
        parent = self.window()
        if hasattr(parent, '_open_camera_fullscreen'):
            parent._open_camera_fullscreen(camera_id)

    def stop_all(self):
        """Stop all streams."""
        for cell in self.cells:
            cell.clear()

    @property
    def is_live(self) -> bool:
        return self._is_live

    def _save_layout(self):
        """Save current layout to config."""
        if not self.config:
            return

        # Build camera map: cell_index -> camera_id
        cameras = {}
        for i, cell in enumerate(self.cells):
            if cell.camera:
                cameras[str(i)] = cell.camera.id

        # Save to config
        self.config.set("layout.grid", [self.rows, self.cols])
        self.config.set("layout.cameras", cameras)
        logger.info(f"Saved layout: {self.rows}x{self.cols} grid with {len(cameras)} cameras")

    def _load_layout(self):
        """Load saved layout from config."""
        if not self.config:
            return

        cameras = self.config.get("layout.cameras", {})
        if not cameras:
            return

        logger.info(f"Loading saved layout with {len(cameras)} cameras")

        for cell_index_str, camera_id in cameras.items():
            try:
                cell_index = int(cell_index_str)
                if 0 <= cell_index < len(self.cells):
                    # Verify camera still exists in database
                    camera = self.db.get_camera(camera_id)
                    if camera:
                        device = self.db.get_device(camera.device_id)
                        if device:
                            self.cells[cell_index].set_camera(camera, device)
                            if self._is_live:
                                self.cells[cell_index].set_timeline_position(
                                    datetime.now(), self._start_time, datetime.now()
                                )
                            else:
                                self.cells[cell_index].set_timeline_position(
                                    self._current_position, self._start_time, self._end_time
                                )
                            logger.debug(f"Loaded camera {camera.name} into cell {cell_index}")
                        else:
                            logger.warning(f"Device {camera.device_id} not found for camera {camera_id}")
                    else:
                        logger.warning(f"Camera {camera_id} not found in database, removing from layout")
            except (ValueError, TypeError) as e:
                logger.error(f"Error loading camera at cell {cell_index_str}: {e}")

        self.camera_count_changed.emit(self.get_camera_count())
