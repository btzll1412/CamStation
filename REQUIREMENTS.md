# CamStation - Program Requirements

## Vision
A lightweight, rock-solid camera management application that combines the best features from UniFi Protect and Digital Watchdog, while being faster and easier to use than iVMS-4200.

## Core Principles

1. **Never Freeze** - All network/heavy operations are async. UI stays responsive with 32+ cameras.
2. **Instant Feedback** - Every action shows immediate visual feedback (loading states, progress, status).
3. **Minimal Clicks** - Common tasks require minimum interaction. No dialog hunting.
4. **Clean Design** - Modern, minimal interface. No clutter, no bloat.
5. **Local Only** - No cloud, no telemetry, no accounts. Your cameras, your data.

---

## Target Performance

| Metric | Target |
|--------|--------|
| Startup time | < 2 seconds |
| Add device | < 5 seconds |
| Stream start | < 1 second |
| UI response | < 16ms (60fps) |
| Memory (idle) | < 200MB |
| Memory (32 cameras) | < 1.5GB |
| CPU (32 cameras) | < 30% |

---

## Feature Roadmap

### Phase 1: Core Foundation
- [x] Project structure
- [x] ISAPI client for Hikvision
- [x] Database layer (SQLite)
- [x] Basic RTSP streaming
- [ ] **Async architecture overhaul**
- [ ] **Connection manager with pooling**
- [ ] **Stream manager with lazy loading**

### Phase 2: Device Onboarding (Easy Setup)
Best of: UniFi Protect's simplicity + DW's flexibility

- [ ] **One-page Add Device wizard**
  - IP/hostname input with validation
  - Auto-detect device type (NVR vs IP Camera)
  - Test connection with live feedback
  - Auto-discover all channels
  - One-click "Add All Cameras"

- [ ] **Network auto-discovery** (optional)
  - Scan local network for Hikvision devices
  - Show discovered devices in list
  - Bulk add multiple devices

- [ ] **Device health monitoring**
  - Background connectivity checks
  - Visual status indicators (green/yellow/red)
  - Notification on device offline

### Phase 3: Live View (Rock Solid)
Best of: UniFi's clean grid + DW's flexibility

- [ ] **Responsive camera grid**
  - Layouts: 1x1, 2x2, 3x3, 4x4, 5x5, 6x6, 8x4 (32 cam)
  - Custom layouts (drag to resize cells)
  - Virtual scrolling (only render visible cells)

- [ ] **Smart streaming**
  - On-demand: Only connect when camera is visible
  - Sub-stream for grid, main-stream for fullscreen
  - Auto-reconnect with exponential backoff
  - Frame dropping under load (prioritize UI)

- [ ] **Camera interactions**
  - Single-click: Select camera (show info bar)
  - Double-click: Fullscreen with smooth animation
  - Right-click: Context menu (snapshot, playback, PTZ, info)
  - Drag-drop: Rearrange cameras in grid

- [ ] **Quick actions bar** (appears on camera hover)
  - 📸 Snapshot
  - ▶️ Playback (jump to timeline)
  - 🎮 PTZ (if supported)
  - 🔊 Audio (if supported)
  - ⓘ Camera info

- [ ] **Fullscreen mode**
  - Press F or double-click
  - ESC to exit
  - Overlay controls (fade after 3 seconds)
  - Cycle through cameras with arrow keys

