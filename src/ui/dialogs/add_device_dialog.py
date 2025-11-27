"""
Dialog for adding new devices (cameras or NVRs).
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QComboBox, QPushButton,
    QLabel, QGroupBox, QProgressBar, QMessageBox,
    QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from typing import Dict, Optional
from api.isapi_client import ISAPIClient


class DeviceDiscoveryThread(QThread):
    """Thread for discovering device info and channels."""
    
    progress = pyqtSignal(str)  # status message
    finished = pyqtSignal(dict)  # device info
    error = pyqtSignal(str)  # error message
    
    def __init__(self, ip: str, port: int, username: str, password: str):
        super().__init__()
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
    
    def run(self):
        """Run device discovery."""
        try:
            self.progress.emit("Connecting to device...")
            
            client = ISAPIClient(self.ip, self.port, self.username, self.password)
            
            # Get device info
            self.progress.emit("Getting device information...")
            device_info = client.get_device_info()
            
            if not device_info:
                self.error.emit("Failed to get device information. Check credentials.")
                return
            
            # Get channels
            self.progress.emit("Discovering channels...")
            channels = client.get_channels()
            
            result = {
                "device_info": device_info,
                "channels": channels,
                "ip": self.ip,
                "port": self.port,
                "username": self.username,
                "password": self.password
            }
            
            self.finished.emit(result)
            
        except Exception as e:
            self.error.emit(str(e))


class AddDeviceDialog(QDialog):
    """Dialog for adding a new device."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.device_info: Optional[Dict] = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup UI components."""
        self.setWindowTitle("Add Device")
        self.setMinimumWidth(400)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        # Connection settings group
        connection_group = QGroupBox("Connection Settings")
        connection_layout = QFormLayout()
        
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("192.168.1.100")
        connection_layout.addRow("IP Address:", self.ip_input)
        
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(80)
        connection_layout.addRow("HTTP Port:", self.port_input)
        
        self.username_input = QLineEdit()
        self.username_input.setText("admin")
        connection_layout.addRow("Username:", self.username_input)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        connection_layout.addRow("Password:", self.password_input)
        
        connection_group.setLayout(connection_layout)
        layout.addWidget(connection_group)
        
        # Device type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Device Type:"))
        self.device_type = QComboBox()
        self.device_type.addItems(["Auto Detect", "NVR", "IP Camera"])
        type_layout.addWidget(self.device_type)
        type_layout.addStretch()
        layout.addLayout(type_layout)
        
        # Options
        self.save_password_cb = QCheckBox("Save password")
        self.save_password_cb.setChecked(True)
        layout.addWidget(self.save_password_cb)
        
        # Status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.progress_bar)
        
        # Device info display (shown after discovery)
        self.device_info_group = QGroupBox("Device Information")
        self.device_info_group.setVisible(False)
        device_info_layout = QFormLayout()
        
        self.model_label = QLabel("-")
        device_info_layout.addRow("Model:", self.model_label)
        
        self.serial_label = QLabel("-")
        device_info_layout.addRow("Serial:", self.serial_label)
        
        self.channels_label = QLabel("-")
        device_info_layout.addRow("Channels:", self.channels_label)
        
        self.device_info_group.setLayout(device_info_layout)
        layout.addWidget(self.device_info_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._on_test_connection)
        button_layout.addWidget(self.test_btn)
        
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.add_btn = QPushButton("Add Device")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.add_btn)
        
        layout.addLayout(button_layout)
    
    def _on_test_connection(self):
        """Test connection to device."""
        ip = self.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "Error", "Please enter an IP address.")
            return
        
        port = self.port_input.value()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        
        # Disable inputs during test
        self._set_inputs_enabled(False)
        self.progress_bar.setVisible(True)
        self.device_info_group.setVisible(False)
        
        # Start discovery thread
        self.discovery_thread = DeviceDiscoveryThread(ip, port, username, password)
        self.discovery_thread.progress.connect(self._on_discovery_progress)
        self.discovery_thread.finished.connect(self._on_discovery_finished)
        self.discovery_thread.error.connect(self._on_discovery_error)
        self.discovery_thread.start()
    
    def _on_discovery_progress(self, message: str):
        """Update status during discovery."""
        self.status_label.setText(message)
    
    def _on_discovery_finished(self, result: Dict):
        """Handle successful discovery."""
        self._set_inputs_enabled(True)
        self.progress_bar.setVisible(False)
        
        self.device_info = result
        device = result.get("device_info", {})
        channels = result.get("channels", [])
        
        # Update device info display
        self.model_label.setText(device.get("model", "Unknown"))
        self.serial_label.setText(device.get("serial_number", "Unknown"))
        self.channels_label.setText(str(len(channels)))
        
        self.device_info_group.setVisible(True)
        self.status_label.setText("Connection successful!")
        self.status_label.setStyleSheet("color: green;")
        
        self.add_btn.setEnabled(True)
    
    def _on_discovery_error(self, error: str):
        """Handle discovery error."""
        self._set_inputs_enabled(True)
        self.progress_bar.setVisible(False)
        
        self.status_label.setText(f"Error: {error}")
        self.status_label.setStyleSheet("color: red;")
        
        self.add_btn.setEnabled(False)
    
    def _set_inputs_enabled(self, enabled: bool):
        """Enable/disable input controls."""
        self.ip_input.setEnabled(enabled)
        self.port_input.setEnabled(enabled)
        self.username_input.setEnabled(enabled)
        self.password_input.setEnabled(enabled)
        self.device_type.setEnabled(enabled)
        self.test_btn.setEnabled(enabled)
    
    def get_device_info(self) -> Optional[Dict]:
        """Get the discovered device info."""
        if self.device_info:
            return {
                **self.device_info,
                "save_password": self.save_password_cb.isChecked()
            }
        return None
