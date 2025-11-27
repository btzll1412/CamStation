# CamStation

A lightweight, open-source desktop application for viewing, configuring, and managing Hikvision cameras and NVRs. Built as a fast, clean alternative to iVMS-4200 — no bloat, no telemetry, just the features you need.

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)

## Features

### Current
- 🚧 Under active development

### Planned
- **Device Management** — Add NVRs and standalone IP cameras, auto-discover channels
- **Live View** — Single and multi-camera grid layouts with smooth streaming
- **Playback** — Search and view recordings stored on NVR/camera, timeline scrubbing
- **PTZ Control** — Full pan/tilt/zoom control for supported cameras
- **Smart Event Search** — Motion detection, line crossing, intrusion events
- **LPR Search** — Search license plates by number, time range, and camera
- **Configuration** — Adjust camera settings, detection zones, network config
- **Export** — Save snapshots and video clips locally

## Why CamStation?

| Feature | iVMS-4200 | CamStation |
|---------|-----------|------------|
| Lightweight | ❌ Heavy, slow startup | ✅ Fast and minimal |
| Cross-platform | ⚠️ Windows-focused | ✅ Windows, macOS, Linux |
| Telemetry | ❌ Phones home | ✅ Fully local, no cloud |
| Open Source | ❌ Proprietary | ✅ MIT License |
| Bloat-free | ❌ Tons of unused features | ✅ Just what you need |

## Installation

### Prerequisites
- Python 3.9 or higher
- FFmpeg (for video streaming)

### From Source
```bash
git clone https://github.com/btzll1412/CamStation.git
cd CamStation
pip install -r requirements.txt
python src/main.py
```

### From Release
*Coming soon — pre-built binaries for Windows, macOS, and Linux*

## Quick Start

1. Launch CamStation
2. Click **Add Device** → Enter your NVR/camera IP, username, and password
3. CamStation will auto-discover all connected channels
4. Double-click any camera to open live view
5. Right-click for playback, configuration, and more

## Screenshots

*Coming soon*

## Architecture

CamStation communicates with Hikvision devices using:
- **ISAPI** — Hikvision's REST-like HTTP API for configuration and events
- **RTSP** — Real-time streaming for live view and playback

All recordings remain on your NVR/camera — CamStation is purely a client.

## Roadmap

- [x] Project setup
- [ ] ISAPI device discovery and authentication
- [ ] Basic live view (single camera)
- [ ] Multi-camera grid view
- [ ] Device tree management
- [ ] Playback with timeline
- [ ] PTZ controls
- [ ] Event search (motion, line crossing, etc.)
- [ ] LPR plate search
- [ ] Configuration panels
- [ ] Export functionality
- [ ] Home Assistant integration (optional)
- [ ] Pre-built releases

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Disclaimer

This project is not affiliated with, endorsed by, or connected to Hikvision in any way. All trademarks are the property of their respective owners.

## Acknowledgments

- The Hikvision ISAPI documentation community
- Everyone frustrated with iVMS-4200 who inspired this project
