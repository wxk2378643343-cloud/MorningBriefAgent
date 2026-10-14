"""Compatibility module alias for services.content.global_news."""
import sys
try:
    from .content import global_news as _implementation
except ImportError:
    from content import global_news as _implementation
sys.modules[__name__] = _implementation
