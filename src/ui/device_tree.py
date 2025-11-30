"""
Device tree widget for displaying cameras and NVRs.

Digital Watchdog-style with:
- Drag & drop cameras to live view grid
- Right-click context menus
- Visual status indicators
- Search/filter
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QMenu, QLineEdit, QHBoxLayout, QPushButton, QLabel,
    QAbstractItemView, QHeaderView, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QByteArray
from PyQt6.QtGui import QAction, QIcon, QDrag, QPixmap, QPainter, QColor, QFont

from typing import List, Optional, Dict
from models.device import Device, Camera
from ui.styles import COLORS
import json


class DraggableTreeWidget(QTreeWidget):
    """Tree widget that supports dragging cameras to grid."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def startDrag(self, supportedActions):
        """Start drag operation with camera data."""
        item = self.currentItem()
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get("type") != "camera":
            return

        # Create drag with camera data
        drag = QDrag(self)
        mime_data = QMimeData()

        # Serialize camera data
        camera_json = json.dumps({
            "camera_id": data["id"],
            "camera_name": data.get("name", "Camera"),
            "device_id": data.get("device_id")
        })
        mime_data.setData("application/x-camera", QByteArray(camera_json.encode()))
        mime_data.setText(data.get("name", "Camera"))

        drag.setMimeData(mime_data)

        # Create drag preview
        pixmap = self._create_drag_pixmap(data.get("name", "Camera"))
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())

        drag.exec(Qt.DropAction.CopyAction)

    def _create_drag_pixmap(self, name: str) -> QPixmap:
        """Create a preview pixmap for dragging."""
        pixmap = QPixmap(180, 40)
        pixmap.fill(QColor(COLORS['bg_secondary']))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Border
        painter.setPen(QColor(COLORS['accent_blue']))
        painter.drawRect(0, 0, 179, 39)

        # Camera icon
        painter.setPen(QColor(COLORS['text_primary']))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(10, 25, f"📷 {name}")

        painter.end()
        return pixmap


