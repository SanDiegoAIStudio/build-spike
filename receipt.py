"""Starting a spike folder and closing it under the receipt-and-check rule.

A build counts only when it leaves a filled-in receipt and a check script that
exits 0. This module creates the folder with a receipt template and a check
stub, and decides whether a finished folder may be recorded as built. It never
runs the check script: the caller runs it and passes the exit code in.
"""
import datetime
import re
import time
from pathlib import Path
from typing import Optional, Tuple

import index
from screen import unsafe_shell

SECTIONS = ("What now exists", "How to run it", "What it proved", "What it did not do", "Next step")
STUB_MARK = "SPIKE-STUB"

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
_FENCE = re.compile(r"^[ \t]*(```|~~~)")


class CapReached(Exception):
    """Raised when the number of spikes started in one day has reached the limit."""


def slugify(title: str) -> str:
    """Lowercase, runs of other characters become one hyphen, at most 40 characters."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-") or "idea"


def _folder_numbers(root: Path, today: str) -> list:
    pattern = re.compile(r"^%s-(\d{2,})-" % re.escape(today))
    numbers = []
    if root.is_dir():
        for child in root.iterdir():
            match = pattern.match(child.name)
            if match and child.is_dir():
                numbers.append(int(match.group(1)))
    return numbers


def new_spike(root, title: str, today: Optional[str] = None, max_per_day: int = 2) -> Path:
    """Create `root/{today}-{NN}-{slug}` with a receipt template and a check stub.

    The cap exists because a build is cheap and the attention of whoever reads
    the results is not. With `max_per_day` above 0, starting another spike on a
    day that already has that many raises CapReached. A folder that exists is
    never reused: when a name is taken the next number is tried.
    """
    root = Path(root)
    if today is None:
        today = datetime.date.today().isoformat()
    numbers = _folder_numbers(root, today)
    if max_per_day > 0 and len(numbers) >= max_per_day:
        raise CapReached("%d spikes already started today (limit %d)" % (len(numbers), max_per_day))
    root.mkdir(parents=True, exist_ok=True)
    slug = slugify(title)
    number = max(numbers) + 1 if numbers else 1
    while True:
        folder = root / ("%s-%02d-%s" % (today, number, slug))
        try:
            folder.mkdir()
            break
        except FileExistsError:
            number += 1
    heading = " ".join(title.split())
    lines = ["# Receipt: %s" % heading, "",
             "Every section below must be filled in before this spike can be closed.", ""]
    for name in SECTIONS:
        lines += ["## %s" % name, "", ""]
    (folder / "RECEIPT.md").write_text("\n".join(lines), encoding="utf-8")
    (folder / "verify.sh").write_text(
        "#!/bin/sh\n"
        "# %s: replace this file with a check that exits 0 only when the spike works.\n"
        "echo \"verify.sh is still the stub\" >&2\n"
        "exit 1\n" % STUB_MARK,
        encoding="utf-8")
    return folder


def receipt_problem(text: str) -> Optional[str]:
    """Return None when all five sections have content, else the first problem found.

    A section is a level 2 heading, matched ignoring case and surrounding
    spaces, followed by at least one non-blank line before the next heading of
    any level or the end of the text. Lines inside a fenced code block are
    content, never headings.
    """
    found = {}
    current = None
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            if current is not None:
                found[current] = True
            continue
        heading = None if in_fence else _HEADING.match(line)
        if heading:
            current = None
            if len(heading.group(1)) == 2:
                name = heading.group(2).strip().lower()
                for section in SECTIONS:
                    if section.lower() == name and section not in found:
                        found[section] = False
                        current = section
                        break
            continue
        if current is not None and line.strip():
            found[current] = True
    for section in SECTIONS:
        if section not in found:
            return "receipt is missing the section: %s" % section
        if not found[section]:
            return "receipt has an empty section: %s" % section
    return None


def _idea_from(receipt_text: Optional[str], fallback: str) -> str:
    if receipt_text:
        first = receipt_text.splitlines()[0] if receipt_text.splitlines() else ""
        prefix = "# Receipt:"
        if first.startswith(prefix):
            idea = first[len(prefix):].strip()[:120]
            if idea:
                return idea
    return fallback


def close_spike(spike_dir, verify_exit: int, index_path, now: Optional[float] = None) -> Tuple[bool, str]:
    """Decide whether a spike counts, record the answer, and return (ok, reason).

    Checks run in order and stop at the first failure: a receipt exists, all
    five sections are filled in, a check script exists, it is not the stub, it
    passes the screen, and the exit code the caller got from running it is 0.
    Pass or fail, one row goes into the record for this folder.
    """
    folder = Path(spike_dir)
    if not folder.is_dir():
        raise FileNotFoundError("not a folder: %s" % folder)
    if now is None:
        now = time.time()

    receipt_file = folder / "RECEIPT.md"
    receipt_text = receipt_file.read_text(encoding="utf-8", errors="replace") if receipt_file.is_file() else None
    verify_file = folder / "verify.sh"
    verify_text = verify_file.read_text(encoding="utf-8", errors="replace") if verify_file.is_file() else ""

    if receipt_text is None:
        ok, reason = False, "no receipt"
    elif receipt_problem(receipt_text):
        ok, reason = False, receipt_problem(receipt_text)
    elif not verify_text.strip():
        ok, reason = False, "no check script"
    elif STUB_MARK in verify_text:
        ok, reason = False, "verify.sh is still the stub"
    elif unsafe_shell(verify_text):
        ok, reason = False, "verify.sh failed the screen: %s" % unsafe_shell(verify_text)
    elif type(verify_exit) is not int or verify_exit != 0:
        ok, reason = False, "check failed (exit %s)" % (verify_exit,)
    else:
        ok, reason = True, "receipt complete, check passed"

    index.record(index_path, {
        "idea": _idea_from(receipt_text, folder.name),
        "dir": str(folder),
        "date": datetime.datetime.fromtimestamp(now).date().isoformat(),
        "built_at": now,
        "verified": ok,
        "verify_note": reason,
    })
    return ok, reason
