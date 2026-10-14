"""Compatibility import; implementation lives in core.agent.context."""
try:
    from .agent.context import *
except ImportError:
    from agent.context import *
