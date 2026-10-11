"""Git-backed checkpoint store. Stdlib only (shells out to the ``git`` binary).

Layout::

    <root>/.git
    <root>/checkpoints/cp-001.json
    <root>/checkpoints/cp-002.json

Each save writes one new file and makes exactly one commit
``checkpoint: cp-NNN <chat_name>/<checkpoint_name>``. Files are never
rewritten. Ids come from max(files on disk, ids ever committed) + 1, so they
are not reused even if a file is deleted from the working tree.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, List, Mapping, Optional, Union

from . import brief as _brief
from .errors import NotFoundError, StoreError, ValidationError
from .model import ID_RE, Checkpoint, format_id, id_number
from .redact import redact_obj

ENV_HOME = "AI_CHECKPOINT_HOME"
CHECKPOINT_DIR = "checkpoints"
_FILE_RE = re.compile(r"^cp-(\d+)\.json$")
_NUMBERED_RE = re.compile(r"^(.*\S)\s+\((\d+)\)$")
_GIT_IDENTITY = ("-c", "user.name=AI Checkpoint", "-c", "user.email=ai-checkpoint@localhost",
                 "-c", "commit.gpgsign=false")
# Never depend on the user's line-ending config (Windows installs default to autocrlf=true).
_GIT_CRLF = ("-c", "core.autocrlf=false", "-c", "core.safecrlf=false")
_LOCK_BYTES = 1  # fixed byte range locked at offset 0 on Windows
_LOCK_TIMEOUT_S = 60.0
_LOCK_RETRY_SLEEP_S = 0.05  # pause between msvcrt lock retries (avoid busy-wait)


def default_root() -> Path:
    """``$AI_CHECKPOINT_HOME`` if set and non-empty, else ``~/.ai-checkpoint``."""
    env = os.environ.get(ENV_HOME)
    if env:
        return Path(env).expanduser()
    return Path.home() / ".ai-checkpoint"


@dataclass
class SaveResult:
    checkpoint_id: str
    commit: str
    checkpoint: Checkpoint
    renamed: bool = False
    requested_name: Optional[str] = None
    original_id: Optional[str] = None
    clash_id: Optional[str] = None  # id already holding the requested name

    def to_dict(self) -> dict:
        name = self.checkpoint.checkpoint_name
        requested = self.requested_name if self.requested_name is not None else name
        if self.renamed:
            message = (f"A checkpoint named {requested!r} already exists in this chat"
                       f" ({self.clash_id or self.original_id}); saved as {name!r} instead.")
        else:
            message = f"Saved as {name!r}."
        return {"checkpoint_id": self.checkpoint_id, "commit": self.commit,
                "checkpoint_name": name, "renamed": self.renamed,
                "requested_name": requested,
                "original_id": self.original_id if self.renamed else None,
                "message": message}


@dataclass
class ListEntry:
    checkpoint_id: str
    chat_name: str
    checkpoint_name: str
    created_at: str
    client: str
    resumed_from: Optional[str]
    brief_tokens: int

    def to_dict(self) -> dict:
        return {
            "id": self.checkpoint_id,
            "chat_name": self.chat_name,
            "checkpoint_name": self.checkpoint_name,
            "created_at": self.created_at,
            "client": self.client,
            "resumed_from": self.resumed_from,
            "brief_tokens": self.brief_tokens,
        }


@dataclass
class Listing:
    """Checkpoints newest first; ``chats`` groups them by chat (newest chat first)."""

    checkpoints: List[ListEntry] = field(default_factory=list)

    @property
    def chats(self) -> "dict[str, List[ListEntry]]":
        groups: "dict[str, List[ListEntry]]" = {}
        for e in self.checkpoints:  # already newest first -> insertion order = newest chat first
            groups.setdefault(e.chat_name, []).append(e)
        return groups

    def __len__(self) -> int:
        return len(self.checkpoints)

    def to_dict(self) -> dict:
        return {
            "checkpoints": [e.to_dict() for e in self.checkpoints],
            "chats": [
                {"chat_name": name, "checkpoints": [e.to_dict() for e in entries]}
                for name, entries in self.chats.items()
            ],
        }


def _ref_matchers(ref: str) -> List[Callable[[Checkpoint], bool]]:
    """How a name ref is matched, most specific first.

    An exact ``chat/name`` wins, then an exact checkpoint name, then the same
    two comparisons ignoring case. Within the hits, the caller still picks the
    earliest id in the newest matching chat.
    """
    folded = ref.casefold()
    matchers: List[Callable[[Checkpoint], bool]] = []
    if "/" in ref:
        chat, name = (part.strip() for part in ref.split("/", 1))
        matchers.append(lambda c, chat=chat, name=name: c.chat_name == chat and c.checkpoint_name == name)
    matchers.append(lambda c, ref=ref: c.checkpoint_name == ref)
    if "/" in ref:
        matchers.append(lambda c, folded=folded: f"{c.chat_name}/{c.checkpoint_name}".casefold() == folded)
    matchers.append(lambda c, folded=folded: c.checkpoint_name.casefold() == folded)
    return matchers


class GitStore:
    """Save / get / resolve / list checkpoints under ``root`` (a git repo)."""

    def __init__(self, root: Union[str, os.PathLike, None] = None,
                 clock: Optional[Callable[[], datetime]] = None):
        self.root = Path(root).expanduser() if root else default_root()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # ----------------------------------------------------------- paths
    @property
    def checkpoint_dir(self) -> Path:
        return self.root / CHECKPOINT_DIR

    def path_for(self, checkpoint_id: str) -> Path:
        return self.checkpoint_dir / f"{checkpoint_id}.json"

    # ------------------------------------------------------------- git
    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items()
               if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
        try:
            proc = subprocess.run(
                ["git", *_GIT_CRLF, "-C", str(self.root), *args],
                capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
            )
        except FileNotFoundError as e:
            raise StoreError("the 'git' executable was not found on PATH") from e
        if check and proc.returncode != 0:
            raise StoreError(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
        return proc

    def _ensure_repo(self) -> None:
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        if not (self.root / ".git").exists():
            self._git("init", "-q")
            self._git("config", "--local", "core.autocrlf", "false", check=False)
            self._git("symbolic-ref", "HEAD", "refs/heads/main", check=False)

    @contextlib.contextmanager
    def _lock(self) -> Iterator[None]:
        """Serialise concurrent saves (best effort).

        Uses ``fcntl.flock`` where available, ``msvcrt.locking`` on Windows, and
        is a no-op only when neither module exists.
        """
        try:
            import fcntl
        except ImportError:
            fcntl = None  # type: ignore[assignment]
        msvcrt = None
        if fcntl is None:
            try:
                import msvcrt  # type: ignore[no-redef]
            except ImportError:
                msvcrt = None
        if fcntl is None and msvcrt is None:
            yield
            return
        with open(self.root / ".git" / "ai-checkpoint.lock", "a") as fh:
            if fcntl is not None:
                fcntl.flock(fh, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(fh, fcntl.LOCK_UN)
                return
            # Windows: lock a fixed byte range at offset 0 (not the append position).
            deadline = time.monotonic() + _LOCK_TIMEOUT_S
            while True:
                fh.seek(0)
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, _LOCK_BYTES)
                    break
                except OSError:  # LK_LOCK gives up after ~10 s; keep waiting
                    if time.monotonic() >= deadline:
                        raise StoreError("timed out waiting for the checkpoint store lock") from None
                    time.sleep(_LOCK_RETRY_SLEEP_S)
            try:
                yield
            finally:
                fh.seek(0)
                with contextlib.suppress(OSError):
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, _LOCK_BYTES)

    # ------------------------------------------------------------- ids
    def _committed_numbers(self) -> List[int]:
        if not (self.root / ".git").exists():
            return []
        proc = self._git("log", "--name-only", "--format=", "--", CHECKPOINT_DIR, check=False)
        if proc.returncode != 0:  # e.g. no commits yet
            return []
        nums = []
        for line in proc.stdout.splitlines():
            m = _FILE_RE.match(line.strip().rsplit("/", 1)[-1])
            if m:
                nums.append(int(m.group(1)))
        return nums

    def _checkpoint_files(self) -> List[tuple]:
        """``(id number, path)`` for every ``cp-NNN.json``, lowest id first."""
        if not self.checkpoint_dir.is_dir():
            return []
        found = []
        for path in self.checkpoint_dir.iterdir():
            match = _FILE_RE.match(path.name)
            if match:
                found.append((int(match.group(1)), path))
        found.sort(key=lambda item: item[0])
        return found

    def _file_numbers(self) -> List[int]:
        return [number for number, _path in self._checkpoint_files()]

    def _next_id(self) -> str:
        return format_id(max(self._file_numbers() + self._committed_numbers() + [0]) + 1)

    # ------------------------------------------------------------ save
    def save(self, data: Union[Mapping[str, Any], Checkpoint]) -> SaveResult:
        """Validate, redact, write ``checkpoints/cp-NNN.json`` and commit it.

        Raises ValidationError (nothing written) for bad input or an unknown
        ``resumed_from``; StoreError if git fails (the new file is removed).
        """
        if isinstance(data, Checkpoint):
            raw = data.to_dict()
        else:
            try:
                raw = dict(data)
            except (TypeError, ValueError):
                raise ValidationError(
                    "checkpoint", f"must be an object (got {type(data).__name__})") from None
        resumed_raw = raw.get("resumed_from")
        # Redact first so secrets can never reach disk, the commit message or validation errors.
        clean = {k: (v if k == "resumed_from" else redact_obj(v)) for k, v in raw.items()}
        cp = Checkpoint.from_dict(clean)
        if cp.resumed_from is not None:
            try:
                cp.resumed_from = self.resolve(resumed_raw if isinstance(resumed_raw, str) else cp.resumed_from)
            except NotFoundError:
                raise ValidationError(
                    "resumed_from", f"no checkpoint matches {cp.resumed_from!r}") from None

        self._ensure_repo()
        with self._lock():
            requested = cp.checkpoint_name
            renamed, original_id, clash_id = self._unique_name(cp)
            cp.checkpoint_id = self._next_id()
            cp.created_at = self._clock().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            path = self.path_for(cp.checkpoint_id)
            payload = json.dumps(cp.to_dict(), indent=2, ensure_ascii=False) + "\n"
            rel = f"{CHECKPOINT_DIR}/{cp.checkpoint_id}.json"
            try:
                with open(path, "x", encoding="utf-8", newline="\n") as fh:
                    fh.write(payload)
                self._git("add", "--", rel)
                self._git(*_GIT_IDENTITY, "commit", "-q", "--no-verify", "-m",
                          f"checkpoint: {cp.checkpoint_id} {cp.chat_name}/{cp.checkpoint_name}",
                          "--", rel)
            except BaseException:
                with contextlib.suppress(OSError):
                    path.unlink()
                self._git("reset", "-q", "--", rel, check=False)
                raise
            commit = self._git("rev-parse", "HEAD").stdout.strip()
        return SaveResult(cp.checkpoint_id, commit, cp, renamed, requested, original_id, clash_id)

    def _unique_name(self, cp: Checkpoint):
        """Finder-style renumbering within the chat (case-insensitive).

        Sets ``cp.checkpoint_name`` to a free name; returns (renamed, original_id, clash_id).
        """
        chat = cp.chat_name.strip().casefold()
        same = sorted((c for c in self._all() if c.chat_name.strip().casefold() == chat),
                      key=lambda c: id_number(c.checkpoint_id))
        taken = {c.checkpoint_name.strip().casefold() for c in same}
        name = cp.checkpoint_name
        if name.strip().casefold() not in taken:
            return False, None, None
        m = _NUMBERED_RE.match(name.strip())
        base = m.group(1) if m else name.strip()
        n = 1
        while f"{base} ({n})".casefold() in taken:
            n += 1
        clash = next(c.checkpoint_id for c in same
                     if c.checkpoint_name.strip().casefold() == name.strip().casefold())
        original = next((c.checkpoint_id for c in same
                         if c.checkpoint_name.strip().casefold() == base.casefold()), clash)
        cp.checkpoint_name = f"{base} ({n})"
        return True, original, clash

    # ------------------------------------------------------------ read
    def _load(self, path: Path) -> Optional[Checkpoint]:
        try:
            return Checkpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None  # unreadable / corrupt file: skip rather than break listing

    def _all(self) -> List[Checkpoint]:
        """All stored checkpoints, newest (highest id) first."""
        loaded = []
        for _number, path in reversed(self._checkpoint_files()):
            cp = self._load(path)
            if cp is not None:
                loaded.append(cp)
        return loaded

    def resolve(self, ref: str) -> str:
        """Resolve a ref to a checkpoint id.

        ``ref`` is an id (``cp-007``), a ``checkpoint_name`` or
        ``chat_name/checkpoint_name``. Names resolve to the earliest match within
        a chat; across chats the chat of the newest match wins. Raises NotFoundError naming the ref.
        """
        if not isinstance(ref, str) or not ref.strip():
            raise NotFoundError(str(ref), f"checkpoint not found: empty ref {ref!r}")
        ref_s = ref.strip()
        m = ID_RE.match(ref_s)
        if m:
            cid = format_id(int(m.group(1)))
            p = self.path_for(cid)
            if p.is_file() and self._load(p) is not None:
                return cid
            raise NotFoundError(ref)
        cps = self._all()  # newest first
        for match in _ref_matchers(ref_s):
            hits = [c for c in cps if match(c)]  # newest first
            if hits:
                # Newest match picks the chat; within that chat the earliest match wins.
                chat = hits[0].chat_name.strip().casefold()
                return min((c for c in hits if c.chat_name.strip().casefold() == chat),
                           key=lambda c: id_number(c.checkpoint_id)).checkpoint_id
        raise NotFoundError(ref)

    def get(self, ref: str) -> Checkpoint:
        """Return the stored checkpoint for ``ref`` (see ``resolve``)."""
        cid = self.resolve(ref)
        cp = self._load(self.path_for(cid))
        if cp is None:  # pragma: no cover (raced with a delete)
            raise NotFoundError(ref)
        return cp

    def list(self, chat_name: Optional[str] = None) -> Listing:
        """Checkpoints newest first, optionally only those of ``chat_name``.

        An empty or not-yet-created store gives an empty Listing.
        """
        entries = []
        for cp in self._all():
            if chat_name is not None and cp.chat_name != chat_name:
                continue
            tokens = _brief.estimate_tokens(_brief.render_brief(cp))
            entries.append(ListEntry(cp.checkpoint_id, cp.chat_name, cp.checkpoint_name,
                                     cp.created_at, cp.client, cp.resumed_from, tokens))
        return Listing(entries)
