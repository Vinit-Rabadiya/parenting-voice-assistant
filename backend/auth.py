"""Compatibility bridge for backend.auth. Direct imports should use backend.core.security."""
from backend.core.security import require_authenticated_user, bearer

__all__ = ["require_authenticated_user", "bearer"]
