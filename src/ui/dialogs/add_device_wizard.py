"""
Smart device onboarding wizard.

Features:
- Network discovery (ONVIF + Hikvision)
- Auto-detection of device protocol
- One-click add for discovered devices
- Manual configuration option
- Progress feedback for all operations
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QComboBox, QPushButton,
    QLabel, QGroupBox, QProgressBar, QMessageBox,
    QCheckBox, QListWidget, QListWidgetItem, QStackedWidget,
    QWidget, QFrame, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QColor, QIcon

from typing import Dict, List, Optional
from dataclasses import asdict

from core.device_manager import (
    DeviceManager, DeviceProtocol, DeviceInfo,
    DeviceCapabilities, ChannelInfo
)
from api.onvif_client import ONVIFDiscovery, DiscoveredDevice
from ui.styles import COLORS


class DeviceDiscoveryThread(QThread):
    """Thread for network device discovery."""

    device_found = pyqtSignal(object)  # DiscoveredDevice
    discovery_complete = pyqtSignal(list)  # List[DiscoveredDevice]
    progress = pyqtSignal(str)

    def __init__(self, timeout: float = 5.0):
        super().__init__()
        self.timeout = timeout
        self._discovery = ONVIFDiscovery()

    def run(self):
        self.progress.emit("Scanning network for cameras...")

        def on_device(device: DiscoveredDevice):
            self.device_found.emit(device)

        devices = self._discovery.discover(self.timeout, on_device)
        self.discovery_complete.emit(devices)

    def stop(self):
        self._discovery.stop()


class DeviceDetectionThread(QThread):
    """Thread for device auto-detection."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(object, str)  # DeviceInfo, message
    error = pyqtSignal(str)

    def __init__(self, ip: str, port: int, username: str, password: str):
        super().__init__()
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self._device_manager = DeviceManager()

    def run(self):
        try:
            device_info, message = self._device_manager.detect_device(
                self.ip, self.port, self.username, self.password,
                on_progress=lambda msg: self.progress.emit(msg)
            )

            if device_info:
                self.finished.emit(device_info, message)
            else:
                self.error.emit(message)

        except Exception as e:
            self.error.emit(str(e))