### Phase 4: Timeline Playback (The Star Feature)
Best of: UniFi's timeline + DW's calendar + our innovations

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back to Live    │ Camera: Front Door │ 📅 Nov 29, 2025  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                                                             │
│                    Playback Video                           │
│                                                             │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  ◀◀  ❚❚  ▶▶    1x ▼    🔊━━━━○     📸  💾  ✂️            │
├─────────────────────────────────────────────────────────────┤
│                         │                                   │
│  ░░░▓▓▓░░░░░▓▓▓▓░░░░░░░|░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │
│  00:00     06:00    12:00    18:00    NOW                   │
│                         ▲                                   │
│                    Current: 11:42:33                        │
└─────────────────────────────────────────────────────────────┘
```

- [ ] **Continuous timeline**
  - 24-hour view (default)
  - Zoom: 1hr, 6hr, 12hr, 24hr, 7-day
  - Pinch/scroll to zoom
  - Smooth horizontal scrolling

- [ ] **Visual event markers**
  - Motion detection (blue bars)
  - Line crossing (orange bars)
  - Intrusion (red bars)
  - LPR/vehicle (purple bars)
  - Recording gaps (gray stripes)

- [ ] **Timeline interactions**
  - Click anywhere to jump
  - Drag playhead to scrub
  - Hover for thumbnail preview (mini popup)
  - Keyboard: ←/→ skip 10sec, Shift+←/→ skip 1min

- [ ] **Playback controls**
  - Play/Pause (spacebar)
  - Speed: 0.5x, 1x, 2x, 4x, 8x, 16x
  - Frame step: < > keys
  - Skip to next/prev event

- [ ] **Calendar picker** (DW style)
  - Click date to show calendar popup
  - Days with recordings highlighted
  - Quick jump: Today, Yesterday, This Week

- [ ] **Multi-camera sync** (DW style)
  - Select multiple cameras
  - Synchronized playback across all
  - Single timeline controls all

- [ ] **Quick export**
  - 📸 Snapshot current frame
  - ✂️ Clip: Mark in/out points on timeline
  - 💾 Export clip as MP4
  - Progress bar with cancel option

### Phase 5: PTZ Controls
Best of: Intuitive + Powerful

- [ ] **On-screen joystick**
  - Drag to pan/tilt
  - Center = stop
  - Distance from center = speed

- [ ] **Zoom controls**
  - +/- buttons
  - Mouse wheel zoom
  - Pinch to zoom (touch)

- [ ] **Preset management**
  - Visual preset grid (thumbnails)
  - Click to go to preset
  - Long-press to save current position
  - Rename/delete presets

- [ ] **PTZ tour**
  - Create tour from presets
  - Set dwell time per preset
  - Start/stop tour

### Phase 6: Settings & Polish

- [ ] **Settings panel** (slide-out)
  - Appearance: Theme (light/dark/auto)
  - Streaming: Quality, buffer size
  - Storage: Snapshot/export paths
  - About: Version, licenses

- [ ] **Keyboard shortcuts**
  - Full keyboard navigation
  - Customizable shortcuts
  - Shortcut help overlay (?)

---

## UI Layout (Final Design)

```
┌──────────────────────────────────────────────────────────────┐
│ 🎥 CamStation          [🔍 Search]  [+ Add Device]  [⚙]  [─□×]│
├────────────┬─────────────────────────────────────────────────┤
│            │ ┌─────────┬─────────┬─────────┬─────────┐       │
│ 📁 Devices │ │         │         │         │         │       │
│            │ │  Cam 1  │  Cam 2  │  Cam 3  │  Cam 4  │       │
│ ▼ NVR-01   │ │         │         │         │         │       │
│   └ Cam 1  │ ├─────────┼─────────┼─────────┼─────────┤       │
│   └ Cam 2  │ │         │         │         │         │       │
│   └ Cam 3  │ │  Cam 5  │  Cam 6  │  Cam 7  │  Cam 8  │       │
│   └ Cam 4  │ │         │         │         │         │       │
│            │ └─────────┴─────────┴─────────┴─────────┘       │
│ ▼ NVR-02   │                                                 │
│   └ Cam 5  │ [1x1] [2x2] [3x3] [4x4] [5x5] [Custom]         │
│   └ ...    │                                                 │
│            ├─────────────────────────────────────────────────┤
│ ● 8 Online │ Timeline (when in playback mode)                │
│ ○ 0 Offline│ ░░░▓▓▓░░░░░▓▓▓▓░░░░|░░░░░░░░░░░░░░░░░░░░░░░░░░ │
└────────────┴─────────────────────────────────────────────────┘
```

---

## Technical Architecture

### Threading Model (Never Freeze)

```
┌─────────────────────────────────────────────────────────────┐
│                      Main Thread (UI)                        │
│  - PyQt6 event loop                                         │
│  - Render frames (QImage)                                   │
│  - Handle user input                                        │
│  - NEVER do network/disk I/O here                           │
└─────────────────────────────────────────────────────────────┘
          ▲                    ▲                    ▲
          │ Signals            │ Signals            │ Signals
          ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Stream Workers  │  │   API Workers   │  │   DB Workers    │
│ (QThread pool)  │  │   (QThread)     │  │   (QThread)     │
│                 │  │                 │  │                 │
│ - RTSP capture  │  │ - Device disc.  │  │ - Load devices  │
│ - Frame decode  │  │ - PTZ commands  │  │ - Save settings │
│ - Frame queue   │  │ - Event search  │  │ - Query history │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

