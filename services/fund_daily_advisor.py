"""Compatibility module alias for services.finance.fund_advisor."""
import sys
try:
    from .finance import fund_advisor as _implementation
except ImportError:
    from finance import fund_advisor as _implementation
sys.modules[__name__] = _implementation
