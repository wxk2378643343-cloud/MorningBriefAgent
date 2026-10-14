"""Compatibility import; implementation lives in core.integrations.feishu.gateway."""
try:
    from .integrations.feishu.gateway import *
except ImportError:
    from integrations.feishu.gateway import *
