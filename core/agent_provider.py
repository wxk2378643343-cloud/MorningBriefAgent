"""Compatibility import; implementation lives in core.agent.provider."""
try:
    from .agent.provider import *
except ImportError:
    from agent.provider import *
