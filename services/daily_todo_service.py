"""Compatibility module alias for services.planning.daily_todo."""
import sys
try:
    from .planning import daily_todo as _implementation
except ImportError:
    from planning import daily_todo as _implementation
sys.modules[__name__] = _implementation
