"""Compatibility bridge for backend.config. Direct imports should use backend.core.config."""
from backend.core.config import Settings, settings

__all__ = ["Settings", "settings"]
