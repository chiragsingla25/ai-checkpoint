"""AI Checkpoint: named restore points for AI chats.

The core (model, redaction, store) is stdlib only; the MCP server and
evaluation kit import their optional dependencies lazily.
"""
from .errors import CheckpointError, NotFoundError, StoreError, ValidationError
from .model import Checkpoint, Decision, LastExchange, VerbatimItem
from .redact import redact_obj, redact_text
from .store import GitStore, ListEntry, Listing, SaveResult, default_root

__version__ = "0.1.0"

__all__ = [
    "Checkpoint", "Decision", "VerbatimItem", "LastExchange",
    "GitStore", "SaveResult", "Listing", "ListEntry", "default_root",
    "redact_text", "redact_obj",
    "CheckpointError", "ValidationError", "NotFoundError", "StoreError",
]
