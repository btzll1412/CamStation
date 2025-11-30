"""
Modern, clean stylesheet for CamStation.

Design principles:
- Dark theme (easy on eyes for monitoring)
- High contrast for important elements
- Minimal borders and shadows
- Consistent spacing
"""

# Color palette
COLORS = {
    # Base colors
    "bg_dark": "#0d1117",      # Darkest background
    "bg_medium": "#161b22",     # Panel background
    "bg_light": "#21262d",      # Elevated surfaces
    "bg_hover": "#30363d",      # Hover state

    # Borders
    "border": "#30363d",
    "border_light": "#484f58",

    # Text
    "text_primary": "#e6edf3",
    "text_secondary": "#8b949e",
    "text_muted": "#6e7681",

    # Accent colors
    "accent_blue": "#2f81f7",
    "accent_green": "#3fb950",
    "accent_red": "#f85149",
    "accent_orange": "#d29922",
    "accent_purple": "#a371f7",

    # Status colors
    "online": "#3fb950",
    "offline": "#f85149",
    "warning": "#d29922",
    "info": "#2f81f7",

    # Timeline event colors
    "motion": "#2f81f7",
    "line_crossing": "#d29922",
    "intrusion": "#f85149",
    "lpr": "#a371f7",
    "recording": "#30363d",
}


