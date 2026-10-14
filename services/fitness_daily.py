"""Compatibility module alias for services.lifestyle.fitness_daily."""
import sys
try:
    from .lifestyle import fitness_daily as _implementation
except ImportError:
    from lifestyle import fitness_daily as _implementation
sys.modules[__name__] = _implementation
