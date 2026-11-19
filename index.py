"""The record of every build and what became of it.

Without a record of what was built and what happened afterwards, every
threshold in a build rule stays a guess. This module keeps one JSON list of
rows, one row per spike folder, and reads it back with a fate for each row.
It uses a file lock, so it works on POSIX systems only.
"""
import fcntl
import json
import os
import sys
import time
from pathlib import Path
from typing import List


def atomic_write(path, text: str) -> None:
    """Write `text` to `path` through a temporary file and a rename.

    A crash in the middle of a write leaves the old file intact. The temporary
    name is unique to the process and the call, so two writers never share one.
    When either step fails the temporary file is removed and the error is raised.
    The file is synced before the rename.
    """
    path = Path(path)
    tmp = path.with_name(".%s.%d.%d.tmp" % (path.name, os.getpid(), time.time_ns()))
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
        folder = None
        try:
            folder = os.open(path.parent, os.O_RDONLY)
            os.fsync(folder)
        except OSError:
            pass
        finally:
            if folder is not None:
                try:
                    os.close(folder)
                except OSError:
                    pass
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _free_aside_name(index_path: Path) -> Path:
    stamp = int(time.time())
    candidate = index_path.with_name("%s.corrupt-%d" % (index_path.name, stamp))
    n = 1
    while candidate.exists():
        n += 1
        candidate = index_path.with_name("%s.corrupt-%d-%d" % (index_path.name, stamp, n))
    return candidate


def _load_for_update(index_path: Path) -> list:
    """Read the list under the lock; a damaged file is renamed aside, never overwritten."""
    if not index_path.exists():
        return []
    try:
        rows = json.loads(index_path.read_text(encoding="utf-8"))
    except ValueError:
        rows = None
    if isinstance(rows, list):
        return rows
    aside = _free_aside_name(index_path)
    index_path.rename(aside)
    print("warning: %s could not be read as a list; kept as %s and started a new one"
          % (index_path.name, aside.name), file=sys.stderr)
    return []


def _same_dir_key(base: Path, value) -> Path:
    return (base / value).resolve()


def record(index_path, entry: dict) -> None:
    """Add one row, or replace the row for the same folder.

    The read-modify-write runs under an exclusive lock on `{index_path}.lock`.
    `dir` is stored relative to the folder holding the index when the spike
    folder is inside it, and as an absolute path otherwise. A row without a
    `dir` is always appended.
    """
    if not isinstance(entry, dict):
        raise TypeError("entry must be a dict")
    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    base = index_path.parent.resolve()
    entry = dict(entry)
    new_key = None
    if isinstance(entry.get("dir"), (str, Path)) and str(entry["dir"]).strip():
        full = Path(entry["dir"]).resolve()
        try:
            entry["dir"] = str(full.relative_to(base))
        except ValueError:
            entry["dir"] = str(full)
        new_key = _same_dir_key(base, entry["dir"])

    lock_path = index_path.with_name(index_path.name + ".lock")
    with open(lock_path, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            rows = _load_for_update(index_path)
            slot = None
            if new_key is not None:
                for i, row in enumerate(rows):
                    if (isinstance(row, dict) and isinstance(row.get("dir"), str)
                            and row["dir"].strip() and _same_dir_key(base, row["dir"]) == new_key):
                        slot = i
                        break
            if slot is None:
                rows.append(entry)
            else:
                rows[slot] = entry
            atomic_write(index_path, json.dumps(rows, indent=2) + "\n")
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _number(value) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _newest_mtime(path: Path) -> float:
    candidates = [path] if path.is_file() else path.rglob("*")
    newest = 0.0
    for item in candidates:
        try:
            if item.is_file():
                newest = max(newest, item.stat().st_mtime)
        except OSError:
            continue
    return newest


def fates(index_path, grace_seconds: int = 300) -> List[dict]:
    """Return a copy of every row with a `fate` added. Read only.

    no-dir: the row has no folder. deleted: the folder is gone. touched: some
    file inside was modified later than `built_at` plus the grace period.
    untouched: nothing changed after the build. A damaged or missing record
    gives an empty list.
    """
    index_path = Path(index_path)
    base = index_path.parent
    try:
        rows = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        copy = dict(row)
        folder = row.get("dir")
        if not isinstance(folder, str) or not folder.strip():
            copy["fate"] = "no-dir"
        else:
            path = base / folder
            if not path.exists():
                copy["fate"] = "deleted"
            elif _newest_mtime(path) > _number(row.get("built_at")) + grace_seconds:
                copy["fate"] = "touched"
            else:
                copy["fate"] = "untouched"
        out.append(copy)
    return out


def summary(rows: List[dict]) -> str:
    """One line: how many spikes, how many verified, and a count per fate."""
    n = len(rows)
    verified = sum(1 for row in rows if row.get("verified") is True)
    percent = (100.0 * verified / n) if n else 0.0
    counts = {}
    for row in rows:
        counts[row.get("fate")] = counts.get(row.get("fate"), 0) + 1
    line = "%d spike(s) recorded, verified %d (%.0f%%)" % (n, verified, percent)
    for fate in sorted(counts, key=str):
        line += ", %s %d" % (fate, counts[fate])
    return line
