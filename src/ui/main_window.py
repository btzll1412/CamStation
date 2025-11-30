"""
Main application window for CamStation.

Digital Watchdog-style unified interface:
- Single view for live and playback (no mode switching)
- Timeline at bottom controls live vs playback
- Drag & drop cameras from device tree
- All cameras sync to timeline position
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QStatusBar, QMenu, QMessageBox, QDockWidget,
    QLabel, QPushButton, QSizePolicy, QApplication
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QAction, QKeySequence

from typing import Optional
from datetime import datetime

from ui.styles import get_stylesheet, COLORS
from ui.device_tree import DeviceTreeWidget
from ui.unified_view import UnifiedGridView
from ui.dialogs.add_device_dialog import AddDeviceDialog
from utils.config import Config
from utils.database import Database
from core.stream_manager import StreamManager


class MainWindow(QMainWindow):
    """Main application window with unified live/playback view."""

    def __init__(self, config: Config, db: Database):
        super().__init__()
        self.config = config
        self.db = db

        # Core services
        self.stream_manager = StreamManager(max_streams=32)

        # State
        self._selected_camera_id: Optional[int] = None

        # Setup
        self.setWindowTitle("CamStation")
        self.setMinimumSize(1200, 800)

        # Apply stylesheet
        self.setStyleSheet(get_stylesheet())

        # Restore window geometry
        self._restore_geometry()

        # Setup UI
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_dock_widgets()
        self._setup_statusbar()
        self._setup_shortcuts()

        # Load devices
        self._load_devices()

        # Status update timer
        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(1000)

    def _setup_menubar(self):
        """Setup the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        add_device_action = QAction("&Add Device...", self)
        add_device_action.setShortcut(QKeySequence("Ctrl+N"))
        add_device_action.triggered.connect(self._on_add_device)
        file_menu.addAction(add_device_action)

        file_menu.addSeparator()

        settings_action = QAction("&Settings...", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._on_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        # Grid layouts
        for size in [1, 2, 3, 4, 5, 6]:
            action = QAction(f"&{size}x{size} Grid", self)
            action.setShortcut(str(size))
            action.triggered.connect(lambda checked, s=size: self._set_grid_layout(s, s))
            view_menu.addAction(action)

        view_menu.addSeparator()

        fullscreen_action = QAction("&Fullscreen", self)
        fullscreen_action.setShortcut(QKeySequence("F11"))
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(fullscreen_action)

        # Events menu
        events_menu = menubar.addMenu("&Events")

        motion_events_action = QAction("&Motion Events...", self)
        motion_events_action.triggered.connect(self._on_motion_events)
        events_menu.addAction(motion_events_action)

        lpr_search_action = QAction("&LPR Plate Search...", self)
        lpr_search_action.setShortcut(QKeySequence("Ctrl+P"))
        lpr_search_action.triggered.connect(self._on_lpr_search)
        events_menu.addAction(lpr_search_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        shortcuts_action = QAction("&Keyboard Shortcuts", self)
        shortcuts_action.setShortcut(QKeySequence("?"))
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)

        help_menu.addSeparator()

        about_action = QAction("&About CamStation", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self):
        """Setup the main toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        # Add device button
        add_device_btn = QPushButton("+ Add Device")
        add_device_btn.setObjectName("primary")
        add_device_btn.setToolTip("Add a new camera or NVR")
        add_device_btn.clicked.connect(self._on_add_device)
        toolbar.addWidget(add_device_btn)

        toolbar.addSeparator()

        # Grid layout buttons
        grid_sizes = [(1, "1x1"), (2, "2x2"), (3, "3x3"), (4, "4x4"), (5, "5x5")]
        for size, label in grid_sizes:
            btn = QPushButton(label)
            btn.setToolTip(f"{label} grid view")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, s=size: self._set_grid_layout(s, s))
            toolbar.addWidget(btn)
            if size == 2:  # Default selection
                btn.setChecked(True)

        toolbar.addSeparator()

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Search
        from PyQt6.QtWidgets import QLineEdit
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search cameras...")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search_input)

    def _setup_central_widget(self):
        """Setup the central widget with unified grid view."""
        # Unified view (combines live + playback with timeline)
        self.unified_view = UnifiedGridView(self.stream_manager, self.db)
        self.unified_view.camera_count_changed.connect(self._on_camera_count_changed)
        self.unified_view.mode_changed.connect(self._on_mode_changed)

        self.setCentralWidget(self.unified_view)

    def _setup_dock_widgets(self):
        """Setup dock widgets (device tree)."""
        # Device tree dock
        device_dock = QDockWidget("Devices", self)
        device_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        device_dock.setMinimumWidth(250)
        device_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self.device_tree = DeviceTreeWidget(self.db)
        self.device_tree.camera_selected.connect(self._on_camera_selected)
        self.device_tree.camera_double_clicked.connect(self._on_camera_double_clicked)
        self.device_tree.add_all_cameras.connect(self._on_add_all_cameras)
        device_dock.setWidget(self.device_tree)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, device_dock)

    def _setup_statusbar(self):
        """Setup the status bar."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)

        # Camera count
        self.camera_count_label = QLabel("Cameras: 0")
        self.statusbar.addWidget(self.camera_count_label)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.statusbar.addWidget(spacer)

        # Mode indicator
        self.mode_label = QLabel("LIVE")
        self.mode_label.setStyleSheet(f"color: #e53935; font-weight: bold;")
        self.statusbar.addPermanentWidget(self.mode_label)

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        from PyQt6.QtGui import QShortcut

        # Space for play/pause (when in playback)
        play_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        play_shortcut.activated.connect(self._toggle_play_pause)

        # Arrow keys for seeking
        left_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        left_shortcut.activated.connect(lambda: self.unified_view._seek_relative(-10))

        right_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        right_shortcut.activated.connect(lambda: self.unified_view._seek_relative(10))

        # L for live
        live_shortcut = QShortcut(QKeySequence("L"), self)
        live_shortcut.activated.connect(self.unified_view._go_live)

        # Escape for exit fullscreen
        escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        escape_shortcut.activated.connect(self._exit_fullscreen)

    def _restore_geometry(self):
        """Restore window geometry from config."""
        geometry = self.config.get("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1400, 900)
            screen = QApplication.primaryScreen().geometry()
            self.move(
                (screen.width() - self.width()) // 2,
                (screen.height() - self.height()) // 2
            )

    def _save_geometry(self):
        """Save window geometry to config."""
        self.config.set("window_geometry", self.saveGeometry())

    def _load_devices(self):
        """Load devices from database into tree."""
        devices = self.db.get_all_devices()
        self.device_tree.load_devices(devices)

    def _update_status(self):
        """Update status bar."""
        count = self.unified_view.get_camera_count()
        self.camera_count_label.setText(f"Cameras: {count}")

    # === Event Handlers ===

    def _on_add_device(self):
        """Handle add device action."""
        dialog = AddDeviceDialog(self)
        if dialog.exec():
            device_info = dialog.get_device_info()
            if device_info:
                self._add_device_to_database(device_info)

    def _add_device_to_database(self, device_info: dict):
        """Add a discovered device to the database."""
        from models.device import Device, Camera

        info = device_info.get("device_info", {})
        channels = device_info.get("channels", [])

        device = Device(
            id=0,
            name=info.get("name", device_info["ip"]),
            ip_address=device_info["ip"],
            port=device_info["port"],
            username=device_info["username"],
            password=device_info["password"] if device_info.get("save_password") else "",
            device_type=info.get("device_type", "unknown"),
            model=info.get("model"),
            serial_number=info.get("serial_number"),
            firmware_version=info.get("firmware_version"),
            max_channels=len(channels)
        )

        for ch in channels:
            camera = Camera(
                id=0,
                device_id=0,
                channel_number=ch.get("channel_number", 1),
                name=ch.get("name", f"Channel {ch.get('channel_number', 1)}"),
                rtsp_url="",
                is_online=ch.get("enabled", True)
            )
            device.cameras.append(camera)

        try:
            device_id = self.db.add_device(device)
            self._load_devices()
            self.statusbar.showMessage(f"Added device: {device.name}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add device: {e}")

    def _on_settings(self):
        """Handle settings action."""
        self.statusbar.showMessage("Settings coming soon", 2000)

    def _on_motion_events(self):
        """Handle motion events action."""
        self.statusbar.showMessage("Motion events coming soon", 2000)

    def _on_lpr_search(self):
        """Handle LPR search action."""
        from ui.dialogs import LPRSearchDialog
        dialog = LPRSearchDialog(self.db, self)
        dialog.exec()

    def _on_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About CamStation",
            "<h2>CamStation</h2>"
            "<p>Version 0.2.0</p>"
            "<p>A lightweight, fast camera management application.</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>Unified live + playback view</li>"
            "<li>Multi-site synchronized playback</li>"
            "<li>Drag & drop camera management</li>"
            "<li>Timeline scrubbing</li>"
            "</ul>"
        )

    def _show_shortcuts(self):
        """Show keyboard shortcuts help."""
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            "<h3>Navigation</h3>"
            "<p><b>1-6</b> - Switch grid layout</p>"
            "<p><b>F11</b> - Toggle fullscreen</p>"
            "<p><b>Escape</b> - Exit fullscreen</p>"
            "<h3>Playback</h3>"
            "<p><b>Space</b> - Play/Pause</p>"
            "<p><b>Left/Right</b> - Seek 10 seconds</p>"
            "<p><b>L</b> - Go to Live</p>"
            "<h3>General</h3>"
            "<p><b>Ctrl+N</b> - Add device</p>"
        )

    def _on_camera_selected(self, camera_id: int):
        """Handle camera selection in device tree."""
        self._selected_camera_id = camera_id

    def _on_camera_double_clicked(self, camera_id: int):
        """Handle camera double-click to add to view."""
        self.unified_view.add_camera(camera_id)

    def _on_add_all_cameras(self, device_id: int):
        """Add all cameras from a device."""
        device = self.db.get_device(device_id)
        if device:
            for camera in device.cameras:
                self.unified_view.add_camera(camera.id)

    def _on_camera_count_changed(self, count: int):
        """Handle camera count change."""
        self.camera_count_label.setText(f"Cameras: {count}")

    def _on_mode_changed(self, mode: str):
        """Handle mode change (live/playback)."""
        if mode == "live":
            self.mode_label.setText("LIVE")
            self.mode_label.setStyleSheet("color: #e53935; font-weight: bold;")
        else:
            self.mode_label.setText("PLAYBACK")
            self.mode_label.setStyleSheet(f"color: {COLORS['accent_blue']}; font-weight: bold;")

    def _open_camera_fullscreen(self, camera_id: int):
        """Open a camera in fullscreen mode."""
        from ui.live_view import FullscreenWindow
        camera = self.db.get_camera(camera_id)
        if camera:
            self._fullscreen_window = FullscreenWindow(camera, self.stream_manager)
            self._fullscreen_window.showFullScreen()

    def _show_ptz_controls(self, camera_id: int):
        """Show PTZ controls for a camera."""
        from ui.components import PTZControlsOverlay

        if not hasattr(self, '_ptz_overlay') or self._ptz_overlay is None:
            self._ptz_overlay = PTZControlsOverlay(self)
            self._ptz_overlay.close_requested.connect(lambda: self._ptz_overlay.hide())

        self._ptz_overlay.set_camera(camera_id)
        self._ptz_overlay.show()
        self._ptz_overlay.move(self.width() - 260, self.height() - 460)

    def _set_grid_layout(self, rows: int, cols: int):
        """Set the grid layout."""
        self.unified_view.set_grid_layout(rows, cols)
        self.statusbar.showMessage(f"View: {rows}x{cols} grid", 2000)

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _exit_fullscreen(self):
        """Exit fullscreen mode."""
        if self.isFullScreen():
            self.showNormal()

    def _toggle_play_pause(self):
        """Toggle play/pause."""
        self.unified_view._toggle_play()

    def _on_search(self, text: str):
        """Handle search input."""
        self.device_tree._on_search(text)

    def closeEvent(self, event):
        """Handle window close event."""
        self._save_geometry()

        # Stop all streams
        self.stream_manager.stop_all()
        self.unified_view.stop_all()

        # Close database
        self.db.close()

        event.accept()
