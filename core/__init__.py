"""
MorningBriefAgent Core Module
Provides foundation services: config, feishu client, feishu calendar, email analyzer, agy bridge.
"""

from .config import *
from .feishu_client import feishu_client
from .email_analyzer import get_latest_high_value_email_digest

__all__ = [
    "feishu_client",
    "get_latest_high_value_email_digest",
]
