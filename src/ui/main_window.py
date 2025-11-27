"""
Main application window for CamStation.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QToolBar, QStatusBar, QMenuBar,
    QMenu, QMessageBox, QDockWidget, QLabel
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QIcon

from ui.device_tree import DeviceTreeWidget
from ui.live_view import LiveViewWidget
from ui.dialogs.add_device_dialog import AddDeviceDialog
from utils.config import Config
from utils.database import Database


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self, config: Config, db: Database):
        super().__init__()
        self.config = config
        self.db = db
        
        self.setWindowTitle("CamStation")
        self.setMinimumSize(1200, 800)
        
        # Restore window geometry if saved
        self._restore_geometry()
        
        # Setup UI components
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_dock_widgets()
        self._setup_statusbar()
        
        # Load devices
        self._load_devices()
    
    def _setup_menubar(self):
        """Setup the menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        add_device_action = QAction("&Add Device...", self)
        add_device_action.setShortcut("Ctrl+N")
        add_device_action.triggered.connect(self._on_add_device)
        file_menu.addAction(add_device_action)
        
        file_menu.addSeparator()
        
        settings_action = QAction("&Settings...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._on_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        single_view_action = QAction("&Single View", self)
        single_view_action.setShortcut("1")
        single_view_action.triggered.connect(lambda: self._set_grid_layout(1, 1))
        view_menu.addAction(single_view_action)
        
        grid_2x2_action = QAction("&2x2 Grid", self)
        grid_2x2_action.setShortcut("2")
        grid_2x2_action.triggered.connect(lambda: self._set_grid_layout(2, 2))
        view_menu.addAction(grid_2x2_action)
        
        grid_3x3_action = QAction("&3x3 Grid", self)
        grid_3x3_action.setShortcut("3")
        grid_3x3_action.triggered.connect(lambda: self._set_grid_layout(3, 3))
        view_menu.addAction(grid_3x3_action)
        
        grid_4x4_action = QAction("&4x4 Grid", self)
        grid_4x4_action.setShortcut("4")
        grid_4x4_action.triggered.connect(lambda: self._set_grid_layout(4, 4))
        view_menu.addAction(grid_4x4_action)
        
        view_menu.addSeparator()
        
        fullscreen_action = QAction("&Fullscreen", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(fullscreen_action)
        
        # Playback menu
        playback_menu = menubar.addMenu("&Playback")
        
        search_recordings_action = QAction("&Search Recordings...", self)
        search_recordings_action.setShortcut("Ctrl+F")
        search_recordings_action.triggered.connect(self._on_search_recordings)
        playback_menu.addAction(search_recordings_action)
        
        # Events menu
        events_menu = menubar.addMenu("&Events")
        
        motion_events_action = QAction("&Motion Events...", self)
        motion_events_action.triggered.connect(self._on_motion_events)
        events_menu.addAction(motion_events_action)
        
        lpr_search_action = QAction("&LPR Plate Search...", self)
        lpr_search_action.setShortcut("Ctrl+L")
        lpr_search_action.triggered.connect(self._on_lpr_search)
        events_menu.addAction(lpr_search_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About CamStation", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)
    
    def _setup_toolbar(self):
        """Setup the main toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
        
        # Add device button
        add_device_btn = QAction("Add Device", self)
        add_device_btn.setToolTip("Add a new camera or NVR")
        add_device_btn.triggered.connect(self._on_add_device)
        toolbar.addAction(add_device_btn)
        
        toolbar.addSeparator()
        
        # View layout buttons
        single_btn = QAction("1x1", self)
        single_btn.setToolTip("Single camera view")
        single_btn.triggered.connect(lambda: self._set_grid_layout(1, 1))
        toolbar.addAction(single_btn)
        
        grid_2x2_btn = QAction("2x2", self)
        grid_2x2_btn.setToolTip("2x2 grid view")
        grid_2x2_btn.triggered.connect(lambda: self._set_grid_layout(2, 2))
        toolbar.addAction(grid_2x2_btn)
        
        grid_3x3_btn = QAction("3x3", self)
        grid_3x3_btn.setToolTip("3x3 grid view")
        grid_3x3_btn.triggered.connect(lambda: self._set_grid_layout(3, 3))
        toolbar.addAction(grid_3x3_btn)
        
        grid_4x4_btn = QAction("4x4", self)
        grid_4x4_btn.setToolTip("4x4 grid view")
        grid_4x4_btn.triggered.connect(lambda: self._set_grid_layout(4, 4))
        toolbar.addAction(grid_4x4_btn)
        
        toolbar.addSeparator()
        
        # Playback button
        playback_btn = QAction("Playback", self)
        playback_btn.setToolTip("Search and playback recordings")
        playback_btn.triggered.connect(self._on_search_recordings)
        toolbar.addAction(playback_btn)
        
        # LPR Search button
        lpr_btn = QAction("LPR Search", self)
        lpr_btn.setToolTip("Search license plates")
        lpr_btn.triggered.connect(self._on_lpr_search)
        toolbar.addAction(lpr_btn)
    
    def _setup_central_widget(self):
        """Setup the central widget with live view grid."""
        self.live_view = LiveViewWidget(self.config)
        self.setCentralWidget(self.live_view)
    
    def _setup_dock_widgets(self):
        """Setup dock widgets (device tree, etc.)."""
        # Device tree dock
        device_dock = QDockWidget("Devices", self)
        device_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        device_dock.setMinimumWidth(250)
        
        self.device_tree = DeviceTreeWidget(self.db)
        self.device_tree.camera_selected.connect(self._on_camera_selected)
        self.device_tree.camera_double_clicked.connect(self._on_camera_double_clicked)
        device_dock.setWidget(self.device_tree)
        
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, device_dock)
    
    def _setup_statusbar(self):
        """Setup the status bar."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        
        # Connection status label
        self.connection_label = QLabel("Ready")
        self.statusbar.addPermanentWidget(self.connection_label)
    
    def _restore_geometry(self):
        """Restore window geometry from config."""
        geometry = self.config.get("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            # Center on screen with default size
            self.resize(1400, 900)
    
    def _save_geometry(self):
        """Save window geometry to config."""
        self.config.set("window_geometry", self.saveGeometry())
    
    def _load_devices(self):
        """Load devices from database into tree."""
        devices = self.db.get_all_devices()
        self.device_tree.load_devices(devices)
    
    # === Slot handlers ===
    
    def _on_add_device(self):
        """Handle add device action."""
        dialog = AddDeviceDialog(self)
        if dialog.exec():
            device_info = dialog.get_device_info()
            # TODO: Test connection and discover channels
            # TODO: Add to database
            # TODO: Refresh device tree
            self.statusbar.showMessage(f"Adding device: {device_info['ip']}", 3000)
    
    def _on_settings(self):
        """Handle settings action."""
        # TODO: Implement settings dialog
        pass
    
    def _on_search_recordings(self):
        """Handle playback search action."""
        # TODO: Implement playback search dialog
        pass
    
    def _on_motion_events(self):
        """Handle motion events action."""
        # TODO: Implement motion events dialog
        pass
    
    def _on_lpr_search(self):
        """Handle LPR search action."""
        # TODO: Implement LPR search dialog
        pass
    
    def _on_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About CamStation",
            "<h2>CamStation</h2>"
            "<p>Version 0.1.0</p>"
            "<p>A lightweight, open-source application for viewing and managing "
            "Hikvision cameras and NVRs.</p>"
            "<p><a href='https://github.com/btzll1412/CamStation'>GitHub Repository</a></p>"
            "<p>Licensed under the MIT License.</p>"
        )
    
    def _on_camera_selected(self, camera_id: int):
        """Handle camera selection in device tree."""
        self.statusbar.showMessage(f"Selected camera: {camera_id}", 2000)
    
    def _on_camera_double_clicked(self, camera_id: int):
        """Handle camera double-click to open live view."""
        camera = self.db.get_camera(camera_id)
        if camera:
            self.live_view.add_camera_to_view(camera)
    
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
    
    def closeEvent(self, event):
        """Handle window close event."""
        self._save_geometry()
        
        # Stop all streams
        self.live_view.stop_all_streams()
        
        # Close database
        self.db.close()
        
        event.accept()
