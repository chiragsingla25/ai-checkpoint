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
_GIT_IDENTITY = ("-c", "user.name=AI Checkpoint", "-c", "user.email=ai-checkpoint@localhost",
                 "-c", "commit.gpgsign=false")


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

    def to_dict(self) -> dict:
        return {"checkpoint_id": self.checkpoint_id, "commit": self.commit}


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
                ["git", "-C", str(self.root), *args],
                capture_output=True, text=True, encoding="utf-8", env=env,
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
            self._git("symbolic-ref", "HEAD", "refs/heads/main", check=False)

    @contextlib.contextmanager
    def _lock(self) -> Iterator[None]:
        """Serialise concurrent saves (best effort; no-op where fcntl is unavailable)."""
        try:
            import fcntl
        except ImportError:  # pragma: no cover (Windows)
            yield
            return
        with open(self.root / ".git" / "ai-checkpoint.lock", "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

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

    def _file_numbers(self) -> List[int]:
        if not self.checkpoint_dir.is_dir():
            return []
        return [int(m.group(1)) for p in self.checkpoint_dir.iterdir()
                if (m := _FILE_RE.match(p.name))]

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
        return SaveResult(cp.checkpoint_id, commit, cp)

    # ------------------------------------------------------------ read
    def _load(self, path: Path) -> Optional[Checkpoint]:
        try:
            return Checkpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None  # unreadable / corrupt file: skip rather than break listing

    def _all(self) -> List[Checkpoint]:
        """All stored checkpoints, newest (highest id) first."""
        if not self.checkpoint_dir.is_dir():
            return []
        files = sorted(
            ((int(m.group(1)), p) for p in self.checkpoint_dir.iterdir()
             if (m := _FILE_RE.match(p.name))),
            key=lambda t: t[0], reverse=True,
        )
        return [cp for _, p in files if (cp := self._load(p)) is not None]

    def resolve(self, ref: str) -> str:
        """Resolve a ref to a checkpoint id.

        ``ref`` is an id (``cp-007``), a ``checkpoint_name`` or
        ``chat_name/checkpoint_name``. Names resolve to the newest match, also
        across chats. Raises NotFoundError naming the ref.
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
        candidates: List[Callable[[Checkpoint], bool]] = []
        if "/" in ref_s:
            chat, name = ref_s.split("/", 1)
            candidates.append(lambda c: c.chat_name == chat.strip() and c.checkpoint_name == name.strip())
        candidates.append(lambda c: c.checkpoint_name == ref_s)
        folded = ref_s.casefold()
        if "/" in ref_s:
            candidates.append(lambda c: f"{c.chat_name}/{c.checkpoint_name}".casefold() == folded)
        candidates.append(lambda c: c.checkpoint_name.casefold() == folded)
        for match in candidates:
            for c in cps:
                if match(c):
                    return c.checkpoint_id
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
