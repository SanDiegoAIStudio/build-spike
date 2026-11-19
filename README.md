# build-spike

build-spike is a small kit for anyone whose automation comes up with ideas: it counts what the automation produces, decides which ideas may be built without asking, and holds each build to a receipt and a passing check, so the output is runnable things instead of to-dos. It is plain Python with no dependencies. A spike is the smallest runnable first version of an idea, built to learn whether the idea is worth more.

## The rule

1. Count what your automation produced last month, by kind. If most of it is to-dos for you, it is producing work for you to do.
2. When an idea's downside is bounded, meaning the first version is cheap, the stakes are low, and the step does not spend money, send anything, deploy or sign in, build the smallest runnable thing instead of writing it down.
3. A build counts only when it leaves a short receipt and a check that passes. Otherwise it reports failed.

The measurement behind it: the idea engine this rule came from judged 175 ideas over 24 nightly runs and acted on 3. Of its 175 planned actions, 127 (73%) were a new backlog entry for its owner. `examples/actions.jsonl` holds the verdict, the planned action kind and the date of the nightly run (`night`) of each of those 175 ideas, with the idea text removed. Two commands reproduce both numbers:

```
python3 spike.py count examples/actions.jsonl --key kind --todo backlog_entry
python3 spike.py count examples/actions.jsonl --key verdict
```

The first prints `to-do share: 127 of 175 (72.6%)` and exits 1, because the share is above the default limit of 0.5. The second prints how many ideas got each verdict: 106 SEED, 64 SHELVE, 3 ACT and 2 KILL.

## What you get

Six commands, with their logic in five files (`new` and `close` share `receipt.py`):

| Command | What it does | Exit codes |
|---|---|---|
| `count FILE --key KEY` | Counts rows by kind and reports the share that are to-dos | 0 within the limit, 1 above it |
| `gate PLAN.json` | Says BUILD or ASK for one plan | 0 build, 1 ask |
| `screen FILE` | Reads a check script for commands that must not run unattended | 0 OK, 1 UNSAFE |
| `new TITLE` | Starts a spike folder with a receipt template and a check stub | 0 started, 1 daily cap reached |
| `close SPIKE_DIR --verify-exit N` | Closes a spike under the receipt-and-check rule and records it | 0 BUILT, 1 FAILED |
| `fates` | Shows what became of every recorded spike | 0 |

Every command exits 2 with one line on standard error when its arguments or its input are bad.

This is real output from `bash examples/demo.sh` (the date and the folder name come from the day it ran). It walks through every command offline in a temporary folder and removes the folder at the end:

```
== count: how much of the output is a to-do for a person (expect exit 1)
backlog_entry     127   72.6%  to-do
none               22   12.6%
draft_spec         12    6.9%
(missing)          11    6.3%
research_dossier    2    1.1%
domain_check        1    0.6%
to-do share: 127 of 175 (72.6%)

== count: the same rows by verdict (expect exit 0)
SEED    106   60.6%
SHELVE   64   36.6%
ACT       3    1.7%
KILL      2    1.1%

== gate: a cheap, low-stakes plan with a harmless step (expect BUILD, exit 0)
BUILD: cheap first version (85), low stakes, no forbidden step in the planned action

== gate: the planned step spends money (expect ASK, exit 1)
ASK: planned action spends money

== gate: the first version is not cheap (expect ASK, exit 1)
ASK: first version is not cheap enough (cheapness 20 < 70)

== screen: an ordinary check script (expect OK, exit 0)
OK

== screen: a script that pipes a download into a shell (expect UNSAFE, exit 1)
UNSAFE: pipe-to-shell

== new: start a spike folder
spikes/2026-11-17-01-turn-a-text-table-into-json

== close: the receipt is empty and the check is the stub (expect FAILED, exit 1)
FAILED: receipt has an empty section: What now exists

== fill the folder with the sample spike, screen its check, then run it
OK
verify.sh exit code: 0

== close: pass the exit code (expect BUILT, exit 0)
BUILT: spikes/2026-11-17-01-turn-a-text-table-into-json

== fates: what became of each build
1 spike(s) recorded, verified 1 (100%), untouched 1
2026-11-17 verified [untouched] Turn a text table into JSON
    2026-11-17-01-turn-a-text-table-into-json

demo finished
```

## Quick start

```
git clone https://github.com/SanDiegoAIStudio/build-spike.git
cd build-spike
bash examples/demo.sh
```

