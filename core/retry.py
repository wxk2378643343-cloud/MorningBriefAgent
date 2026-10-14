"""Compatibility import; implementation lives in core.integrations.feishu.retry."""
try:
    from .integrations.feishu.retry import *
except ImportError:
    from integrations.feishu.retry import *