### Stream Management (32+ Cameras)

```python
class StreamManager:
    """
    Manages camera streams with lazy loading and resource limits.

    - Only active (visible) cameras have live streams
    - Streams use sub-stream by default (lower bandwidth)
    - Main-stream used only for fullscreen/export
    - Max concurrent streams configurable (default: 16)
    - LRU eviction when limit reached
    """
```

### Connection Pooling

```python
class ConnectionPool:
    """
    Reusable HTTP connections to devices.

    - One connection per device (not per camera)
    - Automatic reconnection on failure
    - Health check pings in background
    - Connection timeout: 5 seconds
    - Request timeout: 10 seconds
    """
```

---

## File Structure (Proposed)

```
CamStation/
├── src/
│   ├── main.py                    # Entry point
│   ├── app.py                     # QApplication setup
│   │
│   ├── core/                      # Core services (async)
│   │   ├── __init__.py
│   │   ├── connection_pool.py     # HTTP connection pooling
│   │   ├── stream_manager.py      # RTSP stream lifecycle
│   │   ├── device_manager.py      # Device discovery & health
│   │   └── event_manager.py       # Event aggregation
│   │
│   ├── api/                       # Hikvision API
│   │   ├── __init__.py
│   │   └── isapi_client.py        # ISAPI implementation
│   │
│   ├── models/                    # Data models
│   │   ├── __init__.py
│   │   └── device.py              # Device, Camera, Event models
│   │
│   ├── ui/                        # User interface
│   │   ├── __init__.py
│   │   ├── main_window.py         # Main window
│   │   ├── styles.py              # QSS stylesheets
│   │   │
│   │   ├── components/            # Reusable UI components
│   │   │   ├── __init__.py
│   │   │   ├── camera_cell.py     # Single camera view
│   │   │   ├── camera_grid.py     # Multi-camera grid
│   │   │   ├── device_tree.py     # Device sidebar
│   │   │   ├── timeline.py        # Playback timeline
│   │   │   ├── ptz_control.py     # PTZ joystick
│   │   │   └── loading.py         # Loading spinners/overlays
│   │   │
│   │   ├── dialogs/               # Modal dialogs
│   │   │   ├── __init__.py
│   │   │   ├── add_device.py      # Add device wizard
│   │   │   ├── settings.py        # Settings panel
│   │   │   └── export.py          # Export dialog
│   │   │
│   │   └── widgets/               # Custom widgets
│   │       ├── __init__.py
│   │       ├── clickable_slider.py
│   │       └── hover_button.py
│   │
│   └── utils/                     # Utilities
│       ├── __init__.py
│       ├── config.py              # Configuration
│       ├── database.py            # SQLite database
│       └── logging.py             # Logging setup
│
├── resources/
│   ├── icons/                     # SVG icons
│   └── themes/                    # QSS theme files
│
├── tests/
│   ├── test_api.py
│   ├── test_streaming.py
│   └── test_ui.py
│
├── REQUIREMENTS.md                # This file
├── README.md
├── requirements.txt
└── setup.py
```

---

## Best Features We're Taking

### From UniFi Protect:
- Clean, minimal interface
- Continuous timeline scrubber
- Visual motion markers on timeline
- Hover thumbnails on timeline
- Seamless live-to-playback transition
- Simple device setup

### From Digital Watchdog:
- Calendar date picker
- Multi-camera synchronized playback
- Flexible grid layouts
- Quick export from timeline
- Device health dashboard

### Our Innovations:
- Zero-freeze guarantee (async everything)
- Smart streaming (sub-stream grid, main-stream fullscreen)
- Virtual scrolling (handle 32+ cameras)
- Keyboard-first navigation
- Instant search across all cameras
- One-click common actions

---

## Success Criteria

Before v1.0 release:

- [ ] Add device in under 30 seconds (including all cameras)
- [ ] View 32 cameras simultaneously without UI lag
- [ ] Switch to playback in under 2 seconds
- [ ] Scrub timeline smoothly at 60fps
- [ ] Export clip in real-time (1 min video = 1 min export)
- [ ] Zero crashes in 24-hour stress test
- [ ] Works on Windows 10+, macOS 12+, Ubuntu 22.04+