class DeviceTreeWidget(QWidget):
    """Widget displaying hierarchical view of devices and cameras."""

    # Signals
    camera_selected = pyqtSignal(int)  # camera_id
    camera_double_clicked = pyqtSignal(int)  # camera_id
    device_selected = pyqtSignal(int)  # device_id
    camera_drag_started = pyqtSignal(int)  # camera_id
    add_all_cameras = pyqtSignal(int)  # device_id - add all cameras from device

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._devices: Dict[int, Device] = {}
        self._cameras: Dict[int, Camera] = {}
        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_secondary']};
                border-bottom: 1px solid {COLORS['border']};
                padding: 8px;
            }}
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(8, 8, 8, 8)
        header_layout.setSpacing(8)

        # Title
        title = QLabel("Devices")
        title.setStyleSheet(f"""
            font-size: 14px;
            font-weight: bold;
            color: {COLORS['text_primary']};
        """)
        header_layout.addWidget(title)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search...")
        self.search_input.textChanged.connect(self._on_search)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS['bg_tertiary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px 8px;
                color: {COLORS['text_primary']};
            }}
            QLineEdit:focus {{
                border-color: {COLORS['accent_blue']};
            }}
        """)
        search_layout.addWidget(self.search_input)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(32, 32)
        refresh_btn.setToolTip("Refresh device list")
        refresh_btn.clicked.connect(self._on_refresh)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_tertiary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                color: {COLORS['text_primary']};
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_blue']};
            }}
        """)
        search_layout.addWidget(refresh_btn)

        header_layout.addLayout(search_layout)
        layout.addWidget(header)

        # Drag hint
        hint = QLabel("Drag cameras to the view grid")
        hint.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 11px;
            padding: 4px 8px;
            background-color: {COLORS['bg_dark']};
        """)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        # Tree widget
        self.tree = DraggableTreeWidget()
        self.tree.setHeaderLabels(["Name", "Status"])
        self.tree.setColumnWidth(0, 180)
        self.tree.setColumnWidth(1, 50)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setIndentation(20)
        self.tree.setAnimated(True)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {COLORS['bg_dark']};
                border: none;
                outline: none;
                color: {COLORS['text_primary']};
            }}
            QTreeWidget::item {{
                padding: 6px 4px;
                border-radius: 4px;
            }}
            QTreeWidget::item:hover {{
                background-color: {COLORS['bg_secondary']};
            }}
            QTreeWidget::item:selected {{
                background-color: {COLORS['accent_blue']};
            }}
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {{
                image: url(none);
                border-image: none;
            }}
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {{
                image: url(none);
                border-image: none;
            }}
            QHeaderView::section {{
                background-color: {COLORS['bg_secondary']};
                color: {COLORS['text_secondary']};
                padding: 8px;
                border: none;
                font-weight: bold;
            }}
        """)

        layout.addWidget(self.tree)

        # Quick actions footer
        footer = QFrame()
        footer.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_secondary']};
                border-top: 1px solid {COLORS['border']};
            }}
        """)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 8, 8, 8)

        add_btn = QPushButton("+ Add Device")
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['accent_blue']};
                border: none;
                border-radius: 4px;
                color: white;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #388bfd;
            }}
        """)
        add_btn.clicked.connect(self._on_add_device)
        footer_layout.addWidget(add_btn)

        layout.addWidget(footer)

    def load_devices(self, devices: List[Device]):
        """Load devices into the tree."""
        self.tree.clear()
        self._devices.clear()
        self._cameras.clear()

        for device in devices:
            self._devices[device.id] = device

            # Device item with icon
            device_item = QTreeWidgetItem()
            device_item.setText(0, f"📹 {device.name}")
            device_item.setText(1, "●")
            device_item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "device",
                "id": device.id,
                "name": device.name
            })

            # Set status color
            if device.is_online:
                device_item.setForeground(1, QColor(COLORS['online']))
                device_item.setToolTip(0, f"{device.name}\n{device.ip_address}\nOnline")
            else:
                device_item.setForeground(1, QColor(COLORS['offline']))
                device_item.setToolTip(0, f"{device.name}\n{device.ip_address}\nOffline")

            # Make device row bold
            font = device_item.font(0)
            font.setBold(True)
            device_item.setFont(0, font)

            # Add cameras as children
            for camera in device.cameras:
                self._cameras[camera.id] = camera

                camera_item = QTreeWidgetItem()

                # Icon based on camera type
                icon = "📷"
                if hasattr(camera, 'has_ptz') and camera.has_ptz:
                    icon = "🎥"
                if hasattr(camera, 'camera_type') and 'lpr' in camera.camera_type.lower():
                    icon = "🚗"

                camera_item.setText(0, f"  {icon} {camera.name}")
                camera_item.setText(1, "●")
                camera_item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "camera",
                    "id": camera.id,
                    "device_id": device.id,
                    "name": camera.name
                })

                if camera.is_online:
                    camera_item.setForeground(1, QColor(COLORS['online']))
                    camera_item.setToolTip(0, f"{camera.name}\nChannel {camera.channel_number}\nOnline - Drag to view")
                else:
                    camera_item.setForeground(1, QColor(COLORS['offline']))
                    camera_item.setToolTip(0, f"{camera.name}\nChannel {camera.channel_number}\nOffline")

                device_item.addChild(camera_item)

            self.tree.addTopLevelItem(device_item)
            device_item.setExpanded(True)

        # Update header count
        total_cameras = sum(len(d.cameras) for d in devices)
        # self.tree.setHeaderLabels([f"Devices ({len(devices)})", ""])

    def get_camera(self, camera_id: int) -> Optional[Camera]:
        """Get camera by ID."""
        return self._cameras.get(camera_id)

    def get_device(self, device_id: int) -> Optional[Device]:
        """Get device by ID."""
        return self._devices.get(device_id)

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

            # Expand if searching
            if text and child_visible:
                device_item.setExpanded(True)

    def _on_refresh(self):
        """Refresh device list from database."""
        devices = self.db.get_all_devices()
        self.load_devices(devices)

    def _on_add_device(self):
        """Emit signal to add new device."""
        # This will be handled by main window
        parent = self.window()
        if hasattr(parent, '_on_add_device'):
            parent._on_add_device()

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
            # Empty area - show add device option
            menu = QMenu(self)
            add_action = QAction("➕ Add Device...", self)
            add_action.triggered.connect(self._on_add_device)
            menu.addAction(add_action)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                color: {COLORS['text_primary']};
            }}
            QMenu::item:selected {{
                background-color: {COLORS['accent_blue']};
                border-radius: 2px;
            }}
            QMenu::separator {{
                height: 1px;
                background: {COLORS['border']};
                margin: 4px 8px;
            }}
        """)

        if data["type"] == "camera":
            # Camera context menu
            live_view_action = QAction("▶️ Open in Live View", self)
            live_view_action.triggered.connect(lambda: self.camera_double_clicked.emit(data["id"]))
            menu.addAction(live_view_action)

            playback_action = QAction("⏪ Playback", self)
            playback_action.triggered.connect(lambda: self._open_playback(data["id"]))
            menu.addAction(playback_action)

            menu.addSeparator()

            # Check if PTZ
            camera = self._cameras.get(data["id"])
            if camera and hasattr(camera, 'has_ptz') and camera.has_ptz:
                ptz_action = QAction("🎮 PTZ Control", self)
                ptz_action.triggered.connect(lambda: self._open_ptz(data["id"]))
                menu.addAction(ptz_action)
                menu.addSeparator()

            fullscreen_action = QAction("🖥️ Fullscreen", self)
            fullscreen_action.triggered.connect(lambda: self._open_fullscreen(data["id"]))
            menu.addAction(fullscreen_action)

            menu.addSeparator()

            rename_action = QAction("✏️ Rename...", self)
            rename_action.triggered.connect(lambda: self._rename_camera(data["id"]))
            menu.addAction(rename_action)

            config_action = QAction("⚙️ Configuration", self)
            config_action.triggered.connect(lambda: self._configure_camera(data["id"]))
            menu.addAction(config_action)

        elif data["type"] == "device":
            # Device context menu
            add_all_action = QAction("📺 Add All Cameras to View", self)
            add_all_action.triggered.connect(lambda: self.add_all_cameras.emit(data["id"]))
            menu.addAction(add_all_action)

            menu.addSeparator()

            refresh_action = QAction("🔄 Refresh Channels", self)
            refresh_action.triggered.connect(lambda: self._refresh_device(data["id"]))
            menu.addAction(refresh_action)

            menu.addSeparator()

            rename_action = QAction("✏️ Rename...", self)
            rename_action.triggered.connect(lambda: self._rename_device(data["id"]))
            menu.addAction(rename_action)

            config_action = QAction("⚙️ Device Configuration", self)
            config_action.triggered.connect(lambda: self._configure_device(data["id"]))
            menu.addAction(config_action)

            menu.addSeparator()

            remove_action = QAction("🗑️ Remove Device", self)
            remove_action.triggered.connect(lambda: self._remove_device(data["id"]))
            menu.addAction(remove_action)

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _open_playback(self, camera_id: int):
        """Open playback for camera."""
        parent = self.window()
        if hasattr(parent, '_start_playback_for_camera'):
            camera = self._cameras.get(camera_id)
            if camera:
                parent._switch_to_playback()
                parent._start_playback_for_camera(camera)

    def _open_ptz(self, camera_id: int):
        """Open PTZ control for camera."""
        parent = self.window()
        if hasattr(parent, '_show_ptz_controls'):
            parent._show_ptz_controls(camera_id)

    def _open_fullscreen(self, camera_id: int):
        """Open camera in fullscreen."""
        parent = self.window()
        if hasattr(parent, '_open_camera_fullscreen'):
            parent._open_camera_fullscreen(camera_id)

    def _rename_camera(self, camera_id: int):
        """Rename a camera."""
        from PyQt6.QtWidgets import QInputDialog
        camera = self._cameras.get(camera_id)
        if camera:
            name, ok = QInputDialog.getText(
                self, "Rename Camera",
                "Enter new name:",
                text=camera.name
            )
            if ok and name:
                self.db.update_camera_name(camera_id, name)
                self._on_refresh()

    def _configure_camera(self, camera_id: int):
        """Open camera configuration."""
        # TODO: Implement camera config dialog
        pass

    def _refresh_device(self, device_id: int):
        """Refresh device channels."""
        # TODO: Implement device refresh
        self._on_refresh()

    def _rename_device(self, device_id: int):
        """Rename a device."""
        from PyQt6.QtWidgets import QInputDialog
        device = self._devices.get(device_id)
        if device:
            name, ok = QInputDialog.getText(
                self, "Rename Device",
                "Enter new name:",
                text=device.name
            )
            if ok and name:
                self.db.update_device_name(device_id, name)
                self._on_refresh()

    def _configure_device(self, device_id: int):
        """Open device configuration."""
        # TODO: Implement device config dialog
        pass

    def _remove_device(self, device_id: int):
        """Remove a device."""
        from PyQt6.QtWidgets import QMessageBox
        device = self._devices.get(device_id)
        if device:
            reply = QMessageBox.question(
                self, "Remove Device",
                f"Are you sure you want to remove '{device.name}'?\n\n"
                "This will remove all cameras associated with this device.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.db.delete_device(device_id)
                self._on_refresh()