def get_stylesheet() -> str:
    """Get the main application stylesheet."""
    return f"""
    /* ===== Global ===== */
    QWidget {{
        background-color: {COLORS['bg_medium']};
        color: {COLORS['text_primary']};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        font-size: 13px;
    }}

    /* ===== Main Window ===== */
    QMainWindow {{
        background-color: {COLORS['bg_dark']};
    }}

    /* ===== Menu Bar ===== */
    QMenuBar {{
        background-color: {COLORS['bg_dark']};
        border-bottom: 1px solid {COLORS['border']};
        padding: 4px 8px;
    }}

    QMenuBar::item {{
        background-color: transparent;
        padding: 6px 12px;
        border-radius: 4px;
    }}

    QMenuBar::item:selected {{
        background-color: {COLORS['bg_hover']};
    }}

    QMenu {{
        background-color: {COLORS['bg_light']};
        border: 1px solid {COLORS['border']};
        border-radius: 6px;
        padding: 4px;
    }}

    QMenu::item {{
        padding: 8px 24px 8px 12px;
        border-radius: 4px;
    }}

    QMenu::item:selected {{
        background-color: {COLORS['accent_blue']};
    }}

    QMenu::separator {{
        height: 1px;
        background-color: {COLORS['border']};
        margin: 4px 8px;
    }}

    /* ===== Tool Bar ===== */
    QToolBar {{
        background-color: {COLORS['bg_dark']};
        border-bottom: 1px solid {COLORS['border']};
        padding: 4px 8px;
        spacing: 4px;
    }}

    QToolBar::separator {{
        width: 1px;
        background-color: {COLORS['border']};
        margin: 4px 8px;
    }}

    QToolButton {{
        background-color: transparent;
        border: none;
        border-radius: 6px;
        padding: 8px 16px;
        color: {COLORS['text_secondary']};
        font-weight: 500;
    }}

    QToolButton:hover {{
        background-color: {COLORS['bg_hover']};
        color: {COLORS['text_primary']};
    }}

    QToolButton:pressed {{
        background-color: {COLORS['bg_light']};
    }}

    QToolButton:checked {{
        background-color: {COLORS['accent_blue']};
        color: white;
    }}

    /* ===== Buttons ===== */
    QPushButton {{
        background-color: {COLORS['bg_light']};
        border: 1px solid {COLORS['border']};
        border-radius: 6px;
        padding: 8px 16px;
        font-weight: 500;
        min-width: 80px;
    }}

    QPushButton:hover {{
        background-color: {COLORS['bg_hover']};
        border-color: {COLORS['border_light']};
    }}

    QPushButton:pressed {{
        background-color: {COLORS['bg_medium']};
    }}

    QPushButton:disabled {{
        background-color: {COLORS['bg_medium']};
        color: {COLORS['text_muted']};
        border-color: {COLORS['border']};
    }}

    /* Primary button */
    QPushButton#primary {{
        background-color: {COLORS['accent_blue']};
        border-color: {COLORS['accent_blue']};
        color: white;
    }}

    QPushButton#primary:hover {{
        background-color: #388bfd;
    }}

    /* Danger button */
    QPushButton#danger {{
        background-color: {COLORS['accent_red']};
        border-color: {COLORS['accent_red']};
        color: white;
    }}

    /* ===== Input Fields ===== */
    QLineEdit, QSpinBox, QComboBox {{
        background-color: {COLORS['bg_dark']};
        border: 1px solid {COLORS['border']};
        border-radius: 6px;
        padding: 8px 12px;
        selection-background-color: {COLORS['accent_blue']};
    }}

    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border-color: {COLORS['accent_blue']};
        outline: none;
    }}

    QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
        background-color: {COLORS['bg_medium']};
        color: {COLORS['text_muted']};
    }}

    QComboBox::drop-down {{
        border: none;
        padding-right: 8px;
    }}

    QComboBox::down-arrow {{
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {COLORS['text_secondary']};
        margin-right: 8px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {COLORS['bg_light']};
        border: 1px solid {COLORS['border']};
        border-radius: 6px;
        selection-background-color: {COLORS['accent_blue']};
    }}

    /* ===== Scroll Bars ===== */
    QScrollBar:vertical {{
        background-color: transparent;
        width: 12px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background-color: {COLORS['border']};
        border-radius: 6px;
        min-height: 30px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {COLORS['border_light']};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QScrollBar:horizontal {{
        background-color: transparent;
        height: 12px;
        margin: 0;
    }}

    QScrollBar::handle:horizontal {{
        background-color: {COLORS['border']};
        border-radius: 6px;
        min-width: 30px;
        margin: 2px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background-color: {COLORS['border_light']};
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* ===== Tree Widget ===== */
    QTreeWidget {{
        background-color: {COLORS['bg_dark']};
        border: none;
        outline: none;
    }}

    QTreeWidget::item {{
        padding: 6px 8px;
        border-radius: 4px;
    }}

    QTreeWidget::item:hover {{
        background-color: {COLORS['bg_hover']};
    }}

    QTreeWidget::item:selected {{
        background-color: {COLORS['accent_blue']};
    }}

    QTreeWidget::branch {{
        background-color: transparent;
    }}

    QHeaderView::section {{
        background-color: {COLORS['bg_medium']};
        border: none;
        border-bottom: 1px solid {COLORS['border']};
        padding: 8px;
        font-weight: 600;
    }}

    /* ===== Dock Widget ===== */
    QDockWidget {{
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
    }}

    QDockWidget::title {{
        background-color: {COLORS['bg_dark']};
        padding: 8px;
        font-weight: 600;
    }}

    /* ===== Status Bar ===== */
    QStatusBar {{
        background-color: {COLORS['bg_dark']};
        border-top: 1px solid {COLORS['border']};
        padding: 4px 8px;
    }}

    QStatusBar::item {{
        border: none;
    }}

    /* ===== Group Box ===== */
    QGroupBox {{
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        margin-top: 16px;
        padding-top: 16px;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 8px;
        color: {COLORS['text_secondary']};
        font-weight: 600;
    }}

    /* ===== Progress Bar ===== */
    QProgressBar {{
        background-color: {COLORS['bg_dark']};
        border: none;
        border-radius: 4px;
        height: 8px;
        text-align: center;
    }}

    QProgressBar::chunk {{
        background-color: {COLORS['accent_blue']};
        border-radius: 4px;
    }}

    /* ===== Slider ===== */
    QSlider::groove:horizontal {{
        background-color: {COLORS['bg_dark']};
        height: 6px;
        border-radius: 3px;
    }}

    QSlider::handle:horizontal {{
        background-color: {COLORS['accent_blue']};
        width: 16px;
        height: 16px;
        margin: -5px 0;
        border-radius: 8px;
    }}

    QSlider::handle:horizontal:hover {{
        background-color: #388bfd;
    }}

    QSlider::sub-page:horizontal {{
        background-color: {COLORS['accent_blue']};
        border-radius: 3px;
    }}

    /* ===== Tab Widget ===== */
    QTabWidget::pane {{
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        background-color: {COLORS['bg_medium']};
    }}

    QTabBar::tab {{
        background-color: transparent;
        padding: 10px 20px;
        margin-right: 4px;
        border-bottom: 2px solid transparent;
    }}

    QTabBar::tab:selected {{
        border-bottom-color: {COLORS['accent_blue']};
        color: {COLORS['accent_blue']};
    }}

    QTabBar::tab:hover:!selected {{
        background-color: {COLORS['bg_hover']};
    }}

    /* ===== Dialog ===== */
    QDialog {{
        background-color: {COLORS['bg_medium']};
    }}

    /* ===== Label ===== */
    QLabel {{
        background-color: transparent;
    }}

    QLabel#heading {{
        font-size: 18px;
        font-weight: 600;
    }}

    QLabel#subheading {{
        font-size: 14px;
        color: {COLORS['text_secondary']};
    }}

    /* ===== Check Box ===== */
    QCheckBox {{
        spacing: 8px;
    }}

    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {COLORS['border']};
        border-radius: 4px;
        background-color: {COLORS['bg_dark']};
    }}

    QCheckBox::indicator:checked {{
        background-color: {COLORS['accent_blue']};
        border-color: {COLORS['accent_blue']};
    }}

    QCheckBox::indicator:hover {{
        border-color: {COLORS['accent_blue']};
    }}

    /* ===== Tooltip ===== */
    QToolTip {{
        background-color: {COLORS['bg_light']};
        border: 1px solid {COLORS['border']};
        border-radius: 4px;
        padding: 6px 10px;
        color: {COLORS['text_primary']};
    }}

    /* ===== Splitter ===== */
    QSplitter::handle {{
        background-color: {COLORS['border']};
    }}

    QSplitter::handle:horizontal {{
        width: 1px;
    }}

    QSplitter::handle:vertical {{
        height: 1px;
    }}
    """


