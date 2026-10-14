"""Stable error taxonomy for external integrations."""


class IntegrationError(RuntimeError):
    """Base class for provider failures."""


class RetryableIntegrationError(IntegrationError):
    """Temporary network, timeout, rate-limit, or 5xx failure."""


class ProviderResponseError(IntegrationError):
    """Provider returned a valid response containing an application error."""
