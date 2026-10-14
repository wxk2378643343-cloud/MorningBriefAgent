"""Compatibility import; implementation lives in core.agent.contracts."""
try:
    from .agent.contracts import *
except ImportError:
    from agent.contracts import *
