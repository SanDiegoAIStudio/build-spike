#!/usr/bin/env bash
# An offline walk through every command, in a temporary folder that is removed at the end.
# Nothing is written inside the repository and no check script runs except the sample's own.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
export PYTHONDONTWRITEBYTECODE=1
TMP="$(mktemp -d)" || exit 1
trap 'rm -rf "$TMP"' EXIT
cd "$TMP" || exit 1
ROOT="spikes"

# spike ARGS...: run the kit's command line.
spike() {
  python3 "$REPO/spike.py" "$@"
}

# expect CODE COMMAND...: run the command, show its output, stop when the exit code differs.
expect() {
  want="$1"; shift
  "$@"
  got=$?
  if [ "$got" -ne "$want" ]; then
    echo "demo: expected exit $want, got $got, from: $*" >&2
    exit 1
  fi
}

echo "== count: how much of the output is a to-do for a person (expect exit 1)"
expect 1 spike count "$HERE/actions.jsonl" --key kind --todo backlog_entry

echo
echo "== count: the same rows by verdict (expect exit 0)"
expect 0 spike count "$HERE/actions.jsonl" --key verdict

echo
echo "== gate: a cheap, low-stakes plan with a harmless step (expect BUILD, exit 0)"
expect 0 spike gate "$HERE/plan-build.json"

echo
echo "== gate: the planned step spends money (expect ASK, exit 1)"
expect 1 spike gate "$HERE/plan-spends.json"

echo
echo "== gate: the first version is not cheap (expect ASK, exit 1)"
expect 1 spike gate "$HERE/plan-costly.json"

echo
echo "== screen: an ordinary check script (expect OK, exit 0)"
expect 0 spike screen "$HERE/verify-good.sh"

echo
echo "== screen: a script that pipes a download into a shell (expect UNSAFE, exit 1)"
expect 1 spike screen "$HERE/verify-bad.sh"

echo
echo "== new: start a spike folder"
DIR="$(spike new "Turn a text table into JSON" --root "$ROOT")" || { echo "demo: new failed" >&2; exit 1; }
echo "$DIR"

echo
echo "== close: the receipt is empty and the check is the stub (expect FAILED, exit 1)"
expect 1 spike close "$DIR" --verify-exit 1 --root "$ROOT"

echo
echo "== fill the folder with the sample spike, screen its check, then run it"
for name in RECEIPT.md verify.sh table_to_json.py sample.txt; do
  cp "$HERE/sample-spike/$name" "$DIR/$name"
done
expect 0 spike screen "$DIR/verify.sh"
(cd "$DIR" && /bin/sh verify.sh)
CHECK=$?
echo "verify.sh exit code: $CHECK"

echo
echo "== close: pass the exit code (expect BUILT, exit 0)"
expect 0 spike close "$DIR" --verify-exit "$CHECK" --root "$ROOT"

echo
echo "== fates: what became of each build"
expect 0 spike fates --root "$ROOT"

echo
echo "demo finished"
