"""Compatibility import; implementation lives in core.runtime.config."""
try:
    from .runtime.config import *
except ImportError:
    from runtime.config import *
