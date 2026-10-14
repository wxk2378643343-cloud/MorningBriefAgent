"""Compatibility module alias for services.content.inspect_and_brief."""
import sys
try:
    from .content import inspect_and_brief as _implementation
except ImportError:
    from content import inspect_and_brief as _implementation
sys.modules[__name__] = _implementation
