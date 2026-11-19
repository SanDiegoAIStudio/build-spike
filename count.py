"""Counting what an automation produced, by kind.

Reads rows from a JSON list or from JSON Lines and counts them by the value at
a key. The point is to see how much of the output is work for a person to do.
"""
import json
from pathlib import Path
from typing import Dict, Iterable, List

MISSING = "(missing)"


def load_rows(path) -> List[dict]:
    """Read rows from a file.

    When the first character that is not white space is `[` the file is one
    JSON list of objects. Otherwise it is JSON Lines: one object per line, with
    blank lines skipped. Anything that is not an object raises ValueError that
    names the line or the item.
    """
    text = Path(path).read_text(encoding="utf-8-sig")
    if text.lstrip().startswith("["):
        try:
            items = json.loads(text)
        except ValueError as error:
            raise ValueError("not valid JSON: %s" % error)
        for number, item in enumerate(items, 1):
            if not isinstance(item, dict):
                raise ValueError("item %d is not a JSON object" % number)
        return items
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise ValueError("line %d is not valid JSON" % number)
        if not isinstance(row, dict):
            raise ValueError("line %d is not a JSON object" % number)
        rows.append(row)
    return rows


def _value_at(row: dict, key: str):
    current = row
    for part in key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def count_kinds(rows: Iterable[dict], key: str) -> Dict[str, int]:
    """Count rows by the value at `key`; a dotted key reaches into nested objects.

    A row without the key, or with null there, counts under "(missing)". Text
    values count as they are and other values by their JSON text.
    """
    counts = {}  # type: Dict[str, int]
    for row in rows:
        value = _value_at(row, key)
        if value is None:
            kind = MISSING
        elif isinstance(value, str):
            kind = value
        else:
            kind = json.dumps(value)
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def todo_share(counts: Dict[str, int], todo_kinds: Iterable[str]) -> float:
    """The share of all rows whose kind is in `todo_kinds`; 0.0 for no rows."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return sum(counts.get(kind, 0) for kind in set(todo_kinds)) / total