def get_camera_cell_style(selected: bool = False, connected: bool = False) -> str:
    """Get style for camera cell."""
    if selected:
        border_color = COLORS['accent_blue']
        border_width = "2px"
    else:
        border_color = COLORS['border']
        border_width = "1px"

    return f"""
        background-color: {COLORS['bg_dark']};
        border: {border_width} solid {border_color};
        border-radius: 8px;
    """


def get_timeline_style() -> str:
    """Get style for timeline component."""
    return f"""
        QWidget#timeline {{
            background-color: {COLORS['bg_dark']};
            border-top: 1px solid {COLORS['border']};
        }}

        QWidget#timeline_track {{
            background-color: {COLORS['bg_light']};
            border-radius: 4px;
        }}

        QLabel#time_label {{
            color: {COLORS['text_secondary']};
            font-size: 11px;
        }}

        QLabel#current_time {{
            color: {COLORS['text_primary']};
            font-size: 14px;
            font-weight: 600;
        }}
    """


def get_playback_controls_style() -> str:
    """Get style for playback controls."""
    return f"""
        QPushButton#playback_btn {{
            background-color: transparent;
            border: none;
            border-radius: 20px;
            min-width: 40px;
            min-height: 40px;
            max-width: 40px;
            max-height: 40px;
            font-size: 18px;
        }}

        QPushButton#playback_btn:hover {{
            background-color: {COLORS['bg_hover']};
        }}

        QPushButton#play_btn {{
            background-color: {COLORS['accent_blue']};
            min-width: 48px;
            min-height: 48px;
            max-width: 48px;
            max-height: 48px;
            border-radius: 24px;
        }}

        QPushButton#play_btn:hover {{
            background-color: #388bfd;
        }}

        QComboBox#speed_selector {{
            min-width: 60px;
            padding: 4px 8px;
        }}
    """