You need `python3` on your path (the kit is written for Python 3.9) and bash. Each step of the demo prints a heading that says what to expect:

- The `count` steps read the 175 rows in `examples/actions.jsonl`. The first exits 1 on purpose, because most rows are to-dos. The second counts the same rows by verdict.
- The three `gate` steps show one plan that may build and two that must ask: one plans to spend money, one is not cheap.
- The two `screen` steps show a check script that passes and one that pipes a download into a shell.
- `new` makes a spike folder. `close` fails on it, because the receipt is empty and the check is still the stub.
- The demo then copies in the finished sample from `examples/sample-spike`, screens that sample's `verify.sh` before it runs it, and closes with the exit code it returned. This time `close` prints `BUILT`.
- `fates` lists one spike, not two, because the passing close replaced the row the failed close left for the same folder.

The demo changes nothing inside the repository. The only check script it runs is the sample's own `verify.sh`, inside the temporary folder.

## Count what your automation produces

`count` reads a JSON list of objects or a JSON Lines file, one object per line. Name the field to count by with `--key`; a dotted key such as `plan.type` reaches into nested objects.

```
python3 spike.py count rows.jsonl --key kind --todo backlog_entry,note_to_self --max-share 0.5
```

It prints one line per kind, most frequent first and then by name: the kind, its count, its share as a percent and, for the kinds named in `--todo`, the word `to-do`. A row that lacks the key, or holds `null` there, counts under `(missing)`. Values that are not text are counted by their JSON text. With `--todo` it ends with `to-do share: A of B (P%)` and exits 1 when that share is above `--max-share`, which defaults to 0.5. Without `--todo` it exits 0. A line that is not a JSON object stops the count with exit 2 and names the line.

## Decide: build or ask

`gate` reads a JSON object with three fields. Every other field is ignored.

| Field | Meaning |
|---|---|
| `cheapness` | A whole number from 0 to 100 for how cheap the first runnable version is. 100 is minutes of work, 0 is months. A missing value, a boolean, a float, a string or a number outside 0 to 100 asks. |
| `stakes` | `low`, `medium` or `high`, in any case. A missing or other value asks. |
| `action` | The text of the step the automation plans to take, as opposed to what the idea is about. A missing or empty value asks. |

```
python3 spike.py gate examples/plan-build.json
```

The checks run in that order and the first failure decides. Cheapness below the threshold (70 unless you pass `--threshold`) asks. High stakes ask, and high stakes means committed revenue, legal matters, spending or anything outward-facing. Then the planned action is searched, in lower case, for the five forbidden categories:

| Category | Reason printed | Example phrase |
|---|---|---|
| Spends money | `planned action spends money` | `buy the domain and pay for a year` |
| Sends something outward | `planned action sends something outward` | `send the email to the list` |
| Touches production | `planned action touches production` | `deploy to production` |
| Touches credentials | `planned action touches credentials` | `rotate the api key` |
| Destructive | `planned action destructive` | `drop table users` |

Each category also catches the usual plural and past forms and a few close wordings, for example `send emails to customers`, `read passwords`, `delete the folder` and `git push --force`. Spending also counts charge, refund, donate, money and fund, so `wire funds to the vendor` asks while `wire up the parser` still builds, because a bare wire is not on the list. Sending outward also counts notify, upload, message, mail, share, invite and submit, plus phone, dial and voicemail. The forms call, calls, called and calling ask only when followed by an optional article or possessive (the, a, an, my, our, their or your) and a person word (customer, client, lead, user, owner, vendor, people, someone or them, each with an optional plural s), so `call the parser` still builds. Production also counts `git push`, and push, pushes, pushed or pushing followed by to. `git push --force` stays destructive. Destructive also counts remove and overwrite.

Only the action is screened. An idea may be about customers or money; what matters is that the automatic step taken on it does not spend, send, deploy, sign in or destroy. A plan that passes prints `BUILD` with the numbers behind it; any other plan prints `ASK` with the reason and exits 1.

The gate gives permission and does not rank. If ten ideas pass, order them however you like.

## Screen the check script

`screen` reads a script and reports the first of nine patterns it finds, ignoring case. It prints `OK` or `UNSAFE: reason`.

