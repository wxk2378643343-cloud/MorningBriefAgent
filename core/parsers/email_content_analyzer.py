"""Compatibility import for the canonical subscription email analyzer.

New code should import from :mod:`core.parsers.email_analyzer`. This module
remains as a thin compatibility boundary for existing local scripts.
"""

from .email_analyzer import (
    analyze_subscription_email,
    get_latest_high_value_email_digest,
    parse_email_frontmatter_and_body,
)

__all__ = [
    "analyze_subscription_email",
    "get_latest_high_value_email_digest",
    "parse_email_frontmatter_and_body",
]
