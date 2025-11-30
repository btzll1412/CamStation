"""
Configuration management for CamStation.
"""

import os
import yaml
from pathlib import Path
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class Config:
    """Application configuration manager."""
    
    DEFAULT_CONFIG = {
        "app": {
            "theme": "dark",
            "language": "en",
            "check_updates": True
        },
        "streaming": {
            "default_stream_type": "main",  # main, sub
            "buffer_size": 2,
            "reconnect_attempts": 5,
            "reconnect_delay": 2.0
        },
        "display": {
            "default_grid": [2, 2],
            "show_camera_names": True,
            "show_timestamps": True
        },
        "recording": {
            "snapshot_format": "jpg",
            "snapshot_quality": 95,
            "export_format": "mp4"
        },
        "paths": {
            "snapshots": "~/CamStation/snapshots",
            "exports": "~/CamStation/exports"
        },
        "layout": {
            # Camera layout: maps cell index to camera_id
            # Format: {"grid": [rows, cols], "cameras": {cell_index: camera_id, ...}}
            "grid": [2, 2],
            "cameras": {}
        }
    }
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize configuration.
        
        Args:
            config_dir: Configuration directory path. Defaults to user's config dir.
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # Use platform-appropriate config directory
            if os.name == "nt":  # Windows
                self.config_dir = Path(os.environ.get("APPDATA", "~")) / "CamStation"
            else:  # Linux/macOS
                self.config_dir = Path.home() / ".config" / "camstation"
        
        self.config_dir = self.config_dir.expanduser()
        self.config_file = self.config_dir / "config.yaml"
        self.db_path = self.config_dir / "camstation.db"
        
        # Ensure directories exist
        self._ensure_directories()
        
        # Load or create configuration
        self._config = self._load_config()
    
    def _ensure_directories(self):
        """Ensure all required directories exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Create data directories
        for path_key, path_value in self.DEFAULT_CONFIG["paths"].items():
            path = Path(path_value).expanduser()
            path.mkdir(parents=True, exist_ok=True)
    
    def _load_config(self) -> dict:
        """Load configuration from file or create default."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    config = yaml.safe_load(f) or {}
                
                # Merge with defaults for any missing keys
                return self._merge_config(self.DEFAULT_CONFIG, config)
                
            except Exception as e:
                logger.error(f"Error loading config: {e}")
                return self.DEFAULT_CONFIG.copy()
        else:
            # Create default config file
            self._save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG.copy()
    
    def _merge_config(self, default: dict, loaded: dict) -> dict:
        """Merge loaded config with defaults, keeping loaded values."""
        result = default.copy()
        
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _save_config(self, config: dict = None):
        """Save configuration to file."""
        if config is None:
            config = self._config
        
        try:
            with open(self.config_file, "w") as f:
                yaml.dump(config, f, default_flow_style=False)
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Dot-notation key (e.g., "streaming.buffer_size")
            default: Default value if key not found
        
        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """
        Set a configuration value.
        
        Args:
            key: Dot-notation key (e.g., "streaming.buffer_size")
            value: Value to set
        """
        keys = key.split(".")
        config = self._config
        
        # Navigate to parent
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set value
        config[keys[-1]] = value
        
        # Save to file
        self._save_config()
    
    def get_path(self, key: str) -> Path:
        """
        Get a path configuration value, expanded.
        
        Args:
            key: Path key (e.g., "snapshots")
        
        Returns:
            Expanded Path object
        """
        path_str = self.get(f"paths.{key}", "")
        return Path(path_str).expanduser()
    
    @property
    def snapshot_dir(self) -> Path:
        """Get snapshot directory."""
        return self.get_path("snapshots")
    
    @property
    def export_dir(self) -> Path:
        """Get export directory."""
        return self.get_path("exports")