| Reason | What it looks for |
|---|---|
| rm -rf on an absolute/home path | `rm` aimed at a path that starts with `~`, `/`, `..`, `$HOME` or `${HOME}`, quoted or not, when any recursive flag form counts (`-r`, `-R`, a cluster such as `-rfv`, or `--recursive`), with other options and `--` allowed before the path, such as `rm -rf ~/projects`. A path that starts with `..` counts when the next character is `/`, a quote, a space or the end of the line, such as `rm -rf ..` and `rm -rf ../x`. A relative path such as `rm -rf ./build` does not count. |
| sudo | the word `sudo` |
| pipe-to-shell | `curl` or `wget` piped into a shell or another interpreter, on one line or over lines that end in a backslash. `sh`, `bash`, `zsh`, `dash` and `ksh` count whatever follows them, also when written with a path, after `env`, or both; `env` may carry option words such as `-i` or `-S` and `NAME=value` settings, and may itself be written with a path. `python` (including `python2`, `python3` and a minor version such as `python3.9`), `perl`, `ruby`, `node`, `php` and `fish` may also be written with a path or after `env`, and count in two cases: a lone `-` or `/dev/stdin` comes after them and any option words, whatever follows it; or only option words follow them, and the command then ends or goes on with `;`, `&`, a further pipe, a redirect such as `2>&1` or `> out`, a closing `)` or a `#` comment. They do not count when they name a script, a module or code of their own, such as `python3 -m json.tool`. `bash -c "$(curl ...)"`, `eval "$(curl ...)"` and `<(curl ...)` count too. |
| git push | `git push` |
| system control | `shutdown`, `reboot`, `kill -9`, `killall -9`, `launchctl`, `systemctl` |
| remote access | `ssh`, `scp` or `rsync`, such as `scp out.txt backup:/tmp` |
| secret material | `.env` files, `1password`, `op item` and `keychain`. A path under `.ssh` is reported as remote access, because that pattern comes first. |
| writes outside the workspace | a redirect into `/etc`, `/usr`, `/bin` or `/var` |
| schedules work | `crontab` or `at now` |

The screen is a pattern check. It reads text and runs nothing.

## Leave a receipt and a check

```
python3 spike.py new "Turn a text table into JSON"
```

This creates `spikes/YYYY-MM-DD-NN-turn-a-text-table-into-json` (the folder is `--root` or `$SPIKE_ROOT` when you set one) and prints only its path. NN counts up from 01 for each date, and an existing folder is never reused. The folder holds two files:

- `RECEIPT.md`, a template with five sections that must each be filled in: What now exists, How to run it, What it proved, What it did not do, Next step. A section counts when it has a level 2 heading with one of those names and at least one non-blank line under it.
- `verify.sh`, a stub marked `SPIKE-STUB` that exits 1. Replace it with a check that exits 0 only when the spike works.

`new` stops at two spikes a day and prints `CAP: ...` on standard error with exit 1. The cap exists because a build is cheap and its owner's attention is not. Pass `--max-per-day N` to change the limit, or `--max-per-day 0` to turn the cap off.

`close` takes the exit code you got from running the check:

```
python3 spike.py close spikes/2026-01-15-01-turn-a-text-table-into-json --verify-exit 0
```

It prints `BUILT: folder` and exits 0, or prints `FAILED: reason` and exits 1. Both outcomes are recorded. The checks run in this order and the first failure is the reason:

1. `no receipt`
2. `receipt is missing the section: NAME` or `receipt has an empty section: NAME`
3. `no check script`
4. `verify.sh is still the stub`
5. `verify.sh failed the screen: REASON`
6. `check failed (exit N)`, when the exit code you pass is not 0

A folder that does not exist exits 2 and records nothing. `close` never runs `verify.sh`. You run it and pass the result in.

## See what became of each build

```
python3 spike.py fates
```

`fates` prints a summary line, then one entry per recorded spike, newest first: the date, `verified` or `failed`, the fate in square brackets and the idea, with the folder on the next line. Add `--json` for the rows as a JSON list. The record is `index.json` inside the root. `close` and `fates` take the same `--root` as `new` (default `$SPIKE_ROOT`, else `./spikes`), so give all three the same root; a `close` run with another root starts a second record there. Closing the same folder again replaces its row.

There are four fates:

- `no-dir`: the row has no folder.
- `deleted`: the folder no longer exists.
- `touched`: some file in the folder changed after the build time plus a grace period, 300 seconds unless you pass `--grace-seconds`.
- `untouched`: nothing changed after that.

`touched` is the signal that a build mattered. Somebody came back and changed it, which they do for things they use. A build that is `untouched` or `deleted` was probably not worth the attention it asked for, and a run of those is a reason to raise the bar in the gate.

## Use it from your own automation

A shell loop around the commands. Your own builder fills the folder; the kit only decides, records and holds the rule.

