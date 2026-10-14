"""Compatibility import; implementation lives in core.integrations.feishu.task_gateway."""
try:
    from .integrations.feishu.task_gateway import *
except ImportError:
    from integrations.feishu.task_gateway import *
