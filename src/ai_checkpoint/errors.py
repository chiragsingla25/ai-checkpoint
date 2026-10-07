"""Exceptions raised by the checkpoint core. Stdlib only."""
from __future__ import annotations


class CheckpointError(Exception):
    """Base class for all errors raised by ai_checkpoint."""


class ValidationError(CheckpointError, ValueError):
    """A checkpoint failed validation. ``field`` names the offending field."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


class NotFoundError(CheckpointError, LookupError):
    """A checkpoint ref did not resolve. ``ref`` is the ref as given."""

    def __init__(self, ref: str, message: str | None = None):
        self.ref = ref
        super().__init__(message or f"checkpoint not found: {ref!r}")

    def __str__(self) -> str:  # LookupError would repr() the arg otherwise
        return self.args[0]


class StoreError(CheckpointError):
    """The store (git or filesystem) failed."""
