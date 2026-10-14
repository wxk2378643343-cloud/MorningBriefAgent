"""Compatibility module alias for services.planning.review_sync."""
import sys
try:
    from .planning import review_sync as _implementation
except ImportError:
    from planning import review_sync as _implementation
sys.modules[__name__] = _implementation
