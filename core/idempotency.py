"""Compatibility import; implementation lives in core.integrations.feishu.idempotency."""
try:
    from .integrations.feishu.idempotency import *
except ImportError:
    from integrations.feishu.idempotency import *
