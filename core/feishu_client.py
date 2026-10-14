"""Compatibility import; implementation lives in core.integrations.feishu.client."""
try:
    from .integrations.feishu.client import *
except ImportError:
    from integrations.feishu.client import *
