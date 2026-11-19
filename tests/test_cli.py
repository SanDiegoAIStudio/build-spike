import json
import os
import shutil
import unittest

import support
from support import CliCase, write
import receipt

FILLED = "\n".join(
    ["# Receipt: Cli idea", ""]
    + ["\n".join(["## %s" % name, "", "Something true.", ""]) for name in receipt.SECTIONS])
PLAN_OK = {"title": "t", "cheapness": 90, "stakes": "low", "action": "parse a file locally"}


class UsageTests(CliCase):
    def assert_one_line_error(self, run):
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertEqual(run.stdout, "")
        lines = run.stderr.splitlines()
        self.assertEqual(len(lines), 1, run.stderr)
        self.assertTrue(lines[0].startswith("spike: "), lines[0])

    def test_no_command_is_a_usage_error(self):
        self.assert_one_line_error(self.cli())

    def test_an_unknown_command_is_a_usage_error(self):
        self.assert_one_line_error(self.cli("frobnicate"))

    def test_help_exits_zero_and_lists_every_command(self):
        run = self.cli("--help")
        self.assertEqual(run.returncode, 0)
        for name in ("count", "gate", "screen", "new", "close", "fates"):
            self.assertIn(name, run.stdout)

    def test_each_command_has_its_own_help(self):
        for name in ("count", "gate", "screen", "new", "close", "fates"):
            run = self.cli(name, "--help")
            self.assertEqual(run.returncode, 0, name)
            self.assertIn("usage:", run.stdout)

    def test_nothing_is_created_by_the_read_only_commands(self):
        write(self.path("plan.json"), json.dumps(PLAN_OK))
        write(self.path("rows.jsonl"), '{"k": "a"}\n')
        write(self.path("v.sh"), "echo hi\n")
        self.cli("gate", "plan.json")
        self.cli("count", "rows.jsonl", "--key", "k")
        self.cli("screen", "v.sh")
        self.cli("fates")
        self.assertEqual(sorted(os.listdir(self.tmp)), ["plan.json", "rows.jsonl", "v.sh"])


