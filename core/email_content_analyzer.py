"""Compatibility import; implementation lives in core.parsers.email_content_analyzer."""
try:
    from .parsers.email_content_analyzer import *
except ImportError:
    from parsers.email_content_analyzer import *
