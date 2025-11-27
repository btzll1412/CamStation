#!/usr/bin/env python3
"""
CamStation - A lightweight Hikvision camera and NVR management application
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from ui.main_window import MainWindow
from utils.config import Config
from utils.database import Database


def main():
    """Main application entry point."""
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("CamStation")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("CamStation")
    
    # Set application style
    app.setStyle("Fusion")
    
    # Initialize configuration
    config = Config()
    
    # Initialize database
    db = Database(config.db_path)
    
    # Create and show main window
    window = MainWindow(config, db)
    window.show()
    
    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