class CountTests(CliCase):
    def rows(self, text='{"kind": "a"}\n{"kind": "a"}\n{"kind": "b"}\n{"x": 1}\n'):
        return write(self.path("rows.jsonl"), text)

    def test_counts_are_aligned_and_sorted_by_size(self):
        self.rows()
        run = self.cli("count", "rows.jsonl", "--key", "kind")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.splitlines(), [
            "a          2   50.0%",
            "(missing)  1   25.0%",
            "b          1   25.0%"])

    def test_todo_kinds_are_marked_and_the_share_is_printed(self):
        self.rows()
        run = self.cli("count", "rows.jsonl", "--key", "kind", "--todo", "a", "--max-share", "0.5")
        self.assertEqual(run.returncode, 0, run.stderr)
        lines = run.stdout.splitlines()
        self.assertTrue(lines[0].endswith("to-do"), lines[0])
        self.assertFalse(lines[1].endswith("to-do"))
        self.assertEqual(lines[-1], "to-do share: 2 of 4 (50.0%)")

    def test_a_share_above_the_limit_exits_1(self):
        self.rows()
        run = self.cli("count", "rows.jsonl", "--key", "kind", "--todo", "a,b", "--max-share", "0.5")
        self.assertEqual(run.returncode, 1)
        self.assertIn("to-do share: 3 of 4 (75.0%)", run.stdout)

    def test_a_share_equal_to_the_limit_exits_0(self):
        self.rows()
        run = self.cli("count", "rows.jsonl", "--key", "kind", "--todo", "a", "--max-share", "0.5")
        self.assertEqual(run.returncode, 0)

    def test_the_default_limit_is_one_half(self):
        self.rows()
        self.assertEqual(self.cli("count", "rows.jsonl", "--key", "kind", "--todo", "a").returncode, 0)
        self.assertEqual(self.cli("count", "rows.jsonl", "--key", "kind", "--todo", "a,b").returncode, 1)

    def test_a_limit_of_one_never_fails(self):
        self.rows()
        run = self.cli("count", "rows.jsonl", "--key", "kind", "--todo", "a,b,(missing)", "--max-share", "1")
        self.assertEqual(run.returncode, 0)

    def test_without_todo_there_is_no_share_line(self):
        self.rows()
        run = self.cli("count", "rows.jsonl", "--key", "kind")
        self.assertNotIn("to-do", run.stdout)

    def test_the_bundled_example_is_over_the_limit(self):
        run = self.cli("count", os.path.join(support.EXAMPLES, "actions.jsonl"), "--key", "kind",
                       "--todo", "backlog_entry")
        self.assertEqual(run.returncode, 1)
        self.assertIn("backlog_entry", run.stdout)
        self.assertIn("to-do share: 127 of 175 (72.6%)", run.stdout)

    def test_an_empty_file_says_no_rows(self):
        write(self.path("empty.jsonl"), "")
        run = self.cli("count", "empty.jsonl", "--key", "kind", "--todo", "a")
        self.assertEqual(run.returncode, 0)
        self.assertIn("no rows", run.stdout)
        self.assertIn("to-do share: 0 of 0 (0.0%)", run.stdout)

    def test_a_json_list_works_too(self):
        write(self.path("rows.json"), '[{"kind": "a"}, {"kind": "b"}]')
        run = self.cli("count", "rows.json", "--key", "kind")
        self.assertEqual(run.returncode, 0)
        self.assertEqual(len(run.stdout.splitlines()), 2)

    def test_a_dotted_key_works(self):
        write(self.path("rows.jsonl"), '{"meta": {"kind": "a"}}\n{"meta": {"kind": "a"}}\n')
        run = self.cli("count", "rows.jsonl", "--key", "meta.kind")
        self.assertEqual(run.stdout.splitlines(), ["a  2  100.0%"])

    def test_bad_input_exits_2_with_one_line(self):
        self.rows('{"kind": "a"}\nnot json\n')
        run = self.cli("count", "rows.jsonl", "--key", "kind")
        self.assertEqual(run.returncode, 2)
        self.assertEqual(run.stdout, "")
        self.assertEqual(run.stderr.splitlines(), ["spike: rows.jsonl: line 2 is not valid JSON"])

    def test_a_missing_file_exits_2(self):
        run = self.cli("count", "nothing.jsonl", "--key", "kind")
        self.assertEqual(run.returncode, 2)
        self.assertTrue(run.stderr.startswith("spike: cannot read nothing.jsonl"))

    def test_a_missing_key_option_exits_2(self):
        self.rows()
        self.assertEqual(self.cli("count", "rows.jsonl").returncode, 2)

    def test_an_empty_key_exits_2(self):
        self.rows()
        self.assertEqual(self.cli("count", "rows.jsonl", "--key", "  ").returncode, 2)

    def test_a_limit_outside_0_to_1_exits_2(self):
        self.rows()
        for bad in ("1.5", "-0.1", "abc"):
            run = self.cli("count", "rows.jsonl", "--key", "kind", "--todo", "a", "--max-share", bad)
            self.assertEqual(run.returncode, 2, bad)

    def test_an_empty_todo_list_exits_2(self):
        self.rows()
        self.assertEqual(self.cli("count", "rows.jsonl", "--key", "kind", "--todo", " , ").returncode, 2)


