"""Compatibility import; implementation lives in core.integrations.feishu.errors."""
try:
    from .integrations.feishu.errors import *
except ImportError:
    from integrations.feishu.errors import *
