"""
Main application window for CamStation.

Clean, modern interface with:
- Device tree sidebar
- Multi-camera grid view
- Timeline playback (UniFi Protect style)
- PTZ controls overlay
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QToolBar, QStatusBar, QMenuBar,
    QMenu, QMessageBox, QDockWidget, QLabel,
    QStackedWidget, QPushButton, QSizePolicy,
    QApplication
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence

from typing import Optional, Dict
from datetime import datetime, timedelta

from ui.styles import get_stylesheet, COLORS
from ui.device_tree import DeviceTreeWidget
from ui.live_view import LiveViewWidget
from ui.dialogs.add_device_dialog import AddDeviceDialog
from ui.components.timeline import TimelineWidget, TimelineEvent
from ui.components.playback_controls import PlaybackControls
from utils.config import Config
from utils.database import Database
from core.stream_manager import StreamManager
from core.playback_controller import PlaybackController


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, config: Config, db: Database):
        super().__init__()
        self.config = config
        self.db = db

        # Core services
        self.stream_manager = StreamManager(max_streams=32)
        self.playback_controller: Optional[PlaybackController] = None

        # State
        self._current_mode = "live"  # live, playback
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

        # Playback menu
        playback_menu = menubar.addMenu("&Playback")

        live_mode_action = QAction("&Live View", self)
        live_mode_action.setShortcut(QKeySequence("Ctrl+L"))
        live_mode_action.triggered.connect(self._switch_to_live)
        playback_menu.addAction(live_mode_action)

        playback_menu.addSeparator()

        search_recordings_action = QAction("&Search Recordings...", self)
        search_recordings_action.setShortcut(QKeySequence("Ctrl+F"))
        search_recordings_action.triggered.connect(self._on_search_recordings)
        playback_menu.addAction(search_recordings_action)

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

        # View mode toggle
        self.live_btn = QPushButton("Live")
        self.live_btn.setCheckable(True)
        self.live_btn.setChecked(True)
        self.live_btn.setToolTip("Switch to live view")
        self.live_btn.clicked.connect(self._switch_to_live)
        toolbar.addWidget(self.live_btn)

        self.playback_btn = QPushButton("Playback")
        self.playback_btn.setCheckable(True)
        self.playback_btn.setToolTip("Switch to playback mode")
        self.playback_btn.clicked.connect(self._switch_to_playback)
        toolbar.addWidget(self.playback_btn)

        toolbar.addSeparator()

        # Grid layout buttons
        grid_sizes = [(1, "1x1"), (2, "2x2"), (3, "3x3"), (4, "4x4")]
        for size, label in grid_sizes:
            btn = QPushButton(label)
            btn.setToolTip(f"{label} grid view")
            btn.clicked.connect(lambda checked, s=size: self._set_grid_layout(s, s))
            toolbar.addWidget(btn)

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
        """Setup the central widget with live view and playback."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stacked widget for live/playback modes
        self.view_stack = QStackedWidget()
        layout.addWidget(self.view_stack)

        # Live view
        self.live_view = LiveViewWidget(self.config, self.stream_manager)
        self.view_stack.addWidget(self.live_view)

        # Playback view
        self.playback_widget = self._create_playback_widget()
        self.view_stack.addWidget(self.playback_widget)

        # Timeline (visible in playback mode)
        self.timeline = TimelineWidget()
        self.timeline.position_changed.connect(self._on_timeline_position_changed)
        self.timeline.setVisible(False)
        layout.addWidget(self.timeline)

        # Playback controls (visible in playback mode)
        self.playback_controls = PlaybackControls()
        self.playback_controls.play_clicked.connect(self._on_play)
        self.playback_controls.pause_clicked.connect(self._on_pause)
        self.playback_controls.skip_forward.connect(lambda: self._on_skip(10))
        self.playback_controls.skip_backward.connect(lambda: self._on_skip(-10))
        self.playback_controls.step_forward.connect(self._on_step_forward)
        self.playback_controls.step_backward.connect(self._on_step_backward)
        self.playback_controls.speed_changed.connect(self._on_speed_changed)
        self.playback_controls.setVisible(False)
        layout.addWidget(self.playback_controls)

    def _create_playback_widget(self) -> QWidget:
        """Create the playback view widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Video display
        self.playback_video = QLabel()
        self.playback_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.playback_video.setStyleSheet(f"background-color: {COLORS['bg_dark']};")
        self.playback_video.setText("Select a camera and time range to start playback")
        self.playback_video.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.playback_video)

        return widget

    def _setup_dock_widgets(self):
        """Setup dock widgets (device tree, etc.)."""
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
        device_dock.setWidget(self.device_tree)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, device_dock)

    def _setup_statusbar(self):
        """Setup the status bar."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)

        # Stream count label
        self.stream_count_label = QLabel("Streams: 0")
        self.statusbar.addWidget(self.stream_count_label)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.statusbar.addWidget(spacer)

        # Connection status
        self.connection_label = QLabel("Ready")
        self.statusbar.addPermanentWidget(self.connection_label)

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Space for play/pause
        from PyQt6.QtGui import QShortcut

        play_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        play_shortcut.activated.connect(self._toggle_play_pause)

        # Arrow keys for seeking
        left_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        left_shortcut.activated.connect(lambda: self._on_skip(-10))

        right_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        right_shortcut.activated.connect(lambda: self._on_skip(10))

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
            # Center on screen
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
        stream_count = self.stream_manager.get_active_count()
        self.stream_count_label.setText(f"Streams: {stream_count}")

    # === Mode Switching ===

    def _switch_to_live(self):
        """Switch to live view mode."""
        self._current_mode = "live"
        self.view_stack.setCurrentIndex(0)
        self.timeline.setVisible(False)
        self.playback_controls.setVisible(False)

        self.live_btn.setChecked(True)
        self.playback_btn.setChecked(False)

        # Stop playback if running
        if self.playback_controller:
            self.playback_controller.stop()

        self.statusbar.showMessage("Live view", 2000)

    def _switch_to_playback(self):
        """Switch to playback mode."""
        self._current_mode = "playback"
        self.view_stack.setCurrentIndex(1)
        self.timeline.setVisible(True)
        self.playback_controls.setVisible(True)

        self.live_btn.setChecked(False)
        self.playback_btn.setChecked(True)

        self.statusbar.showMessage("Playback mode", 2000)

    # === Action Handlers ===

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

        # Add cameras
        for ch in channels:
            camera = Camera(
                id=0,
                device_id=0,
                channel_number=ch.get("channel_number", 1),
                name=ch.get("name", f"Channel {ch.get('channel_number', 1)}"),
                rtsp_url="",  # Will be constructed by database
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
        # TODO: Implement settings dialog
        self.statusbar.showMessage("Settings dialog coming soon", 2000)

    def _on_search_recordings(self):
        """Handle playback search action."""
        self._switch_to_playback()
        # TODO: Show date picker dialog

    def _on_motion_events(self):
        """Handle motion events action."""
        # TODO: Implement motion events dialog
        self.statusbar.showMessage("Motion events coming soon", 2000)

    def _on_lpr_search(self):
        """Handle LPR search action."""
        # TODO: Implement LPR search dialog
        self.statusbar.showMessage("LPR search coming soon", 2000)

    def _on_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About CamStation",
            "<h2>CamStation</h2>"
            "<p>Version 0.1.0</p>"
            "<p>A lightweight, fast, and easy-to-use application for viewing "
            "and managing Hikvision cameras and NVRs.</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>Live view with up to 36 cameras</li>"
            "<li>Smooth timeline scrubbing playback</li>"
            "<li>PTZ control</li>"
            "<li>Motion and LPR event search</li>"
            "</ul>"
            "<p><a href='https://github.com/btzll1412/CamStation'>GitHub Repository</a></p>"
            "<p>Licensed under the MIT License.</p>"
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
            "<p><b>Left/Right</b> - Skip 10 seconds</p>"
            "<p><b>Shift+Left/Right</b> - Skip 1 minute</p>"
            "<p><b>./,</b> - Frame step forward/backward</p>"
            "<h3>General</h3>"
            "<p><b>Ctrl+N</b> - Add device</p>"
            "<p><b>Ctrl+F</b> - Search recordings</p>"
            "<p><b>Ctrl+L</b> - Live view</p>"
        )

    def _on_camera_selected(self, camera_id: int):
        """Handle camera selection in device tree."""
        self._selected_camera_id = camera_id
        self.statusbar.showMessage(f"Selected camera: {camera_id}", 2000)

    def _on_camera_double_clicked(self, camera_id: int):
        """Handle camera double-click to open live view."""
        camera = self.db.get_camera(camera_id)
        if camera:
            if self._current_mode == "live":
                self.live_view.add_camera_to_view(camera)
            else:
                self._start_playback_for_camera(camera)

    def _start_playback_for_camera(self, camera):
        """Start playback for a camera."""
        # Get device for RTSP URL construction
        device = self.db.get_device(camera.device_id)
        if not device:
            return

        # Default to last 24 hours
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)

        # Create playback controller
        self.playback_controller = PlaybackController(
            on_frame=self._on_playback_frame,
            on_status=self._on_playback_status,
            on_position=self._on_playback_position
        )

        # Build RTSP playback URL
        base_url = f"rtsp://{device.username}:{device.password}@{device.ip_address}:{device.rtsp_port}"
        playback_url = f"{base_url}/Streaming/tracks/{camera.channel_number}01"

        # Load recording
        self.playback_controller.load_recording(
            playback_url, start_time, end_time
        )

        # Setup timeline
        self.timeline.set_time_range(start_time, end_time)
        self.timeline.set_current_time(start_time)
        self.timeline.set_thumbnail_callback(self.playback_controller.get_thumbnail)

        # Setup playback controls
        self.playback_controls.set_duration(end_time - start_time)

        # Start playback
        self.playback_controller.play()

    def _on_playback_frame(self, frame, timestamp):
        """Handle new playback frame."""
        from PyQt6.QtGui import QImage, QPixmap
        import cv2

        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w

        q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

        # Scale to fit
        pixmap = QPixmap.fromImage(q_img).scaled(
            self.playback_video.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        self.playback_video.setPixmap(pixmap)

    def _on_playback_status(self, status: str):
        """Handle playback status change."""
        self.playback_controls.set_playing(status == "playing")
        self.statusbar.showMessage(f"Playback: {status}", 2000)

    def _on_playback_position(self, position: datetime):
        """Handle playback position update."""
        self.timeline.set_current_time(position)
        self.playback_controls.set_current_time(position)

    def _on_timeline_position_changed(self, position: datetime):
        """Handle timeline scrub."""
        if self.playback_controller:
            self.playback_controller.seek(position)

    def _on_play(self):
        """Handle play button."""
        if self.playback_controller:
            self.playback_controller.play()

    def _on_pause(self):
        """Handle pause button."""
        if self.playback_controller:
            self.playback_controller.pause()

    def _toggle_play_pause(self):
        """Toggle play/pause."""
        if self._current_mode == "playback" and self.playback_controller:
            if self.playback_controller.is_playing:
                self.playback_controller.pause()
            else:
                self.playback_controller.play()

    def _on_skip(self, seconds: int):
        """Handle skip forward/backward."""
        if self.playback_controller:
            self.playback_controller.seek_relative(seconds)

    def _on_step_forward(self):
        """Handle step forward."""
        if self.playback_controller:
            self.playback_controller.step_forward()

    def _on_step_backward(self):
        """Handle step backward."""
        if self.playback_controller:
            self.playback_controller.step_backward()

    def _on_speed_changed(self, speed: float):
        """Handle speed change."""
        if self.playback_controller:
            self.playback_controller.set_speed(speed)

    def _set_grid_layout(self, rows: int, cols: int):
        """Set the live view grid layout."""
        self.live_view.set_grid_layout(rows, cols)
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

    def _on_search(self, text: str):
        """Handle search input."""
        self.device_tree._on_search(text)

    def closeEvent(self, event):
        """Handle window close event."""
        self._save_geometry()

        # Stop all streams
        self.stream_manager.stop_all()

        # Stop playback
        if self.playback_controller:
            self.playback_controller.stop()

        # Close database
        self.db.close()

        event.accept()
