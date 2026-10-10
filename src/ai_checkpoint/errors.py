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


class RequestError(ValidationError):
    """A request-level validation error whose message is the whole text (no field prefix)."""

    def __init__(self, message: str):
        super().__init__("request", message)

    def __str__(self) -> str:
        return self.message


class CheckError(ValidationError):
    """Save-time checks failed. ``problems`` lists every failing check; nothing was written."""

    def __init__(self, problems: list):
        self.problems = list(problems)
        n = len(self.problems)
        head = (f"Save rejected: {n} problem{'s' if n != 1 else ''} found. Nothing was saved. "
                "Fix all of them and call save_checkpoint again.")
        text = head + "".join(f"\n{i}. {m}" for i, m in enumerate(self.problems, 1))
        super().__init__("checks", text)

    def __str__(self) -> str:
        return self.message


class NotFoundError(CheckpointError, LookupError):
    """A checkpoint ref did not resolve. ``ref`` is the ref as given."""

    def __init__(self, ref: str, message: str | None = None):
        self.ref = ref
        super().__init__(message or f"checkpoint not found: {ref!r}")

    def __str__(self) -> str:  # LookupError would repr() the arg otherwise
        return self.args[0]


class StoreError(CheckpointError):
    """The store (git or filesystem) failed."""