class GateTests(CliCase):
    def plan(self, **changes):
        plan = dict(PLAN_OK)
        plan.update(changes)
        return write(self.path("plan.json"), json.dumps(plan))

    def test_build_exits_0(self):
        self.plan()
        run = self.cli("gate", "plan.json")
        self.assertEqual(run.returncode, 0)
        self.assertTrue(run.stdout.startswith("BUILD: cheap first version (90)"), run.stdout)

    def test_ask_exits_1_with_the_reason(self):
        self.plan(action="buy a domain")
        run = self.cli("gate", "plan.json")
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, "ASK: planned action spends money\n")

    def test_the_bundled_plans(self):
        expected = {"plan-build.json": 0, "plan-spends.json": 1, "plan-costly.json": 1}
        for name, code in expected.items():
            self.assertEqual(self.cli("gate", os.path.join(support.EXAMPLES, name)).returncode, code, name)

    def test_the_plan_can_come_from_standard_input(self):
        run = self.cli("gate", "-", stdin=json.dumps(PLAN_OK))
        self.assertEqual(run.returncode, 0)
        run = self.cli("gate", "-", stdin=json.dumps(dict(PLAN_OK, stakes="high")))
        self.assertEqual(run.returncode, 1)

    def test_the_threshold_option(self):
        self.plan(cheapness=50)
        self.assertEqual(self.cli("gate", "plan.json").returncode, 1)
        self.assertEqual(self.cli("gate", "plan.json", "--threshold", "50").returncode, 0)
        self.assertEqual(self.cli("gate", "plan.json", "--threshold", "51").returncode, 1)

    def test_a_threshold_outside_0_to_100_exits_2(self):
        self.plan()
        for bad in ("101", "-1", "x", "7.5"):
            self.assertEqual(self.cli("gate", "plan.json", "--threshold", bad).returncode, 2, bad)

    def test_bad_json_exits_2(self):
        write(self.path("plan.json"), "{not json")
        run = self.cli("gate", "plan.json")
        self.assertEqual(run.returncode, 2)
        self.assertEqual(len(run.stderr.splitlines()), 1)

    def test_a_list_is_not_a_plan(self):
        write(self.path("plan.json"), "[1, 2]")
        run = self.cli("gate", "plan.json")
        self.assertEqual(run.returncode, 2)
        self.assertIn("must hold one JSON object", run.stderr)

    def test_a_missing_file_exits_2(self):
        self.assertEqual(self.cli("gate", "nothing.json").returncode, 2)

    def test_a_plan_without_the_fields_asks_and_exits_1(self):
        write(self.path("plan.json"), "{}")
        run = self.cli("gate", "plan.json")
        self.assertEqual(run.returncode, 1)
        self.assertTrue(run.stdout.startswith("ASK: no usable cheapness"))


class ScreenTests(CliCase):
    def test_ok_exits_0(self):
        write(self.path("v.sh"), "#!/bin/sh\ntest -f out.txt\n")
        run = self.cli("screen", "v.sh")
        self.assertEqual((run.returncode, run.stdout), (0, "OK\n"))

    def test_unsafe_exits_1_with_the_reason(self):
        write(self.path("v.sh"), "sudo make install\n")
        run = self.cli("screen", "v.sh")
        self.assertEqual((run.returncode, run.stdout), (1, "UNSAFE: sudo\n"))

    def test_the_bundled_scripts(self):
        self.assertEqual(self.cli("screen", os.path.join(support.EXAMPLES, "verify-good.sh")).stdout, "OK\n")
        bad = self.cli("screen", os.path.join(support.EXAMPLES, "verify-bad.sh"))
        self.assertEqual((bad.returncode, bad.stdout), (1, "UNSAFE: pipe-to-shell\n"))

    def test_standard_input(self):
        self.assertEqual(self.cli("screen", "-", stdin="echo ok\n").returncode, 0)
        self.assertEqual(self.cli("screen", "-", stdin="git push\n").returncode, 1)

    def test_the_script_is_never_run(self):
        write(self.path("v.sh"), "touch ran-marker\n")
        self.cli("screen", "v.sh")
        self.assertFalse(os.path.exists(self.path("ran-marker")))

    def test_bytes_that_are_not_text_do_not_crash_it(self):
        with open(self.path("v.sh"), "wb") as handle:
            handle.write(b"echo \xff\xfe ok\n")
        self.assertEqual(self.cli("screen", "v.sh").returncode, 0)
        with open(self.path("v2.sh"), "wb") as handle:
            handle.write(b"\xff\nsudo ls\n")
        self.assertEqual(self.cli("screen", "v2.sh").returncode, 1)

    def test_a_missing_file_exits_2(self):
        run = self.cli("screen", "nothing.sh")
        self.assertEqual(run.returncode, 2)
        self.assertTrue(run.stderr.startswith("spike: cannot read nothing.sh"))


