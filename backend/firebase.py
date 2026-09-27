"""Compatibility bridge for backend.firebase. Direct imports should use backend.core.firebase."""
from backend.core.firebase import initialize_firebase

__all__ = ["initialize_firebase"]
