"""Errors shared by the core and its clients; no UI dependencies."""


class RomkitError(Exception):
    """Base for errors that can be presented to a user."""


class ValidationError(RomkitError, ValueError):
    pass


class SerializationError(RomkitError, ValueError):
    pass


class WorkspaceError(RomkitError):
    pass


class PlatformError(RomkitError):
    pass


class TransformError(RomkitError):
    pass
