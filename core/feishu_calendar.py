"""Compatibility import; implementation lives in core.integrations.feishu.calendar."""
try:
    from .integrations.feishu.calendar import *
except ImportError:
    from integrations.feishu.calendar import *