class NewAndCloseTests(CliCase):
    def new(self, title, *extra, **kwargs):
        return self.cli("new", title, *extra, **kwargs)

    def test_new_prints_only_the_path(self):
        run = self.new("Turn a text table into JSON")
        self.assertEqual(run.returncode, 0, run.stderr)
        lines = run.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(os.path.join("spikes", "")), lines[0])
        self.assertTrue(lines[0].endswith("-01-turn-a-text-table-into-json"), lines[0])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, lines[0], "RECEIPT.md")))
        self.assertEqual(run.stderr, "")

    def test_the_third_new_spike_of_the_day_is_stopped(self):
        self.assertEqual(self.new("a").returncode, 0)
        self.assertEqual(self.new("b").returncode, 0)
        run = self.new("c")
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, "")
        self.assertTrue(run.stderr.startswith("CAP: 2 spikes already started today (limit 2)"), run.stderr)
        self.assertEqual(len(os.listdir(self.path("spikes"))), 2)

    def test_max_per_day_changes_the_limit_and_zero_turns_it_off(self):
        self.assertEqual(self.new("a", "--max-per-day", "1").returncode, 0)
        self.assertEqual(self.new("b", "--max-per-day", "1").returncode, 1)
        for name in "cdefg":
            self.assertEqual(self.new(name, "--max-per-day", "0").returncode, 0)

    def test_a_negative_limit_and_an_empty_title_exit_2(self):
        self.assertEqual(self.new("a", "--max-per-day", "-1").returncode, 2)
        self.assertEqual(self.new("   ").returncode, 2)
        self.assertFalse(os.path.exists(self.path("spikes")))

    def test_root_option_and_environment_variable(self):
        run = self.new("a", "--root", "mine")
        self.assertTrue(run.stdout.startswith("mine"), run.stdout)
        run = self.new("b", env={"SPIKE_ROOT": "fromenv"})
        self.assertTrue(run.stdout.startswith("fromenv"), run.stdout)
        run = self.new("c", "--root", "flag", env={"SPIKE_ROOT": "fromenv"})
        self.assertTrue(run.stdout.startswith("flag"), run.stdout)
        self.assertEqual(sorted(os.listdir(self.tmp)), ["flag", "fromenv", "mine"])

    def test_an_empty_environment_variable_means_the_default(self):
        run = self.new("a", env={"SPIKE_ROOT": ""})
        self.assertTrue(run.stdout.startswith("spikes"), run.stdout)

    def test_a_root_that_cannot_be_made_exits_2(self):
        write(self.path("blocker"), "a file")
        run = self.new("a", "--root", os.path.join("blocker", "inside"))
        self.assertEqual(run.returncode, 2)
        self.assertTrue(run.stderr.startswith("spike: cannot create the spike folder"))

    def test_close_of_a_fresh_folder_fails_and_is_recorded(self):
        folder = self.new("idea").stdout.strip()
        run = self.cli("close", folder, "--verify-exit", "0")
        self.assertEqual((run.returncode, run.stdout),
                         (1, "FAILED: receipt has an empty section: What now exists\n"))
        with open(self.path("spikes", "index.json")) as handle:
            rows = json.load(handle)
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]["verified"], False)

    def test_close_of_a_finished_folder_prints_built_and_records_it(self):
        folder = self.new("idea").stdout.strip()
        write(self.path(folder, "RECEIPT.md"), FILLED)
        write(self.path(folder, "verify.sh"), "#!/bin/sh\ntest -f RECEIPT.md\n")
        run = self.cli("close", folder, "--verify-exit", "0")
        self.assertEqual((run.returncode, run.stdout), (0, "BUILT: %s\n" % folder))
        with open(self.path("spikes", "index.json")) as handle:
            rows = json.load(handle)
        self.assertIs(rows[0]["verified"], True)
        self.assertEqual(rows[0]["dir"], os.path.basename(folder))
        self.assertEqual(rows[0]["idea"], "Cli idea")

    def test_a_failing_check_exit_code_fails_the_close(self):
        folder = self.new("idea").stdout.strip()
        write(self.path(folder, "RECEIPT.md"), FILLED)
        write(self.path(folder, "verify.sh"), "#!/bin/sh\ntest -f RECEIPT.md\n")
        run = self.cli("close", folder, "--verify-exit", "4")
        self.assertEqual((run.returncode, run.stdout), (1, "FAILED: check failed (exit 4)\n"))

    def test_close_uses_root_for_the_index(self):
        folder = self.new("idea", "--root", "r").stdout.strip()
        self.cli("close", folder, "--verify-exit", "0", "--root", "r")
        self.assertTrue(os.path.isfile(self.path("r", "index.json")))
        self.assertFalse(os.path.exists(self.path("spikes")))

    def test_close_of_a_missing_folder_exits_2_and_records_nothing(self):
        run = self.cli("close", "nothing-here", "--verify-exit", "0")
        self.assertEqual(run.returncode, 2)
        self.assertEqual(run.stderr.splitlines(), ["spike: nothing-here is not a folder"])
        self.assertFalse(os.path.exists(self.path("spikes")))

    def test_close_of_a_file_exits_2(self):
        write(self.path("a-file"), "x")
        self.assertEqual(self.cli("close", "a-file", "--verify-exit", "0").returncode, 2)

    def test_close_needs_the_exit_code_as_a_whole_number(self):
        folder = self.new("idea").stdout.strip()
        self.assertEqual(self.cli("close", folder).returncode, 2)
        self.assertEqual(self.cli("close", folder, "--verify-exit", "ok").returncode, 2)
        self.assertEqual(self.cli("close", folder, "--verify-exit", "0.5").returncode, 2)
        self.assertFalse(os.path.exists(self.path("spikes", "index.json")))


