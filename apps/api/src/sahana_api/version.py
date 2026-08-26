"""Single source of truth for the application version.

The value is intentionally defined here rather than read from package metadata so
that it is available without an installed distribution (for example inside a
container built from source) and can be imported cheaply at module load time.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
