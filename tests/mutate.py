"""Break the code on purpose and check that the tests notice.

Each mutation changes one place in one source file, in a temporary copy of the
repository, and runs the whole test suite against the copy. A mutation is
killed when the suite fails and survives when it still passes. A surviving
mutation means a test is missing or too weak.

Run it from the repository root: python3 tests/mutate.py
Exit code 0 means every mutation was killed, 1 means at least one survived or
the unmutated suite did not pass, and 2 means a mutation did not apply.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKIP = {".git", "__pycache__", "spikes"}
TIMEOUT = 180

# (name, file, [(old text, new text), ...], runs)
# `old text` must occur exactly once. `runs` is how many times the suite must
# fail for the mutation to count as killed; mutations that depend on timing
# between processes run more than once.
MUTATIONS = [
    # gate
    ("gate: threshold comparison reversed", "gate.py",
     [("if cheapness < threshold:", "if cheapness > threshold:")], 1),
    ("gate: a cheapness equal to the threshold fails", "gate.py",
     [("if cheapness < threshold:", "if cheapness <= threshold:")], 1),
    ("gate: a boolean counts as a cheapness", "gate.py",
     [("isinstance(cheapness, bool) or ", "")], 1),
    ("gate: a float counts as a cheapness", "gate.py",
     [("not isinstance(cheapness, int)", "not isinstance(cheapness, (int, float))")], 1),
    ("gate: the 0 to 100 range is not checked", "gate.py",
     [(" or not 0 <= cheapness <= 100", "")], 1),
    ("gate: high stakes pass", "gate.py",
     [('if stakes == "high":', 'if stakes == "never":')], 1),
    ("gate: a missing stakes value passes", "gate.py",
     [("if stakes not in STAKES:", "if stakes not in STAKES + (None,):")], 1),
    ("gate: stakes are compared with their capitals", "gate.py",
     [("stakes.lower() if isinstance(stakes, str)", "stakes if isinstance(stakes, str)")], 1),
    ("gate: an empty action passes", "gate.py",
     [("if not isinstance(action, str) or not action.strip():", "if not isinstance(action, str):")], 1),
    ("gate: the forbidden screen is skipped", "gate.py",
     [("if re.search(pattern, text):", "if False:")], 1),
    ("gate: the forbidden screen also reads the title", "gate.py",
     [("text = action.lower()", 'text = (str(plan.get("title", "")) + " " + action).lower()')], 1),
    ("gate: the forbidden screen is case sensitive", "gate.py",
     [("text = action.lower()", "text = action")], 1),
    ("gate: the destructive category is missing words", "gate.py",
     [("drop table|", "")], 1),
    ("gate: paying is not treated as spending", "gate.py",
     [("|paying", "")], 1),
    ("gate: sends is not treated as an outward send", "gate.py",
     [("sends?", "send")], 1),
    ("gate: deploying is not treated as production", "gate.py",
     [("|deploying", "")], 1),
    ("gate: passwords are not treated as credentials", "gate.py",
     [("passwords?", "password")], 1),
    ("gate: deletes is not treated as destructive", "gate.py",
     [("deletes?", "delete")], 1),
    ("gate: charge, refund, donate, money and fund are not spending", "gate.py",
     [("charg(?:e|es|ed|ing)|refund(?:s|ed|ing)?|donat(?:e|es|ed|ing)|money|funds?", "(?!)")], 1),
    ("gate: notify, upload, message, mail, share, invite and submit are not outward", "gate.py",
     [("notif(?:y|ies|ied|ying|ication|ications)|upload(?:s|ed|ing)?|messag(?:e|es|ed|ing)|"
       "mails?|mailed|mailing|shar(?:e|es|ed|ing)|invit(?:e|es|ed|ing)|submit(?:s|ted|ting)?|",
       "")], 1),
    ("gate: phone, dial, voicemail and a call to a person are not outward", "gate.py",
     [("phon(?:e|ed|ing)|dial(?:s|ed|ing)?|voicemails?|call(?:s|ed|ing)?"
       "\\s+(?:(?:their|your|the|our|an|my|a)\\s+)?"
       "(?:customer|client|lead|user|owner|vendor|people|someone|them)s?", "(?!)")], 1),
    ("gate: git push and push to are not production", "gate.py",
     [("git\\s+push(?!\\s+--force)|push(?:es|ed|ing)?\\s+to", "(?!)")], 1),
    ("gate: remove and overwrite are not destructive", "gate.py",
     [("|remov(?:e|es|ed|ing)|overwrit(?:e|es|ing|ten)|overwrote", "")], 1),
    # screen
    ("screen: ignore-case flag dropped", "screen.py",
     [("re.search(pattern, script, re.I)", "re.search(pattern, script)")], 1),
    ("screen: always returns None", "screen.py",
     [("if re.search(pattern, script, re.I):", "if False:")], 1),
    ("screen: the sudo pattern is missing", "screen.py",
     [('    (r"\\bsudo\\b", "sudo"),\n', "")], 1),
    ("screen: patterns tried in reverse order", "screen.py",
     [("for pattern, reason in UNSAFE:", "for pattern, reason in reversed(UNSAFE):")], 1),
    ("screen: the home folder is not covered by the rm pattern", "screen.py",
     [("(?:~|/", "(?:/")], 1),
    ("screen: rm misses the -fr form", "screen.py",
     [("-[A-Za-z]*[rR]", "-[rR]")], 1),
    ("screen: rm misses $HOME", "screen.py",
     [("|\\$HOME", "")], 1),
    ("screen: the recursive flag requirement is removed", "screen.py",
     [("\\s+(?:-[A-Za-z]*[rR][A-Za-z]*|--recursive)", "")], 1),
    ("screen: r and R are not counted as recursive", "screen.py",
     [("[rR]", "[q]")], 1),
    ("screen: --recursive is not counted as recursive", "screen.py",
     [("|--recursive", "")], 1),
    ("screen: the ${HOME} form is dropped", "screen.py",
     [("\\$\\{HOME\\}", "\\$\\{NEVER\\}")], 1),
    ("screen: pipe-to-shell misses zsh", "screen.py",
     [("|zsh", "")], 1),
    ("screen: pipe-to-shell misses a command substitution", "screen.py",
     [("-c\\s+[\\\"']\\$\\((?:curl|wget)", "-c\\s+[\\\"']\\$(?:true)")], 1),
    ("screen: os.environ matches the env pattern", "screen.py",
     [("\\.env\\b", "\\.env")], 1),
    ("screen: pipe-to-shell misses a path prefix", "screen.py",
     [("(?:\\S*/)?", "")], 1),
    ("screen: pipe-to-shell misses env", "screen.py",
     [("(?:\\benv\\b(?:\\s+(?:-\\S+|\\S*=\\S*))*\\s+)?", "")], 1),
    ("screen: pipe-to-shell misses the new interpreters", "screen.py",
     [("|(?:fish|perl|ruby|node|php|python(?:[23](?:\\.\\d+)?)?)", "")], 1),
    ("screen: pipe-to-shell misses a shell named by a path or through env", "screen.py",
     [("(?:zsh|bash|dash|ksh|sh)\\b(?=[\\s;&)<>|]|$)", ""),
      ("|(?:fish|perl|ruby|node|php|python(?:[23](?:\\.\\d+)?)?)",
       "(?:fish|perl|ruby|node|php|python(?:[23](?:\\.\\d+)?)?)")], 1),
    ("screen: pipe-to-shell misses a pipe, redirect, ) or comment after an interpreter", "screen.py",
     [(")#<>|]|&&|\\|\\||\\d+>", "]|&&|\\|\\|")], 1),
    ("screen: pipe-to-shell misses a program read from stdin", "screen.py",
     [("|\\s+(?:-|/dev/stdin)(?!\\S)", "")], 1),
    ("screen: pipe-to-shell misses eval of a download", "screen.py",
     [("|\\beval\\s+[\\\"']?\\$\\(\\s*(?:curl|wget)", "")], 1),
    ("screen: rm misses a parent directory", "screen.py",
     [("|\\.\\.(?:/|[\\\"']|\\s|$)", "")], 1),
    # receipt
    ("receipt: an unfilled receipt closes", "receipt.py",
     [("elif receipt_problem(receipt_text):", "elif False:")], 1),
    ("receipt: the stub closes", "receipt.py",
     [("elif STUB_MARK in verify_text:", "elif False:")], 1),
    ("receipt: a script that fails the screen closes", "receipt.py",
     [("elif unsafe_shell(verify_text):", "elif False:")], 1),
    ("receipt: a non-zero exit code closes as verified", "receipt.py",
     [("elif type(verify_exit) is not int or verify_exit != 0:", "elif type(verify_exit) is not int:")], 1),
    ("receipt: False and 0.0 count as an exit code of 0", "receipt.py",
     [("type(verify_exit) is not int or verify_exit != 0", "verify_exit != 0")], 1),
    ("receipt: a failed close is not recorded", "receipt.py",
     [("    index.record(index_path, {", "    if ok: index.record(index_path, {")], 1),
    ("receipt: the recorded verified flag is always true", "receipt.py",
     [('"verified": ok,', '"verified": True,')], 1),
    ("receipt: the recorded build time is zero", "receipt.py",
     [('"built_at": now,', '"built_at": 0,')], 1),
    ("receipt: the cap is ignored", "receipt.py",
     [("if max_per_day > 0 and len(numbers) >= max_per_day:", "if False:")], 1),
    ("receipt: the cap stops one spike late", "receipt.py",
     [("len(numbers) >= max_per_day", "len(numbers) > max_per_day")], 1),
    ("receipt: a cap of 0 is a cap", "receipt.py",
     [("max_per_day > 0 and ", "")], 1),
    ("receipt: the new number is the count, not the highest number plus one", "receipt.py",
     [("number = max(numbers) + 1 if numbers else 1", "number = len(numbers) + 1")], 1),
    ("receipt: an existing folder is reused", "receipt.py",
     [("folder.mkdir()", "folder.mkdir(exist_ok=True)")], 1),
    ("receipt: a file with a spike name counts as a spike", "receipt.py",
     [("if match and child.is_dir():", "if match:")], 1),
    ("receipt: lines inside a code fence can be headings", "receipt.py",
     [("heading = None if in_fence else _HEADING.match(line)", "heading = _HEADING.match(line)")], 1),
    ("receipt: a level 3 heading counts as a section", "receipt.py",
     [("if len(heading.group(1)) == 2:", "if len(heading.group(1)) >= 2:")], 1),
    ("receipt: an empty section is accepted", "receipt.py",
     [("if not found[section]:", "if False:")], 1),
    ("receipt: a deeper heading does not end a section", "receipt.py",
     [("            current = None\n            if len(heading.group(1)) == 2:",
       "            if len(heading.group(1)) == 2:")], 1),
    ("receipt: a repeated heading replaces the first", "receipt.py",
     [(" and section not in found", "")], 1),
    ("receipt: an empty idea text is used as the idea", "receipt.py",
     [("            if idea:\n", "            if True:\n")], 1),
    ("receipt: the idea is cut one character late", "receipt.py",
     [("[:120]", "[:121]")], 1),
    ("receipt: the folder name slug is cut one character late", "receipt.py",
     [('.strip("-")[:40].strip("-")', '.strip("-")[:41].strip("-")')], 1),
    ("receipt: a cut slug can end in a hyphen", "receipt.py",
     [('[:40].strip("-")', "[:40]")], 1),
    ("receipt: line breaks in a title reach the heading", "receipt.py",
     [('heading = " ".join(title.split())', "heading = title")], 1),
    # index
    ("index: record drops the lock", "index.py",
     [("fcntl.flock(lock, fcntl.LOCK_EX)", "pass")], 5),
    ("index: a damaged index is overwritten in place", "index.py",
     [("index_path.rename(aside)", "pass")], 1),
    ("index: a second record for a folder is appended", "index.py",
     [("rows[slot] = entry", "rows.append(entry)")], 1),
    ("index: a folder inside the root is stored with its full path", "index.py",
     [('entry["dir"] = str(full.relative_to(base))', 'entry["dir"] = str(full)')], 1),
    ("index: a failed write leaves its temporary file", "index.py",
     [("tmp.unlink(missing_ok=True)", "pass")], 1),
    ("index: the temporary file is not synced", "index.py",
     [("os.fsync(handle.fileno())", "pass")], 1),
    ("index: fates ignores the grace period", "index.py",
     [(" + grace_seconds", "")], 1),
    ("index: a change exactly at the end of the grace period counts", "index.py",
     [("elif _newest_mtime(path) > _number(", "elif _newest_mtime(path) >= _number(")], 1),
    ("index: fates looks only at the top level of a folder", "index.py",
     [('path.rglob("*")', 'path.glob("*")')], 1),
    ("index: a row with no folder raises", "index.py",
     [('copy["fate"] = "no-dir"', 'raise KeyError("dir")')], 1),
    ("index: any truthy verified value counts as verified", "index.py",
     [('row.get("verified") is True', 'row.get("verified")')], 1),
    # count
    ("count: rows without the key are dropped", "count.py",
     [("            kind = MISSING\n", "            continue\n")], 1),
    ("count: a dotted key is not followed into nested objects", "count.py",
     [('for part in key.split("."):', "for part in [key]:")], 1),
    ("count: a bad line is skipped", "count.py",
     [('raise ValueError("line %d is not valid JSON" % number)', "continue")], 1),
    ("count: a kind named twice counts twice", "count.py",
     [("for kind in set(todo_kinds)", "for kind in list(todo_kinds)")], 1),
    ("count: other values are counted by their Python text", "count.py",
     [("kind = json.dumps(value)", "kind = str(value)")], 1),
    # command line
    ("cli: gate exits 0 on ASK", "spike.py",
     [("return 0 if ok else 1", "return 0")], 1),
    ("cli: count exits 0 above the largest share", "spike.py",
     [("return 1 if share > args.max_share else 0", "return 0")], 1),
    ("cli: count exits 1 at the largest share", "spike.py",
     [("return 1 if share > args.max_share else 0", "return 1 if share >= args.max_share else 0")], 1),
    ("cli: screen exits 0 on UNSAFE", "spike.py",
     [('print("UNSAFE: %s" % reason)\n    return 1', 'print("UNSAFE: %s" % reason)\n    return 0')], 1),
    ("cli: close exits 0 on FAILED", "spike.py",
     [('print("FAILED: %s" % reason)\n    return 1', 'print("FAILED: %s" % reason)\n    return 0')], 1),
    ("cli: new exits 0 at the cap", "spike.py",
     [('print("CAP: %s" % error, file=sys.stderr)\n        return 1',
       'print("CAP: %s" % error, file=sys.stderr)\n        return 0')], 1),
    ("cli: bad arguments exit 1", "spike.py",
     [('print("spike: %s" % error, file=sys.stderr)\n        return 2',
       'print("spike: %s" % error, file=sys.stderr)\n        return 1')], 1),
    ("cli: close does not check that the folder exists first", "spike.py",
     [("if not folder.is_dir():", "if False:")], 1),
    ("cli: fates lists oldest first", "spike.py",
     [("reverse=True", "reverse=False")], 1),
    ("cli: the root environment variable is ignored", "spike.py",
     [('os.environ.get("SPIKE_ROOT") or "spikes"', '"spikes"')], 1),
    ("demo: the sample check is not screened", "examples/demo.sh",
     [('expect 0 spike screen "$DIR/verify.sh"', "true")], 1),
]


def copy_repository(destination):
    for name in os.listdir(ROOT):
        if name in SKIP:
            continue
        source = os.path.join(ROOT, name)
        if os.path.isdir(source):
            shutil.copytree(source, os.path.join(destination, name),
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(source, os.path.join(destination, name))


def run_suite(folder):
    """Return True when the whole suite passes in `folder`."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("SPIKE_ROOT", None)
    try:
        done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-f"],
                              cwd=folder, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def apply_mutation(folder, name, filename, edits):
    target = os.path.join(folder, filename)
    with open(target, encoding="utf-8") as handle:
        text = handle.read()
    mutated = text
    for old, new in edits:
        found = mutated.count(old)
        if found != 1:
            print("mutate: '%s' needs its old text to occur once in %s, found %d times"
                  % (name, filename, found), file=sys.stderr)
            raise SystemExit(2)
        mutated = mutated.replace(old, new)
    if mutated == text:
        print("mutate: '%s' did not change %s" % (name, filename), file=sys.stderr)
        raise SystemExit(2)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(mutated)
    if filename.endswith(".py"):
        compile(mutated, target, "exec")


def test_one(name, filename, edits, runs):
    """Return True when every one of the `runs` runs of the suite fails."""
    for _ in range(runs):
        folder = tempfile.mkdtemp(prefix="spike-mutate-")
        try:
            copy_repository(folder)
            apply_mutation(folder, name, filename, edits)
            if run_suite(folder):
                return False
        finally:
            shutil.rmtree(folder, ignore_errors=True)
    return True


def main():
    started = time.time()
    folder = tempfile.mkdtemp(prefix="spike-mutate-")
    try:
        copy_repository(folder)
        baseline = run_suite(folder)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    if not baseline:
        print("baseline: the suite fails without any mutation; fix that first")
        return 1
    print("baseline: the suite passes without any mutation")
    survived = []
    for name, filename, edits, runs in MUTATIONS:
        killed = test_one(name, filename, edits, runs)
        print("%-9s %s" % ("killed" if killed else "SURVIVED", name))
        sys.stdout.flush()
        if not killed:
            survived.append(name)
    total = len(MUTATIONS)
    print("%d mutations, %d killed, %d survived (%.0f seconds)"
          % (total, total - len(survived), len(survived), time.time() - started))
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
