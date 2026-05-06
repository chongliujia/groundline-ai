class GroundlineError(Exception):
    """Base exception for Groundline."""


class UnsupportedSourceTypeError(GroundlineError):
    """Raised when no parser is registered for a source type."""


class BackendUnavailableError(GroundlineError):
    """Raised when a configured backend cannot be reached."""


class ProviderConfigurationError(GroundlineError):
    """Raised when a provider cannot be built from local configuration."""

