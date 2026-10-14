"""Compatibility import; implementation lives in core.parsers.email_analyzer."""
try:
    from .parsers.email_analyzer import *
except ImportError:
    from parsers.email_analyzer import *
