"""Compatibility module alias for services.communications.chat_digest."""
import sys
try:
    from .communications import chat_digest as _implementation
except ImportError:
    from communications import chat_digest as _implementation
sys.modules[__name__] = _implementation