class FatesTests(CliCase):
    def test_no_record_yet(self):
        run = self.cli("fates")
        self.assertEqual((run.returncode, run.stdout), (0, "No spikes recorded yet.\n"))

    def seed(self):
        for name in ("old", "new", "gone"):
            os.makedirs(self.path("spikes", name), exist_ok=True)
            os.utime(write(self.path("spikes", name, "f.txt"), "x"), (1000, 1000))
        shutil.rmtree(self.path("spikes", "gone"))
        rows = [
            {"idea": "older one", "dir": "old", "date": "2026-01-01", "built_at": 1000, "verified": True},
            {"idea": "newer one", "dir": "new", "date": "2026-02-01", "built_at": 1000, "verified": False},
            {"idea": "lost one", "dir": "gone", "date": "2026-01-15", "built_at": 1000, "verified": True},
            {"idea": "no folder", "date": "2026-03-01", "built_at": 1000, "verified": True},
        ]
        write(self.path("spikes", "index.json"), json.dumps(rows))

    def test_rows_are_listed_newest_first_with_a_summary(self):
        self.seed()
        run = self.cli("fates")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.splitlines(), [
            "4 spike(s) recorded, verified 3 (75%), deleted 1, no-dir 1, untouched 2",
            "2026-03-01 verified [no-dir] no folder",
            "    ",
            "2026-02-01 failed [untouched] newer one",
            "    new",
            "2026-01-15 verified [deleted] lost one",
            "    gone",
            "2026-01-01 verified [untouched] older one",
            "    old"])

    def test_json_output(self):
        self.seed()
        run = self.cli("fates", "--json")
        self.assertEqual(run.returncode, 0)
        rows = json.loads(run.stdout)
        self.assertEqual([row["fate"] for row in rows], ["untouched", "untouched", "deleted", "no-dir"])

    def test_json_output_with_no_record_is_an_empty_list(self):
        self.assertEqual(json.loads(self.cli("fates", "--json").stdout), [])

    def test_the_grace_option(self):
        self.seed()
        os.utime(self.path("spikes", "new", "f.txt"), (1100, 1100))
        by_idea = lambda args: {r["idea"]: r["fate"] for r in json.loads(self.cli("fates", "--json", *args).stdout)}
        self.assertEqual(by_idea([])["newer one"], "untouched")
        self.assertEqual(by_idea(["--grace-seconds", "50"])["newer one"], "touched")
        self.assertEqual(self.cli("fates", "--grace-seconds", "-1").returncode, 2)

    def test_root_option(self):
        self.seed()
        os.rename(self.path("spikes"), self.path("moved"))
        self.assertEqual(self.cli("fates").stdout, "No spikes recorded yet.\n")
        self.assertIn("4 spike(s)", self.cli("fates", "--root", "moved").stdout)

    def test_a_damaged_index_reads_as_empty(self):
        write(self.path("spikes", "index.json"), "damaged")
        run = self.cli("fates")
        self.assertEqual((run.returncode, run.stdout), (0, "No spikes recorded yet.\n"))
        with open(self.path("spikes", "index.json")) as handle:
            self.assertEqual(handle.read(), "damaged")


if __name__ == "__main__":
    unittest.main()
