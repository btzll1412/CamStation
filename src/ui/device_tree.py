"""
Device tree widget for displaying cameras and NVRs.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QMenu, QLineEdit, QHBoxLayout, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QIcon

from typing import List, Optional
from models.device import Device, Camera


class DeviceTreeWidget(QWidget):
    """Widget displaying hierarchical view of devices and cameras."""
    
    # Signals
    camera_selected = pyqtSignal(int)  # camera_id
    camera_double_clicked = pyqtSignal(int)  # camera_id
    device_selected = pyqtSignal(int)  # device_id
    
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Search bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search devices...")
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(30)
        refresh_btn.setToolTip("Refresh device list")
        refresh_btn.clicked.connect(self._on_refresh)
        search_layout.addWidget(refresh_btn)
        
        layout.addLayout(search_layout)
        
        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Status"])
        self.tree.setColumnWidth(0, 180)
        self.tree.setColumnWidth(1, 60)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        
        layout.addWidget(self.tree)
    
    def load_devices(self, devices: List[Device]):
        """Load devices into the tree."""
        self.tree.clear()
        
        for device in devices:
            device_item = QTreeWidgetItem([device.name, "●"])
            device_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "device", "id": device.id})
            
            # Set status color
            if device.is_online:
                device_item.setForeground(1, Qt.GlobalColor.green)
            else:
                device_item.setForeground(1, Qt.GlobalColor.red)
            
            # Add cameras as children
            for camera in device.cameras:
                camera_item = QTreeWidgetItem([camera.name, "●"])
                camera_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "camera", "id": camera.id})
                
                if camera.is_online:
                    camera_item.setForeground(1, Qt.GlobalColor.green)
                else:
                    camera_item.setForeground(1, Qt.GlobalColor.red)
                
                device_item.addChild(camera_item)
            
            self.tree.addTopLevelItem(device_item)
            device_item.setExpanded(True)
    
    def _on_search(self, text: str):
        """Filter tree items based on search text."""
        text = text.lower()
        
        for i in range(self.tree.topLevelItemCount()):
            device_item = self.tree.topLevelItem(i)
            device_visible = text in device_item.text(0).lower()
            
            # Check children
            child_visible = False
            for j in range(device_item.childCount()):
                camera_item = device_item.child(j)
                if text in camera_item.text(0).lower():
                    camera_item.setHidden(False)
                    child_visible = True
                else:
                    camera_item.setHidden(bool(text))
            
            device_item.setHidden(not (device_visible or child_visible) and bool(text))
    
    def _on_refresh(self):
        """Refresh device list from database."""
        devices = self.db.get_all_devices()
        self.load_devices(devices)
    
    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle item click."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            if data["type"] == "camera":
                self.camera_selected.emit(data["id"])
            elif data["type"] == "device":
                self.device_selected.emit(data["id"])
    
    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle item double-click."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data["type"] == "camera":
            self.camera_double_clicked.emit(data["id"])
    
    def _on_context_menu(self, position):
        """Show context menu."""
        item = self.tree.itemAt(position)
        if not item:
            return
        
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        menu = QMenu(self)
        
        if data["type"] == "camera":
            live_view_action = QAction("Open Live View", self)
            live_view_action.triggered.connect(lambda: self.camera_double_clicked.emit(data["id"]))
            menu.addAction(live_view_action)
            
            playback_action = QAction("Playback", self)
            # playback_action.triggered.connect(...)
            menu.addAction(playback_action)
            
            menu.addSeparator()
            
            ptz_action = QAction("PTZ Control", self)
            menu.addAction(ptz_action)
            
            menu.addSeparator()
            
            config_action = QAction("Configuration", self)
            menu.addAction(config_action)
        
        elif data["type"] == "device":
            refresh_action = QAction("Refresh Channels", self)
            menu.addAction(refresh_action)
            
            menu.addSeparator()
            
            config_action = QAction("Device Configuration", self)
            menu.addAction(config_action)
            
            menu.addSeparator()
            
            remove_action = QAction("Remove Device", self)
            menu.addAction(remove_action)
        
        menu.exec(self.tree.viewport().mapToGlobal(position))