class DiscoveredDeviceWidget(QFrame):
    """Widget for displaying a discovered device."""

    clicked = pyqtSignal(object)  # DiscoveredDevice

    def __init__(self, device: DiscoveredDevice, parent=None):
        super().__init__(parent)
        self.device = device
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_light']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 8px;
            }}
            QFrame:hover {{
                background-color: {COLORS['bg_hover']};
                border-color: {COLORS['accent_blue']};
            }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        # Icon based on device type
        icon_label = QLabel()
        icon_text = {
            'hikvision': '🎥',
            'dahua': '📷',
            'axis': '📹',
            'onvif': '📸'
        }.get(self.device.device_type, '📸')
        icon_label.setText(icon_text)
        icon_label.setStyleSheet("font-size: 24px;")
        layout.addWidget(icon_label)

        # Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QLabel(self.device.name)
        name_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_primary']};")
        info_layout.addWidget(name_label)

        details_label = QLabel(f"{self.device.ip_address}:{self.device.port} • {self.device.device_type.upper()}")
        details_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        info_layout.addWidget(details_label)

        layout.addLayout(info_layout)
        layout.addStretch()

        # Add button
        add_btn = QPushButton("Add")
        add_btn.setFixedWidth(60)
        add_btn.clicked.connect(lambda: self.clicked.emit(self.device))
        layout.addWidget(add_btn)

    def mousePressEvent(self, event):
        self.clicked.emit(self.device)


class AddDeviceWizard(QDialog):
    """
    Smart device onboarding wizard.

    Pages:
    1. Discovery - Find cameras on network
    2. Manual - Enter device details manually
    3. Credentials - Enter username/password
    4. Detecting - Auto-detect device type
    5. Confirm - Review and add device
    """

    device_added = pyqtSignal(object)  # DeviceInfo

    def __init__(self, parent=None):
        super().__init__(parent)
        self._detected_device: Optional[DeviceInfo] = None
        self._selected_discovered: Optional[DiscoveredDevice] = None

        self._setup_ui()
        self._start_discovery()

    def _setup_ui(self):
        self.setWindowTitle("Add Device")
        self.setMinimumSize(600, 500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QWidget()
        header.setStyleSheet(f"background-color: {COLORS['bg_dark']};")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 20, 24, 20)

        title = QLabel("Add Camera or NVR")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {COLORS['text_primary']};")
        header_layout.addWidget(title)

        subtitle = QLabel("Discover cameras on your network or add manually")
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']};")
        header_layout.addWidget(subtitle)

        layout.addWidget(header)

        # Tab buttons
        tab_widget = QWidget()
        tab_widget.setStyleSheet(f"background-color: {COLORS['bg_dark']}; border-bottom: 1px solid {COLORS['border']};")
        tab_layout = QHBoxLayout(tab_widget)
        tab_layout.setContentsMargins(24, 0, 24, 0)
        tab_layout.setSpacing(0)

        self.discover_tab = QPushButton("Discover")
        self.discover_tab.setCheckable(True)
        self.discover_tab.setChecked(True)
        self.discover_tab.clicked.connect(lambda: self._switch_page(0))
        self._style_tab_button(self.discover_tab, True)
        tab_layout.addWidget(self.discover_tab)

        self.manual_tab = QPushButton("Manual")
        self.manual_tab.setCheckable(True)
        self.manual_tab.clicked.connect(lambda: self._switch_page(1))
        self._style_tab_button(self.manual_tab, False)
        tab_layout.addWidget(self.manual_tab)

        tab_layout.addStretch()
        layout.addWidget(tab_widget)

        # Stacked content
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # Page 0: Discovery
        self.stack.addWidget(self._create_discovery_page())

        # Page 1: Manual entry
        self.stack.addWidget(self._create_manual_page())

        # Page 2: Detecting
        self.stack.addWidget(self._create_detecting_page())

        # Page 3: Confirm
        self.stack.addWidget(self._create_confirm_page())

    def _style_tab_button(self, btn: QPushButton, active: bool):
        if active:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    border-bottom: 2px solid {COLORS['accent_blue']};
                    color: {COLORS['accent_blue']};
                    padding: 12px 20px;
                    font-weight: bold;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    border-bottom: 2px solid transparent;
                    color: {COLORS['text_secondary']};
                    padding: 12px 20px;
                }}
                QPushButton:hover {{
                    color: {COLORS['text_primary']};
                }}
            """)

    def _switch_page(self, index: int):
        if index == 0:
            self.stack.setCurrentIndex(0)
            self._style_tab_button(self.discover_tab, True)
            self._style_tab_button(self.manual_tab, False)
            self.discover_tab.setChecked(True)
            self.manual_tab.setChecked(False)
        elif index == 1:
            self.stack.setCurrentIndex(1)
            self._style_tab_button(self.discover_tab, False)
            self._style_tab_button(self.manual_tab, True)
            self.discover_tab.setChecked(False)
            self.manual_tab.setChecked(True)

    def _create_discovery_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)

        # Status and refresh
        status_layout = QHBoxLayout()

        self.discovery_status = QLabel("Searching for cameras...")
        self.discovery_status.setStyleSheet(f"color: {COLORS['text_secondary']};")
        status_layout.addWidget(self.discovery_status)

        status_layout.addStretch()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._start_discovery)
        status_layout.addWidget(self.refresh_btn)

        layout.addLayout(status_layout)

        # Progress bar
        self.discovery_progress = QProgressBar()
        self.discovery_progress.setRange(0, 0)
        self.discovery_progress.setFixedHeight(4)
        self.discovery_progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS['bg_dark']};
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS['accent_blue']};
            }}
        """)
        layout.addWidget(self.discovery_progress)

        # Discovered devices list
        self.discovered_scroll = QScrollArea()
        self.discovered_scroll.setWidgetResizable(True)
        self.discovered_scroll.setStyleSheet("QScrollArea { border: none; }")

        self.discovered_container = QWidget()
        self.discovered_layout = QVBoxLayout(self.discovered_container)
        self.discovered_layout.setSpacing(8)
        self.discovered_layout.setContentsMargins(0, 8, 0, 8)
        self.discovered_layout.addStretch()

        self.discovered_scroll.setWidget(self.discovered_container)
        layout.addWidget(self.discovered_scroll)

        # Empty state
        self.no_devices_label = QLabel("No cameras found on the network.\nMake sure your cameras are powered on and connected.")
        self.no_devices_label.setStyleSheet(f"color: {COLORS['text_muted']}; padding: 40px;")
        self.no_devices_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_devices_label.setVisible(False)
        layout.addWidget(self.no_devices_label)

        return page

    def _create_manual_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)

        # Connection settings
        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("192.168.1.100")
        form_layout.addRow("IP Address:", self.ip_input)

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(80)
        form_layout.addRow("HTTP Port:", self.port_input)

        self.username_input = QLineEdit()
        self.username_input.setText("admin")
        form_layout.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Password:", self.password_input)

        layout.addLayout(form_layout)

        # Protocol selection
        protocol_group = QGroupBox("Device Type")
        protocol_layout = QVBoxLayout(protocol_group)

        self.protocol_auto = QCheckBox("Auto-detect (recommended)")
        self.protocol_auto.setChecked(True)
        protocol_layout.addWidget(self.protocol_auto)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["Hikvision (ISAPI)", "ONVIF", "Generic RTSP"])
        self.protocol_combo.setEnabled(False)
        protocol_layout.addWidget(self.protocol_combo)

        self.protocol_auto.toggled.connect(lambda checked: self.protocol_combo.setEnabled(not checked))

        layout.addWidget(protocol_group)

        # Save password option
        self.save_password_cb = QCheckBox("Save password (stored locally)")
        self.save_password_cb.setChecked(True)
        layout.addWidget(self.save_password_cb)

        layout.addStretch()

        # Test connection button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.test_btn = QPushButton("Test Connection")
        self.test_btn.setObjectName("primary")
        self.test_btn.setFixedWidth(150)
        self.test_btn.clicked.connect(self._on_test_connection)
        btn_layout.addWidget(self.test_btn)

        layout.addLayout(btn_layout)

        return page

    def _create_detecting_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 40, 24, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Spinner
        spinner = QLabel("🔍")
        spinner.setStyleSheet("font-size: 48px;")
        spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(spinner)

        self.detecting_status = QLabel("Detecting device type...")
        self.detecting_status.setStyleSheet(f"font-size: 16px; color: {COLORS['text_primary']};")
        self.detecting_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.detecting_status)

        self.detecting_progress = QProgressBar()
        self.detecting_progress.setRange(0, 0)
        self.detecting_progress.setFixedWidth(300)
        layout.addWidget(self.detecting_progress, alignment=Qt.AlignmentFlag.AlignCenter)

        return page

    def _create_confirm_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)

        # Success header
        success_layout = QHBoxLayout()
        success_icon = QLabel("✅")
        success_icon.setStyleSheet("font-size: 32px;")
        success_layout.addWidget(success_icon)

        success_text = QVBoxLayout()
        self.confirm_title = QLabel("Device Found!")
        self.confirm_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['text_primary']};")
        success_text.addWidget(self.confirm_title)

        self.confirm_subtitle = QLabel("")
        self.confirm_subtitle.setStyleSheet(f"color: {COLORS['text_secondary']};")
        success_text.addWidget(self.confirm_subtitle)

        success_layout.addLayout(success_text)
        success_layout.addStretch()
        layout.addLayout(success_layout)

        layout.addSpacing(20)

        # Device info
        info_group = QGroupBox("Device Information")
        info_layout = QFormLayout(info_group)

        self.info_name = QLabel("-")
        info_layout.addRow("Name:", self.info_name)

        self.info_model = QLabel("-")
        info_layout.addRow("Model:", self.info_model)

        self.info_protocol = QLabel("-")
        info_layout.addRow("Protocol:", self.info_protocol)

        self.info_channels = QLabel("-")
        info_layout.addRow("Channels:", self.info_channels)

        self.info_capabilities = QLabel("-")
        self.info_capabilities.setWordWrap(True)
        info_layout.addRow("Features:", self.info_capabilities)

        layout.addWidget(info_group)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()

        back_btn = QPushButton("Back")
        back_btn.clicked.connect(lambda: self._switch_page(1))
        btn_layout.addWidget(back_btn)

        btn_layout.addStretch()

        self.add_device_btn = QPushButton("Add Device")
        self.add_device_btn.setObjectName("primary")
        self.add_device_btn.clicked.connect(self._on_add_device)
        btn_layout.addWidget(self.add_device_btn)

        layout.addLayout(btn_layout)

        return page

    def _start_discovery(self):
        """Start network discovery."""
        self.discovery_progress.setVisible(True)
        self.discovery_status.setText("Scanning network for cameras...")
        self.no_devices_label.setVisible(False)
        self.refresh_btn.setEnabled(False)

        # Clear existing devices
        while self.discovered_layout.count() > 1:
            item = self.discovered_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Start discovery thread
        self._discovery_thread = DeviceDiscoveryThread(timeout=5.0)
        self._discovery_thread.device_found.connect(self._on_device_found)
        self._discovery_thread.discovery_complete.connect(self._on_discovery_complete)
        self._discovery_thread.start()

    def _on_device_found(self, device: DiscoveredDevice):
        """Handle discovered device."""
        widget = DiscoveredDeviceWidget(device)
        widget.clicked.connect(self._on_discovered_device_clicked)

        # Insert before the stretch
        self.discovered_layout.insertWidget(self.discovered_layout.count() - 1, widget)

    def _on_discovery_complete(self, devices: List[DiscoveredDevice]):
        """Handle discovery completion."""
        self.discovery_progress.setVisible(False)
        self.refresh_btn.setEnabled(True)

        count = len(devices)
        if count == 0:
            self.discovery_status.setText("No cameras found")
            self.no_devices_label.setVisible(True)
        else:
            self.discovery_status.setText(f"Found {count} device{'s' if count != 1 else ''}")

    def _on_discovered_device_clicked(self, device: DiscoveredDevice):
        """Handle click on discovered device."""
        self._selected_discovered = device

        # Pre-fill manual form
        self.ip_input.setText(device.ip_address)
        self.port_input.setValue(device.port)

        # Switch to credentials entry
        self._switch_page(1)

    def _on_test_connection(self):
        """Test connection and detect device."""
        ip = self.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "Error", "Please enter an IP address.")
            return

        port = self.port_input.value()
        username = self.username_input.text().strip()
        password = self.password_input.text()

        # Switch to detecting page
        self.stack.setCurrentIndex(2)
        self.detecting_status.setText("Connecting to device...")

        # Start detection thread
        self._detection_thread = DeviceDetectionThread(ip, port, username, password)
        self._detection_thread.progress.connect(self._on_detection_progress)
        self._detection_thread.finished.connect(self._on_detection_finished)
        self._detection_thread.error.connect(self._on_detection_error)
        self._detection_thread.start()

    def _on_detection_progress(self, message: str):
        """Update detection progress."""
        self.detecting_status.setText(message)

    def _on_detection_finished(self, device_info: DeviceInfo, message: str):
        """Handle successful device detection."""
        self._detected_device = device_info

        # Update confirm page
        self.confirm_subtitle.setText(message)
        self.info_name.setText(device_info.name)
        self.info_model.setText(f"{device_info.manufacturer} {device_info.model}")
        self.info_protocol.setText(device_info.protocol.value.upper())
        self.info_channels.setText(str(len(device_info.channels)))

        # Build capabilities string
        caps = device_info.capabilities
        cap_list = []
        if caps.live_view: cap_list.append("Live View")
        if caps.playback: cap_list.append("Playback")
        if caps.ptz: cap_list.append("PTZ")
        if caps.audio: cap_list.append("Audio")
        if caps.lpr: cap_list.append("LPR")
        if caps.motion_detection: cap_list.append("Motion Detection")

        self.info_capabilities.setText(", ".join(cap_list) if cap_list else "Basic streaming only")

        # Switch to confirm page
        self.stack.setCurrentIndex(3)

    def _on_detection_error(self, error: str):
        """Handle detection error."""
        self._switch_page(1)
        QMessageBox.critical(self, "Detection Failed", f"Could not detect device:\n{error}")

    def _on_add_device(self):
        """Add the detected device."""
        if self._detected_device:
            # Update password based on save preference
            if not self.save_password_cb.isChecked():
                self._detected_device.password = ""

            self.device_added.emit(self._detected_device)
            self.accept()

    def get_device_info(self) -> Optional[DeviceInfo]:
        """Get the added device info."""
        return self._detected_device
