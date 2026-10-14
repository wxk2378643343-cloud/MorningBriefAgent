"""Compatibility import; implementation lives in core.agent.agy_bridge."""
try:
    from .agent.agy_bridge import *
except ImportError:
    from agent.agy_bridge import *
