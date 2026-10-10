"""Git-backed checkpoint store. Stdlib only (shells out to the ``git`` binary).

Layout::

    <root>/.git
    <root>/checkpoints/cp-001.json
    <root>/checkpoints/cp-002.json            (old flat files, read in place)
    <root>/chats/<chat>/chat.json, events.jsonl
    <root>/chats/<chat>/checkpoints/cp-003/   (bundles, see docs/DESIGN-v2.md)

Each save writes one new bundle folder and makes exactly one commit
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
from . import bundle as _bundle
from . import structured as _structured
from .errors import NotFoundError, RequestError, StoreError, ValidationError
from .model import ID_RE, WORKSPACE_CATEGORIES, Checkpoint, format_id, id_number
from .redact import redact_obj

ENV_HOME = "AI_CHECKPOINT_HOME"
CHECKPOINT_DIR = "checkpoints"
CHATS_DIR = "chats"
_FILE_RE = re.compile(r"^cp-(\d+)\.json$")
_BUNDLE_RE = re.compile(r"^cp-(\d+)$")
_BUNDLE_PATH_RE = re.compile(r"^chats/[^/]+/checkpoints/cp-(\d+)/")
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
    next_action: Optional[dict] = None  # {"task_id", "text"} or None
    echo: str = ""  # "Next action saved: <task text>. Correct?"

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
                "next_action": self.next_action,
                "message": f"{message} {self.echo}" if self.echo else message}


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
        """Path of an old flat checkpoint file (bundles: see ``_bundle_dirs``)."""
        return self.checkpoint_dir / f"{checkpoint_id}.json"

    @property
    def chats_dir(self) -> Path:
        return self.root / CHATS_DIR

    def _bundle_dirs(self) -> "List[tuple]":
        """(number, folder) for every bundle folder on disk."""
        out = []
        if self.chats_dir.is_dir():
            for chat in self.chats_dir.iterdir():
                cps = chat / CHECKPOINT_DIR
                if cps.is_dir():
                    out.extend((int(m.group(1)), p) for p in cps.iterdir()
                               if p.is_dir() and (m := _BUNDLE_RE.match(p.name)))
        return out

    def _chat_folder_for(self, chat_name: str) -> "tuple":
        """(folder path, exists) for a chat: found by chat.json key, else a free name."""
        key = _bundle.chat_key(chat_name)
        base = _bundle.chat_folder(chat_name)
        n = 1
        while True:
            folder = self.chats_dir / (base if n == 1 else f"{base}-{n}")
            meta = folder / "chat.json"
            if not folder.exists():
                return folder, False
            try:
                if json.loads(meta.read_text(encoding="utf-8")).get("key") == key:
                    return folder, True
            except (OSError, ValueError, AttributeError):
                pass
            n += 1

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
        proc = self._git("log", "--name-only", "--format=", "--", CHECKPOINT_DIR, CHATS_DIR,
                         check=False)
        if proc.returncode != 0:  # e.g. no commits yet
            return []
        nums = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            m = _BUNDLE_PATH_RE.match(line) or _FILE_RE.match(line.rsplit("/", 1)[-1])
            if m:
                nums.append(int(m.group(1)))
        return nums

    def _file_numbers(self) -> List[int]:
        flat = []
        if self.checkpoint_dir.is_dir():
            flat = [int(m.group(1)) for p in self.checkpoint_dir.iterdir()
                    if (m := _FILE_RE.match(p.name))]
        return flat + [n for n, _ in self._bundle_dirs()]

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
        plan_updates = clean.get("plan_updates")
        if plan_updates is not None:
            if clean.get("tasks") is not None:
                raise RequestError("Give either tasks (a new plan) or plan_updates (changes to the "
                                   "parent's plan), not both.")
            if not clean.get("resumed_from"):
                raise RequestError("plan_updates needs resumed_from: pass the id of the checkpoint "
                                   "this chat was resumed from.")
        cp = Checkpoint.from_dict(clean)
        if cp.resumed_from is not None:
            try:
                cp.resumed_from = self.resolve(resumed_raw if isinstance(resumed_raw, str) else cp.resumed_from)
            except NotFoundError:
                raise ValidationError(
                    "resumed_from", f"no checkpoint matches {cp.resumed_from!r}") from None

        parent = parent_v2 = None
        if cp.resumed_from is not None:
            parent = self.get(cp.resumed_from)
            parent_v2 = parent.v2 if parent.v2 is not None else _structured.from_flat(parent)
        # Only a resumed save that uses the structured fields (tasks, plan_updates, user_turns,
        # facts) carries the sections it does not supply forward and merges the ones it does
        # (DESIGN-v2 s.11). An old-fields-only resumed save behaves as before: nothing carried.
        merge = any(clean.get(k) is not None for k in ("tasks", "plan_updates", "user_turns", "facts"))
        carry = parent_v2 is not None and merge
        base = _structured.max_task_number(parent_v2.tasks) if parent_v2 is not None else 0
        cp.v2 = _structured.build(clean, cp, base, parent_v2 if carry else None)
        new_tasks = None
        if plan_updates is not None:
            cp.v2.tasks, new_tasks = _structured.apply_plan_updates(
                parent_v2.tasks, plan_updates, cp.resumed_from, base)
        if carry:
            cp.decisions = _structured.decisions_flat(cp.v2.decisions)
            cp.open_questions = [q["text"] for q in cp.v2.questions]
            self._carry_flat(cp, parent, clean)
        else:
            cp.decisions = [d for d, row in zip(cp.decisions, cp.v2.decisions)
                            if row["status"] == "active"]
        cp.next_steps = _bundle.next_steps_from_tasks(cp.v2.tasks)
        _structured.run_checks(clean, cp, cp.v2, new_tasks)

        self._ensure_repo()
        with self._lock():
            requested = cp.checkpoint_name
            renamed, original_id, clash_id = self._unique_name(cp)
            cp.checkpoint_id = self._next_id()
            cp.created_at = self._clock().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            _structured.finalize(cp.v2, cp.created_at)
            chat_dir, chat_exists = self._chat_folder_for(cp.chat_name)
            bundle_dir = chat_dir / CHECKPOINT_DIR / cp.checkpoint_id
            events_path = chat_dir / "events.jsonl"
            chat_json = chat_dir / "chat.json"
            old_events = events_path.read_bytes() if events_path.is_file() else None
            relroot = chat_dir.relative_to(self.root).as_posix()
            paths = [f"{relroot}/{CHECKPOINT_DIR}/{cp.checkpoint_id}", f"{relroot}/events.jsonl"]
            if not chat_json.is_file():
                paths.append(f"{relroot}/chat.json")
            try:
                _bundle.write_bundle(bundle_dir, cp, _brief.render_brief(cp))
                if not chat_json.is_file():
                    chat_json.write_bytes(_bundle.dumps_json(
                        {"version": _bundle.BUNDLE_VERSION, "chat_name": cp.chat_name,
                         "key": _bundle.chat_key(cp.chat_name)}))
                tasks = cp.v2.tasks
                info = _structured.next_action_info(tasks)
                nxt = info["action"]
                seq = (old_events or b"").count(b"\n") + 1
                event = _bundle.dumps_jsonl([{
                    "seq": seq, "ts": cp.created_at, "type": "checkpoint_saved",
                    "checkpoint_id": cp.checkpoint_id, "checkpoint_name": cp.checkpoint_name,
                    "resumed_from": cp.resumed_from, "client": cp.client, "tasks": len(tasks),
                    "unfinished": sum(t["status"] != "done" for t in tasks),
                    "next_action": nxt["task_id"] if nxt else None,
                    "renamed_from": requested if renamed else None}])
                with open(events_path, "ab") as fh:
                    fh.write(event)
                self._git("add", "--", *paths)
                self._git(*_GIT_IDENTITY, "commit", "-q", "--no-verify", "-m",
                          f"checkpoint: {cp.checkpoint_id} {cp.chat_name}/{cp.checkpoint_name}",
                          "--", *paths)
            except BaseException:
                self._rollback(chat_dir, bundle_dir, events_path, old_events, chat_exists, paths)
                raise
            commit = self._git("rev-parse", "HEAD").stdout.strip()
        return SaveResult(cp.checkpoint_id, commit, cp, renamed, requested, original_id, clash_id,
                          nxt, _structured.echo_text(info))

    def _rollback(self, chat_dir, bundle_dir, events_path, old_events, chat_existed, paths):
        """Undo a failed save: restore events.jsonl, remove what this save created."""
        import shutil
        shutil.rmtree(bundle_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            if old_events is None:
                events_path.unlink()
            else:
                events_path.write_bytes(old_events)
        if not chat_existed:
            with contextlib.suppress(OSError):
                (chat_dir / "chat.json").unlink()
            with contextlib.suppress(OSError):
                (chat_dir / CHECKPOINT_DIR).rmdir()
            with contextlib.suppress(OSError):
                chat_dir.rmdir()
        self._git("reset", "-q", "--", *paths, check=False)

    @staticmethod
    def _carry_flat(cp: Checkpoint, parent: Checkpoint, clean: Mapping) -> None:
        """Workspace (merged by category and key) and verbatim (replaced if supplied)."""
        merged = {}
        for cat, (key, _o, _l) in WORKSPACE_CATEGORIES.items():
            items = [dict(i) for i in parent.workspace.get(cat, [])]
            for new in cp.workspace.get(cat, []):
                at = next((n for n, old in enumerate(items) if old.get(key) == new.get(key)), None)
                if at is None:
                    items.append(dict(new))
                else:
                    items[at] = dict(new)
            merged[cat] = items
        cp.workspace = merged
        if clean.get("verbatim") is None:
            cp.verbatim = list(parent.verbatim)

    def _task_base(self, parent_id: Optional[str]) -> int:
        """Highest task number in the parent's plan (task ids continue from it)."""
        if not parent_id:
            return 0
        parent = self.get(parent_id)
        if parent.v2 is not None:
            return _structured.max_task_number(parent.v2.tasks)
        return len(parent.next_steps)

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
            if path.is_dir():
                return _bundle.read_bundle(path)
            return Checkpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None  # unreadable / corrupt file or bundle: skip rather than break listing

    def _path_of(self, checkpoint_id: str) -> Optional[Path]:
        """Flat file or bundle folder for an id, or None."""
        flat = self.path_for(checkpoint_id)
        if flat.is_file():
            return flat
        n = id_number(checkpoint_id)
        return next((p for num, p in self._bundle_dirs() if num == n), None)

    def _all(self) -> List[Checkpoint]:
        """All stored checkpoints, newest (highest id) first."""
        files = [(int(m.group(1)), p) for p in (self.checkpoint_dir.iterdir()
                 if self.checkpoint_dir.is_dir() else []) if (m := _FILE_RE.match(p.name))]
        files += self._bundle_dirs()
        files.sort(key=lambda t: t[0], reverse=True)
        return [cp for _, p in files if (cp := self._load(p)) is not None]

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
            p = self._path_of(cid)
            if p is not None and self._load(p) is not None:
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
        p = self._path_of(cid)
        cp = self._load(p) if p is not None else None
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
