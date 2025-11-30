"""
Build script for creating CamStation Windows executable.

Usage:
    python build_exe.py

Requirements:
    pip install pyinstaller

Output:
    dist/CamStation.exe (single file executable)
    or
    dist/CamStation/ (folder with exe and dependencies)
"""

import subprocess
import sys
import os

def build():
    """Build the Windows executable."""

    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=CamStation",
        "--windowed",  # No console window
        "--onefile",   # Single exe file
        "--icon=resources/icon.ico",  # App icon (if exists)
        "--add-data=resources;resources",  # Include resources folder
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "--hidden-import=PyQt6",
        "--hidden-import=sqlalchemy",
        "--hidden-import=onvif",
        "--hidden-import=zeep",
        "--hidden-import=wsdiscovery",
        "--collect-all=onvif",
        "--collect-all=zeep",
        "src/main.py"
    ]

    # Check if icon exists, if not remove that argument
    if not os.path.exists("resources/icon.ico"):
        cmd = [c for c in cmd if "icon.ico" not in c]

    # Check if resources folder exists
    if not os.path.exists("resources"):
        cmd = [c for c in cmd if "resources;resources" not in c]

    print("Building CamStation executable...")
    print(f"Command: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
        print("\n✓ Build complete!")
        print("  Executable: dist/CamStation.exe")
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Build failed: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("\n✗ PyInstaller not found. Install it with:")
        print("  pip install pyinstaller")
        sys.exit(1)

if __name__ == "__main__":
    build()
