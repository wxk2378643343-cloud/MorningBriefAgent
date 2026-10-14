"""Compatibility import; implementation lives in core.runtime.doctor."""
try:
    from .runtime.doctor import *
except ImportError:
    from runtime.doctor import *