```
if python3 spike.py gate plan.json; then
  dir="$(python3 spike.py new "$TITLE")" || exit 1
  # your builder writes RECEIPT.md, verify.sh and the rest into "$dir"
  python3 spike.py screen "$dir/verify.sh" || exit 1
  # run the check somewhere a mistake is cheap and capture its exit code in CODE
  python3 spike.py close "$dir" --verify-exit "$CODE"
fi
```

The same with the Python functions, from the repository folder:

```python
import gate
import receipt
import screen

ok, reason = gate.decide({"cheapness": 85, "stakes": "low", "action": "parse the saved tables into json locally"})
if ok:
    folder = receipt.new_spike("spikes", "Compare three pricing pages")
    # your builder writes into folder
    problem = screen.unsafe_shell((folder / "verify.sh").read_text())
    if problem is None:
        # run the check where a mistake is cheap and put its exit code in code
        ok, reason = receipt.close_spike(folder, verify_exit=code, index_path="spikes/index.json")
```

`receipt.new_spike` raises `receipt.CapReached` at the daily cap. `receipt.close_spike` raises `FileNotFoundError` when the folder does not exist. `index.fates(index_path)` returns the rows with their fates, and `count.count_kinds(rows, key)` does the counting.

## Tests

```
python3 -m unittest discover -s tests
python3 tests/mutate.py
```

The first runs the unit tests in about ten seconds and reports 232 tests. The second proves they can fail: it breaks the code one place at a time in a temporary copy of the repository, runs the tests against each copy, prints `killed` when the tests noticed and `SURVIVED` when they did not, and exits 1 if any survived. It reports 99 mutations, and every one is killed. On the macOS machine the tests were run on, the mutation run took between 8 and 17 minutes. The tests use only temporary folders, run no check script except the sample's own `verify.sh` inside a temporary copy, and leave nothing behind in the repository.

## Limits

- The kit never runs the check script and never builds anything itself. `close` trusts the exit code it is given.
- The screen and the forbidden list are pattern checks that a determined script can get past. The screen is not a sandbox, so run a check that a model wrote in a container, a throwaway machine or a restricted account. The screen still misses a download that reaches a shell through another command, such as a second pipe through `tee`. An interpreter that names its own script or module is not counted, so a download piped into a program that runs its input another way is not caught. An option that takes a separate value, such as `python3 -W ignore` or `env -u NAME bash`, is read as the program or script name, so that form is not counted.
- The patterns are blunt on purpose and will ask about harmless wording. Any action naming one of the plain words in the lists asks, for example `convert text to json` and `count words in the text file` (the word `text`), `write a blog post draft` (`post`), `count tokens in the prompt` (`token`), `list deleted files` (`deleted`) and `remove duplicate rows` (`remove`). A wrong ask costs one question.
- `count` splits lines the way Python's `str.splitlines` does, so a JSONL row holding a raw U+2028 or U+2029 character inside a string is reported as not valid JSON.
- The screen reads `verify.sh` only. It does not read the files that `verify.sh` runs, such as `table_to_json.py` in the sample, so screen those yourself or keep the whole check inside `verify.sh`.
- The forbidden list is English only.
- The record uses a file lock, so the kit works on POSIX systems only.
- The daily cap is counted without a lock, so two `new` commands started at the same moment can both pass it. Each still gets its own folder.
- The daily cap counts the spike folders in the root that carry today's date, so deleting one frees a slot.
- `close` treats any `verify.sh` that holds the text `SPIKE-STUB` anywhere, a comment included, as the unedited stub.
- The tests were run on macOS with Python 3.9.6. They were not run on Linux, on Windows or on other Python versions.
- `touched` only means a file in the folder changed after the grace period. It does not say who changed it or why.
- `close` trusts the exit code you pass with `--verify-exit`, so run `verify.sh` yourself after `screen` passes and pass the code it really returned.
- The screen reads shell text only, so a check that hands code to another interpreter, such as `python3 -c`, is not read for what that code does.
- `tests/mutate.py` counts a suite run that passes its 180 second time limit as killed, so on a slow or loaded machine a mutation the tests miss can show as killed. The one mutation that removes the record's lock runs five times, because a race can hide it, and counts as killed only when all five runs fail.

## License

MIT. See `LICENSE`.

## Built at San Diego AI Studio

The rule and this kit come out of San Diego AI Studio, the builders' community in San Diego, where builders show the systems they run. More at https://sandiegoaistudio.com/projects.
