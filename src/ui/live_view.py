"""
Live view widget for displaying camera streams in a grid.
"""

from PyQt6.QtWidgets import (
    QWidget, QGridLayout, QLabel, QFrame,
    QVBoxLayout, QMenu, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QAction

import cv2
import numpy as np
from typing import Optional, Dict, List
from threading import Thread
import queue

from models.device import Camera
from streaming.rtsp_stream import RTSPStream
from utils.config import Config


class CameraViewCell(QFrame):
    """Single camera view cell in the grid."""
    
    clicked = pyqtSignal(int)  # cell_index
    double_clicked = pyqtSignal(int)  # cell_index
    
    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.camera: Optional[Camera] = None
        self.stream: Optional[RTSPStream] = None
        self.is_selected = False
        
        self._setup_ui()
        
        # Frame update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_frame)
    
    def _setup_ui(self):
        """Setup UI components."""
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        self.setLineWidth(1)
        self.setStyleSheet("background-color: #1a1a1a;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Video display label
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("color: #666;")
        self.video_label.setText("No Camera")
        self.video_label.setScaledContents(False)
        layout.addWidget(self.video_label)
        
        # Camera name overlay
        self.name_label = QLabel()
        self.name_label.setStyleSheet(
            "color: white; background-color: rgba(0,0,0,128); padding: 2px 5px;"
        )
        self.name_label.setVisible(False)
    
    def set_camera(self, camera: Camera):
        """Set camera for this cell and start streaming."""
        self.stop_stream()
        
        self.camera = camera
        self.name_label.setText(camera.name)
        self.name_label.setVisible(True)
        self.video_label.setText("Connecting...")
        
        # Start RTSP stream
        self.stream = RTSPStream(camera.rtsp_url)
        self.stream.start()
        
        # Start frame update timer (30 fps target)
        self.update_timer.start(33)
    
    def stop_stream(self):
        """Stop current stream."""
        self.update_timer.stop()
        
        if self.stream:
            self.stream.stop()
            self.stream = None
        
        self.camera = None
        self.name_label.setVisible(False)
        self.video_label.setText("No Camera")
        self.video_label.setPixmap(QPixmap())
    
    def _update_frame(self):
        """Update the displayed frame from stream."""
        if not self.stream:
            return
        
        frame = self.stream.get_frame()
        if frame is not None:
            self._display_frame(frame)
        elif not self.stream.is_connected():
            self.video_label.setText("Connection Lost")
    
    def _display_frame(self, frame: np.ndarray):
        """Display a frame on the video label."""
        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        
        # Create QImage
        q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        
        # Scale to fit label while maintaining aspect ratio
        label_size = self.video_label.size()
        scaled_pixmap = QPixmap.fromImage(q_img).scaled(
            label_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        self.video_label.setPixmap(scaled_pixmap)
    
    def set_selected(self, selected: bool):
        """Set selection state."""
        self.is_selected = selected
        if selected:
            self.setStyleSheet("background-color: #1a1a1a; border: 2px solid #0078d4;")
        else:
            self.setStyleSheet("background-color: #1a1a1a;")
    
    def mousePressEvent(self, event):
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Handle double-click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.index)
        super().mouseDoubleClickEvent(event)
    
    def contextMenuEvent(self, event):
        """Show context menu."""
        menu = QMenu(self)
        
        if self.camera:
            snapshot_action = QAction("Take Snapshot", self)
            menu.addAction(snapshot_action)
            
            menu.addSeparator()
            
            playback_action = QAction("Playback", self)
            menu.addAction(playback_action)
            
            ptz_action = QAction("PTZ Control", self)
            menu.addAction(ptz_action)
            
            menu.addSeparator()
            
            fullscreen_action = QAction("Fullscreen", self)
            menu.addAction(fullscreen_action)
            
            menu.addSeparator()
            
            close_action = QAction("Close Stream", self)
            close_action.triggered.connect(self.stop_stream)
            menu.addAction(close_action)
        
        menu.exec(event.globalPos())


class LiveViewWidget(QWidget):
    """Widget containing grid of camera views."""
    
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.cells: List[CameraViewCell] = []
        self.selected_cell: int = -1
        self.rows = 2
        self.cols = 2
        
        self._setup_ui()
        self.set_grid_layout(2, 2)
    
    def _setup_ui(self):
        """Setup UI components."""
        self.layout = QGridLayout(self)
        self.layout.setSpacing(2)
        self.layout.setContentsMargins(2, 2, 2, 2)
    
    def set_grid_layout(self, rows: int, cols: int):
        """Set the grid layout dimensions."""
        self.rows = rows
        self.cols = cols
        
        # Store cameras from existing cells
        existing_cameras = []
        for cell in self.cells:
            if cell.camera:
                existing_cameras.append(cell.camera)
            cell.stop_stream()
            cell.deleteLater()
        
        self.cells.clear()
        
        # Clear layout
        while self.layout.count():
            self.layout.takeAt(0)
        
        # Create new cells
        cell_index = 0
        for row in range(rows):
            for col in range(cols):
                cell = CameraViewCell(cell_index)
                cell.clicked.connect(self._on_cell_clicked)
                cell.double_clicked.connect(self._on_cell_double_clicked)
                
                self.layout.addWidget(cell, row, col)
                self.cells.append(cell)
                cell_index += 1
        
        # Restore cameras to new cells
        for i, camera in enumerate(existing_cameras):
            if i < len(self.cells):
                self.cells[i].set_camera(camera)
    
    def add_camera_to_view(self, camera: Camera):
        """Add a camera to the next available cell or selected cell."""
        # If a cell is selected, use that
        if self.selected_cell >= 0 and self.selected_cell < len(self.cells):
            self.cells[self.selected_cell].set_camera(camera)
            return
        
        # Otherwise find first empty cell
        for cell in self.cells:
            if cell.camera is None:
                cell.set_camera(camera)
                return
        
        # All cells full, replace first cell
        if self.cells:
            self.cells[0].set_camera(camera)
    
    def stop_all_streams(self):
        """Stop all active streams."""
        for cell in self.cells:
            cell.stop_stream()
    
    def _on_cell_clicked(self, index: int):
        """Handle cell click."""
        # Deselect previous
        if self.selected_cell >= 0 and self.selected_cell < len(self.cells):
            self.cells[self.selected_cell].set_selected(False)
        
        # Select new
        self.selected_cell = index
        if index >= 0 and index < len(self.cells):
            self.cells[index].set_selected(True)
    
    def _on_cell_double_clicked(self, index: int):
        """Handle cell double-click (fullscreen toggle)."""
        # TODO: Implement fullscreen for single cell
        pass
