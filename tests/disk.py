"""Helpers for tests that look at what a save wrote to disk (bundle layout, DESIGN-v2)."""
import shutil
from pathlib import Path


def cp_path(store, checkpoint_id):
    """Bundle folder (or old flat file) of a stored checkpoint."""
    return store._path_of(checkpoint_id)


def tree_bytes(path):
    """All bytes under a file or folder, in path order, with paths mixed in."""
    path = Path(path)
    if path.is_file():
        return path.read_bytes()
    out = b""
    for p in sorted(path.rglob("*")):
        if p.is_file():
            out += str(p.relative_to(path)).encode() + b"\0" + p.read_bytes() + b"\0"
    return out


def disk_text(store, checkpoint_id):
    """Concatenated text of every file of one checkpoint."""
    return tree_bytes(cp_path(store, checkpoint_id)).decode("utf-8", errors="replace")


def remove_cp(store, checkpoint_id):
    p = cp_path(store, checkpoint_id)
    shutil.rmtree(p) if p.is_dir() else p.unlink()
