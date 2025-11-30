"""
LPR (License Plate Recognition) search dialog.

Features:
- Search by plate number (with wildcards)
- Date range filter
- Camera filter
- Direction filter (in/out)
- Results table with thumbnails
- Export to CSV
- View capture image
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QPushButton, QLabel,
    QGroupBox, QTableWidget, QTableWidgetItem,
    QDateTimeEdit, QHeaderView, QMessageBox,
    QFileDialog, QSplitter, QFrame, QSizePolicy,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, QDateTime, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

from datetime import datetime, timedelta
from typing import List, Dict, Optional
import csv
import os

from utils.database import Database
from ui.styles import COLORS


class LPRSearchThread(QThread):
    """Thread for searching LPR events."""

    finished = pyqtSignal(list)  # List of events
    progress = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, db: Database, start_time: datetime, end_time: datetime,
                 plate_number: str = None, camera_id: int = None,
                 direction: str = None, limit: int = 500):
        super().__init__()
        self.db = db
        self.start_time = start_time
        self.end_time = end_time
        self.plate_number = plate_number
        self.camera_id = camera_id
        self.direction = direction
        self.limit = limit

    def run(self):
        try:
            self.progress.emit("Searching...")

            results = self.db.search_lpr_events(
                start_time=self.start_time,
                end_time=self.end_time,
                plate_number=self.plate_number,
                camera_id=self.camera_id,
                direction=self.direction,
                limit=self.limit
            )

            self.finished.emit(results)

        except Exception as e:
            self.error.emit(str(e))


class LPRSearchDialog(QDialog):
    """Dialog for searching LPR events."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._results: List[Dict] = []

        self._setup_ui()
        self._load_cameras()

    def _setup_ui(self):
        self.setWindowTitle("LPR Plate Search")
        self.setMinimumSize(900, 600)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Search filters
        filter_group = QGroupBox("Search Filters")
        filter_layout = QHBoxLayout(filter_group)

        # Left column
        left_form = QFormLayout()
        left_form.setSpacing(8)

        self.plate_input = QLineEdit()
        self.plate_input.setPlaceholderText("ABC123 or *123* (wildcards supported)")
        self.plate_input.returnPressed.connect(self._on_search)
        left_form.addRow("Plate Number:", self.plate_input)

        self.camera_combo = QComboBox()
        self.camera_combo.addItem("All Cameras", None)
        left_form.addRow("Camera:", self.camera_combo)

        filter_layout.addLayout(left_form)

        # Right column
        right_form = QFormLayout()
        right_form.setSpacing(8)

        # Date range
        self.start_datetime = QDateTimeEdit()
        self.start_datetime.setDateTime(QDateTime.currentDateTime().addDays(-7))
        self.start_datetime.setCalendarPopup(True)
        right_form.addRow("From:", self.start_datetime)

        self.end_datetime = QDateTimeEdit()
        self.end_datetime.setDateTime(QDateTime.currentDateTime())
        self.end_datetime.setCalendarPopup(True)
        right_form.addRow("To:", self.end_datetime)

        filter_layout.addLayout(right_form)

        # Direction filter
        dir_form = QFormLayout()
        dir_form.setSpacing(8)

        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Any Direction", "In", "Out"])
        dir_form.addRow("Direction:", self.direction_combo)

        # Quick date buttons
        quick_layout = QHBoxLayout()
        for text, days in [("Today", 0), ("Yesterday", 1), ("Last 7 Days", 7), ("Last 30 Days", 30)]:
            btn = QPushButton(text)
            btn.setFixedWidth(80)
            btn.clicked.connect(lambda checked, d=days: self._set_quick_date(d))
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        dir_form.addRow("Quick:", quick_layout)

        filter_layout.addLayout(dir_form)

        layout.addWidget(filter_group)

        # Search button and status
        search_layout = QHBoxLayout()

        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("primary")
        self.search_btn.setFixedWidth(120)
        self.search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(self.search_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        search_layout.addWidget(self.status_label)

        search_layout.addStretch()

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_export)
        search_layout.addWidget(self.export_btn)

        layout.addLayout(search_layout)

        # Results splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels([
            "Plate", "Time", "Camera", "Direction", "Confidence", "Vehicle", "Color"
        ])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.results_table.doubleClicked.connect(self._on_row_double_clicked)

        splitter.addWidget(self.results_table)

        # Preview panel
        preview_frame = QFrame()
        preview_frame.setMinimumWidth(250)
        preview_frame.setMaximumWidth(350)
        preview_frame.setStyleSheet(f"background-color: {COLORS['bg_light']}; border-radius: 8px;")

        preview_layout = QVBoxLayout(preview_frame)

        preview_title = QLabel("Event Details")
        preview_title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {COLORS['text_primary']};")
        preview_layout.addWidget(preview_title)

        # Plate display
        self.plate_label = QLabel("---")
        self.plate_label.setStyleSheet(f"""
            font-size: 28px;
            font-weight: bold;
            font-family: monospace;
            color: {COLORS['text_primary']};
            background-color: {COLORS['bg_dark']};
            padding: 16px;
            border-radius: 8px;
            text-align: center;
        """)
        self.plate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.plate_label)

        # Details
        self.detail_time = QLabel("Time: ---")
        self.detail_camera = QLabel("Camera: ---")
        self.detail_direction = QLabel("Direction: ---")
        self.detail_confidence = QLabel("Confidence: ---")
        self.detail_vehicle = QLabel("Vehicle: ---")

        for label in [self.detail_time, self.detail_camera, self.detail_direction,
                      self.detail_confidence, self.detail_vehicle]:
            label.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 4px;")
            preview_layout.addWidget(label)

        # Snapshot preview
        self.snapshot_label = QLabel("No snapshot")
        self.snapshot_label.setMinimumHeight(150)
        self.snapshot_label.setStyleSheet(f"""
            background-color: {COLORS['bg_dark']};
            border-radius: 8px;
            color: {COLORS['text_muted']};
        """)
        self.snapshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.snapshot_label)

        # Action buttons
        action_layout = QHBoxLayout()

        self.playback_btn = QPushButton("View Playback")
        self.playback_btn.setEnabled(False)
        action_layout.addWidget(self.playback_btn)

        self.view_image_btn = QPushButton("Full Image")
        self.view_image_btn.setEnabled(False)
        action_layout.addWidget(self.view_image_btn)

        preview_layout.addLayout(action_layout)
        preview_layout.addStretch()

        splitter.addWidget(preview_frame)
        splitter.setSizes([600, 300])

        layout.addWidget(splitter)

        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_layout.addWidget(close_btn)

        layout.addLayout(close_layout)

    def _load_cameras(self):
        """Load cameras into dropdown."""
        try:
            devices = self.db.get_all_devices()
            for device in devices:
                for camera in device.cameras:
                    if camera.has_lpr:
                        self.camera_combo.addItem(
                            f"{device.name} - {camera.name}",
                            camera.id
                        )
        except Exception as e:
            pass

    def _set_quick_date(self, days_ago: int):
        """Set quick date range."""
        now = QDateTime.currentDateTime()

        if days_ago == 0:
            # Today
            start = QDateTime(now.date())
            self.start_datetime.setDateTime(start)
        elif days_ago == 1:
            # Yesterday
            start = QDateTime(now.date().addDays(-1))
            end = QDateTime(now.date())
            self.start_datetime.setDateTime(start)
            self.end_datetime.setDateTime(end)
            return
        else:
            self.start_datetime.setDateTime(now.addDays(-days_ago))

        self.end_datetime.setDateTime(now)

    def _on_search(self):
        """Perform search."""
        # Get filter values
        start_time = self.start_datetime.dateTime().toPyDateTime()
        end_time = self.end_datetime.dateTime().toPyDateTime()

        plate_number = self.plate_input.text().strip() or None
        camera_id = self.camera_combo.currentData()

        direction = None
        dir_text = self.direction_combo.currentText().lower()
        if dir_text in ('in', 'out'):
            direction = dir_text

        # Clear table
        self.results_table.setRowCount(0)
        self.status_label.setText("Searching...")
        self.search_btn.setEnabled(False)

        # Start search thread
        self._search_thread = LPRSearchThread(
            self.db, start_time, end_time,
            plate_number, camera_id, direction
        )
        self._search_thread.finished.connect(self._on_search_finished)
        self._search_thread.error.connect(self._on_search_error)
        self._search_thread.start()

    def _on_search_finished(self, results: List[Dict]):
        """Handle search results."""
        self._results = results
        self.search_btn.setEnabled(True)

        count = len(results)
        self.status_label.setText(f"Found {count} result{'s' if count != 1 else ''}")
        self.export_btn.setEnabled(count > 0)

        # Populate table
        self.results_table.setRowCount(count)

        for row, event in enumerate(results):
            # Plate number
            plate_item = QTableWidgetItem(event['plate_number'])
            plate_item.setFont(self.results_table.font())
            plate_item.setData(Qt.ItemDataRole.UserRole, event)
            self.results_table.setItem(row, 0, plate_item)

            # Time
            time_str = event['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
            self.results_table.setItem(row, 1, QTableWidgetItem(time_str))

            # Camera
            self.results_table.setItem(row, 2, QTableWidgetItem(event['camera_name']))

            # Direction
            direction = event.get('direction', '-') or '-'
            self.results_table.setItem(row, 3, QTableWidgetItem(direction.upper() if direction != '-' else '-'))

            # Confidence
            confidence = event.get('confidence', 0) or 0
            self.results_table.setItem(row, 4, QTableWidgetItem(f"{confidence:.0%}"))

            # Vehicle type
            vehicle = event.get('vehicle_type', '-') or '-'
            self.results_table.setItem(row, 5, QTableWidgetItem(vehicle))

            # Vehicle color
            color = event.get('vehicle_color', '-') or '-'
            self.results_table.setItem(row, 6, QTableWidgetItem(color))

    def _on_search_error(self, error: str):
        """Handle search error."""
        self.search_btn.setEnabled(True)
        self.status_label.setText(f"Error: {error}")
        QMessageBox.critical(self, "Search Error", f"Failed to search: {error}")

    def _on_selection_changed(self):
        """Handle row selection."""
        rows = self.results_table.selectedItems()
        if not rows:
            self._clear_preview()
            return

        row = rows[0].row()
        if row < len(self._results):
            event = self._results[row]
            self._show_preview(event)

    def _show_preview(self, event: Dict):
        """Show event preview."""
        self.plate_label.setText(event['plate_number'])

        time_str = event['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
        self.detail_time.setText(f"Time: {time_str}")
        self.detail_camera.setText(f"Camera: {event['camera_name']}")

        direction = event.get('direction', 'Unknown') or 'Unknown'
        self.detail_direction.setText(f"Direction: {direction.upper()}")

        confidence = event.get('confidence', 0) or 0
        self.detail_confidence.setText(f"Confidence: {confidence:.0%}")

        vehicle = event.get('vehicle_type', 'Unknown') or 'Unknown'
        color = event.get('vehicle_color', '') or ''
        if color:
            self.detail_vehicle.setText(f"Vehicle: {color} {vehicle}")
        else:
            self.detail_vehicle.setText(f"Vehicle: {vehicle}")

        # Load snapshot if available
        snapshot_path = event.get('snapshot_path')
        if snapshot_path and os.path.exists(snapshot_path):
            pixmap = QPixmap(snapshot_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.snapshot_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.snapshot_label.setPixmap(scaled)
                self.view_image_btn.setEnabled(True)
            else:
                self.snapshot_label.setText("Failed to load image")
                self.view_image_btn.setEnabled(False)
        else:
            self.snapshot_label.setText("No snapshot available")
            self.view_image_btn.setEnabled(False)

        self.playback_btn.setEnabled(True)

    def _clear_preview(self):
        """Clear preview panel."""
        self.plate_label.setText("---")
        self.detail_time.setText("Time: ---")
        self.detail_camera.setText("Camera: ---")
        self.detail_direction.setText("Direction: ---")
        self.detail_confidence.setText("Confidence: ---")
        self.detail_vehicle.setText("Vehicle: ---")
        self.snapshot_label.setText("No snapshot")
        self.snapshot_label.setPixmap(QPixmap())
        self.playback_btn.setEnabled(False)
        self.view_image_btn.setEnabled(False)

    def _on_row_double_clicked(self, index):
        """Handle double-click on row."""
        # Could open playback at this timestamp
        pass

    def _on_export(self):
        """Export results to CSV."""
        if not self._results:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export LPR Results", "lpr_export.csv",
            "CSV Files (*.csv)"
        )

        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Header
                writer.writerow([
                    'Plate Number', 'Date/Time', 'Camera', 'Direction',
                    'Confidence', 'Vehicle Type', 'Vehicle Color', 'Plate Color'
                ])

                # Data
                for event in self._results:
                    writer.writerow([
                        event['plate_number'],
                        event['timestamp'].strftime("%Y-%m-%d %H:%M:%S"),
                        event['camera_name'],
                        event.get('direction', ''),
                        f"{(event.get('confidence', 0) or 0):.0%}",
                        event.get('vehicle_type', ''),
                        event.get('vehicle_color', ''),
                        event.get('plate_color', '')
                    ])

            QMessageBox.information(
                self, "Export Complete",
                f"Exported {len(self._results)} records to:\n{file_path}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export: {e}")
