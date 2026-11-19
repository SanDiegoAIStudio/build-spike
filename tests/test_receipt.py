import datetime
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

import support
from support import TempCase, write
import receipt

FILLED = "\n".join(
    ["# Receipt: Turn a text table into JSON", "", "Every section below must be filled in.", ""]
    + ["\n".join(["## %s" % name, "", "Something true about it.", ""]) for name in receipt.SECTIONS])

GOOD_CHECK = "#!/bin/sh\npython3 main.py > out.txt\ngrep -q ok out.txt\n"
NOW = 1_700_000_000.0


def local_date(stamp):
    return datetime.datetime.fromtimestamp(stamp).date().isoformat()


class SlugTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(receipt.slugify("Turn a text table into JSON"), "turn-a-text-table-into-json")
        self.assertEqual(receipt.slugify("  --Hello,   World!!  "), "hello-world")
        self.assertEqual(receipt.slugify("a" * 60), "a" * 40)
        self.assertEqual(receipt.slugify("!!!"), "idea")
        self.assertEqual(receipt.slugify(""), "idea")

    def test_a_cut_never_leaves_a_trailing_hyphen(self):
        title = "a" * 39 + " b"
        self.assertEqual(receipt.slugify(title), "a" * 39)


class NewSpikeTests(TempCase):
    def test_three_spikes_are_numbered_01_02_03(self):
        names = [os.path.basename(receipt.new_spike(self.tmp, "same title", today="2026-01-05", max_per_day=0))
                 for _ in range(3)]
        self.assertEqual(names, ["2026-01-05-01-same-title", "2026-01-05-02-same-title", "2026-01-05-03-same-title"])

    def test_the_folder_holds_a_receipt_and_a_stub(self):
        folder = receipt.new_spike(self.path("spikes"), "Turn a text table into JSON", today="2026-01-05")
        self.assertTrue(folder.is_dir())
        text = (folder / "RECEIPT.md").read_text()
        lines = text.splitlines()
        self.assertEqual(lines[0], "# Receipt: Turn a text table into JSON")
        self.assertIn("filled in before this spike can be closed", text)
        headings = [line for line in lines if line.startswith("## ")]
        self.assertEqual(headings, ["## %s" % name for name in receipt.SECTIONS])
        stub = (folder / "verify.sh").read_text().splitlines()
        self.assertEqual(stub[0], "#!/bin/sh")
        self.assertIn(receipt.STUB_MARK, stub[1])
        self.assertTrue(stub[1].startswith("#"))
        self.assertIn(">&2", stub[2])
        self.assertEqual(stub[-1], "exit 1")

    def test_an_untouched_new_folder_cannot_be_closed(self):
        folder = receipt.new_spike(self.path("spikes"), "idea", today="2026-01-05")
        ok, why = receipt.close_spike(folder, 0, self.path("spikes", "index.json"), now=NOW)
        self.assertFalse(ok)
        self.assertEqual(why, "receipt has an empty section: What now exists")

    def test_a_filled_receipt_over_the_stub_still_cannot_be_closed(self):
        folder = receipt.new_spike(self.path("spikes"), "idea", today="2026-01-05")
        write(str(folder / "RECEIPT.md"), FILLED)
        for code in (0, 1):
            ok, why = receipt.close_spike(folder, code, self.path("spikes", "index.json"), now=NOW)
            self.assertEqual((ok, why), (False, "verify.sh is still the stub"))

    def test_the_default_day_is_the_local_date(self):
        folder = receipt.new_spike(self.path("spikes"), "idea")
        today = datetime.date.today().isoformat()
        self.assertTrue(folder.name.startswith(today + "-01-"), folder.name)

    def test_numbering_continues_after_the_highest_number(self):
        os.makedirs(self.path("2026-01-05-01-a"))
        os.makedirs(self.path("2026-01-05-07-b"))
        self.assertEqual(receipt.new_spike(self.tmp, "c", today="2026-01-05", max_per_day=0).name,
                         "2026-01-05-08-c")

    def test_numbers_may_grow_past_two_digits(self):
        os.makedirs(self.path("2026-01-05-99-a"))
        self.assertEqual(receipt.new_spike(self.tmp, "c", today="2026-01-05", max_per_day=0).name,
                         "2026-01-05-100-c")

    def test_a_taken_name_is_never_reused(self):
        write(self.path("2026-01-05-01-x"), "a file that is not a folder")
        folder = receipt.new_spike(self.tmp, "x", today="2026-01-05", max_per_day=0)
        self.assertEqual(folder.name, "2026-01-05-02-x")
        with open(self.path("2026-01-05-01-x")) as handle:
            self.assertEqual(handle.read(), "a file that is not a folder")

    def test_a_name_taken_after_the_count_was_read_is_never_reused(self):
        first = receipt.new_spike(self.tmp, "x", today="2026-01-05", max_per_day=0)
        write(str(first / "RECEIPT.md"), "my work")
        with mock.patch.object(receipt, "_folder_numbers", return_value=[]):
            second = receipt.new_spike(self.tmp, "x", today="2026-01-05", max_per_day=0)
        self.assertEqual(second.name, "2026-01-05-02-x")
        self.assertEqual((first / "RECEIPT.md").read_text(), "my work")

    def test_a_folder_with_files_in_it_is_not_overwritten(self):
        first = receipt.new_spike(self.tmp, "x", today="2026-01-05", max_per_day=0)
        write(str(first / "RECEIPT.md"), "my work")
        receipt.new_spike(self.tmp, "x", today="2026-01-05", max_per_day=0)
        self.assertEqual((first / "RECEIPT.md").read_text(), "my work")

    def test_other_days_and_other_names_do_not_count_or_collide(self):
        os.makedirs(self.path("2026-01-04-01-a"))
        os.makedirs(self.path("2026-01-05-1-a"))
        write(self.path("2026-01-05-05-a"), "file, not a folder")
        os.makedirs(self.path("notes"))
        self.assertEqual(receipt.new_spike(self.tmp, "a", today="2026-01-05").name, "2026-01-05-01-a")

    def test_the_cap_stops_the_third_spike_of_a_day(self):
        receipt.new_spike(self.tmp, "a", today="2026-01-05")
        receipt.new_spike(self.tmp, "b", today="2026-01-05")
        with self.assertRaises(receipt.CapReached) as caught:
            receipt.new_spike(self.tmp, "c", today="2026-01-05")
        self.assertEqual(str(caught.exception), "2 spikes already started today (limit 2)")
        self.assertEqual(len(os.listdir(self.tmp)), 2)

    def test_the_cap_is_per_day(self):
        receipt.new_spike(self.tmp, "a", today="2026-01-05")
        receipt.new_spike(self.tmp, "b", today="2026-01-05")
        receipt.new_spike(self.tmp, "c", today="2026-01-06")

    def test_the_cap_limit_is_the_argument(self):
        receipt.new_spike(self.tmp, "a", today="2026-01-05", max_per_day=1)
        with self.assertRaises(receipt.CapReached) as caught:
            receipt.new_spike(self.tmp, "b", today="2026-01-05", max_per_day=1)
        self.assertEqual(str(caught.exception), "1 spikes already started today (limit 1)")
        receipt.new_spike(self.tmp, "b", today="2026-01-05", max_per_day=2)

    def test_a_cap_of_zero_turns_the_cap_off(self):
        for n in range(5):
            receipt.new_spike(self.tmp, "a%d" % n, today="2026-01-05", max_per_day=0)
        self.assertEqual(len(os.listdir(self.tmp)), 5)

    def test_a_title_with_a_line_break_stays_on_one_heading_line(self):
        folder = receipt.new_spike(self.tmp, "two\nlines  here", today="2026-01-05")
        self.assertEqual((folder / "RECEIPT.md").read_text().splitlines()[0], "# Receipt: two lines here")

    def test_parallel_starts_never_share_a_folder(self):
        code = ("import sys; sys.path.insert(0, %r); import time, receipt; "
                "time.sleep(max(0.0, float(sys.argv[2]) - time.time())); "
                "print(receipt.new_spike(sys.argv[1], 'same', today='2026-01-05', max_per_day=0))"
                % support.ROOT)
        start = __import__("time").time() + 1.0
        procs = [subprocess.Popen([sys.executable, "-c", code, self.tmp, str(start)],
                                  stdout=subprocess.PIPE, universal_newlines=True) for _ in range(8)]
        paths = [proc.communicate()[0].strip() for proc in procs]
        self.assertEqual(len(set(paths)), 8)
        self.assertEqual(len(os.listdir(self.tmp)), 8)


class ReceiptProblemTests(unittest.TestCase):
    def test_a_filled_receipt_has_no_problem(self):
        self.assertIsNone(receipt.receipt_problem(FILLED))

    def test_each_missing_section_is_named(self):
        for name in receipt.SECTIONS:
            text = FILLED.replace("## %s" % name, "## Something else")
            self.assertEqual(receipt.receipt_problem(text), "receipt is missing the section: %s" % name)

    def test_each_empty_section_is_named(self):
        for name in receipt.SECTIONS:
            text = FILLED.replace("## %s\n\nSomething true about it.\n" % name, "## %s\n\n" % name)
            self.assertEqual(receipt.receipt_problem(text), "receipt has an empty section: %s" % name)

    def test_the_first_failure_in_section_order_is_reported(self):
        text = FILLED.replace("## Next step", "## Elsewhere").replace(
            "## What it proved\n\nSomething true about it.\n", "## What it proved\n\n")
        self.assertEqual(receipt.receipt_problem(text), "receipt has an empty section: What it proved")

    def test_when_a_heading_appears_twice_the_first_one_counts(self):
        text = FILLED.replace("## Next step\n\nSomething true about it.\n",
                              "## Next step\n\n## Next step\nText under the second one\n")
        self.assertEqual(receipt.receipt_problem(text), "receipt has an empty section: Next step")
        text = FILLED.replace("## Next step\n\nSomething true about it.\n",
                              "## Next step\nText under the first one\n\n## Next step\n")
        self.assertIsNone(receipt.receipt_problem(text))

    def test_an_empty_text_is_missing_the_first_section(self):
        self.assertEqual(receipt.receipt_problem(""), "receipt is missing the section: What now exists")

    def test_headings_match_without_regard_to_case_or_spaces(self):
        text = FILLED.replace("## What now exists", "##   WHAT NOW EXISTS   ").replace(
            "## Next step", "## next step  ")
        self.assertIsNone(receipt.receipt_problem(text))

    def test_a_section_of_blank_lines_is_empty(self):
        text = FILLED.replace("## Next step\n\nSomething true about it.\n", "## Next step\n\n   \n\t\n")
        self.assertEqual(receipt.receipt_problem(text), "receipt has an empty section: Next step")

    def test_a_heading_of_any_level_ends_a_section(self):
        text = FILLED.replace("## How to run it\n\nSomething true about it.\n", "## How to run it\n\n### Detail\nSome text\n")
        self.assertEqual(receipt.receipt_problem(text), "receipt has an empty section: How to run it")
        text = FILLED.replace("## How to run it\n\nSomething true about it.\n", "## How to run it\n\n# Top\nSome text\n")
        self.assertEqual(receipt.receipt_problem(text), "receipt has an empty section: How to run it")

    def test_text_under_a_deeper_heading_does_not_fill_the_section_above(self):
        text = FILLED.replace("## What it proved\n\nSomething true about it.\n",
                              "## What it proved\n\n#### Notes\nonly under the notes\n")
        self.assertEqual(receipt.receipt_problem(text), "receipt has an empty section: What it proved")

    def test_a_level_3_heading_does_not_count_as_a_section(self):
        text = FILLED.replace("## Next step", "### Next step")
        self.assertEqual(receipt.receipt_problem(text), "receipt is missing the section: Next step")

    def test_a_hash_line_inside_a_code_fence_is_content_not_a_heading(self):
        text = FILLED.replace("## How to run it\n\nSomething true about it.\n",
                              "## How to run it\n\n```sh\n# run it\npython3 main.py\n```\n")
        self.assertIsNone(receipt.receipt_problem(text))
        only_fence = FILLED.replace("## How to run it\n\nSomething true about it.\n",
                                    "## How to run it\n\n```sh\n# run it\n```\n")
        self.assertIsNone(receipt.receipt_problem(only_fence))

    def test_a_section_heading_inside_a_code_fence_does_not_count_as_the_section(self):
        text = FILLED.replace("## What it proved\n\nSomething true about it.\n", "")
        text = text.replace("## How to run it\n\nSomething true about it.\n",
                            "## How to run it\n\n```md\n## What it proved\nText inside the fence.\n```\n")
        self.assertEqual(receipt.receipt_problem(text), "receipt is missing the section: What it proved")

    def test_windows_line_endings_are_accepted(self):
        self.assertIsNone(receipt.receipt_problem(FILLED.replace("\n", "\r\n")))


class CloseSpikeTests(TempCase):
    def make(self, receipt_text=FILLED, check=GOOD_CHECK, name="2026-01-05-01-x"):
        folder = self.path("spikes", name)
        os.makedirs(folder)
        if receipt_text is not None:
            write(os.path.join(folder, "RECEIPT.md"), receipt_text)
        if check is not None:
            write(os.path.join(folder, "verify.sh"), check)
        return folder

    def close(self, folder, code=0):
        return receipt.close_spike(folder, code, self.path("spikes", "index.json"), now=NOW)

    def rows(self):
        with open(self.path("spikes", "index.json")) as handle:
            return json.load(handle)

    def test_a_folder_that_does_not_exist_raises_and_records_nothing(self):
        with self.assertRaises(FileNotFoundError):
            self.close(self.path("spikes", "nothing-here"))
        self.assertFalse(os.path.exists(self.path("spikes", "index.json")))

    def test_a_file_is_not_a_spike_folder(self):
        write(self.path("a-file"), "x")
        with self.assertRaises(FileNotFoundError):
            self.close(self.path("a-file"))

    def test_no_receipt(self):
        self.assertEqual(self.close(self.make(receipt_text=None)), (False, "no receipt"))

    def test_an_unfilled_receipt(self):
        text = FILLED.replace("## Next step\n\nSomething true about it.\n", "## Next step\n\n")
        self.assertEqual(self.close(self.make(receipt_text=text)), (False, "receipt has an empty section: Next step"))

    def test_no_check_script(self):
        self.assertEqual(self.close(self.make(check=None)), (False, "no check script"))

    def test_an_empty_check_script(self):
        self.assertEqual(self.close(self.make(check="  \n\n")), (False, "no check script"))

    def test_the_stub_is_refused(self):
        stub = "#!/bin/sh\n# %s: replace me\nexit 1\n" % receipt.STUB_MARK
        self.assertEqual(self.close(self.make(check=stub)), (False, "verify.sh is still the stub"))

    def test_a_script_that_fails_the_screen_is_refused(self):
        folder = self.make(check="#!/bin/sh\nsudo make install\n")
        self.assertEqual(self.close(folder), (False, "verify.sh failed the screen: sudo"))

    def test_a_failing_check_is_refused(self):
        self.assertEqual(self.close(self.make(), 3), (False, "check failed (exit 3)"))

    def test_a_non_integer_exit_code_is_a_failure(self):
        for number, bad in enumerate((None, True, False, "0", 0.0)):
            ok, why = self.close(self.make(name="2026-01-05-%02d-y" % number), bad)
            self.assertFalse(ok, repr(bad))
            self.assertTrue(why.startswith("check failed"), why)

    def test_a_passing_check_closes(self):
        self.assertEqual(self.close(self.make()), (True, "receipt complete, check passed"))

    def test_the_checks_run_in_order(self):
        both_bad = FILLED.replace("## Next step\n\nSomething true about it.\n", "## Next step\n\n")
        self.assertEqual(self.close(self.make(receipt_text=None, check="sudo x"), 1), (False, "no receipt"))
        self.assertEqual(self.close(self.make(receipt_text=both_bad, check=None, name="b"), 1)[1],
                         "receipt has an empty section: Next step")
        stub_and_unsafe = "# %s\nsudo x\n" % receipt.STUB_MARK
        self.assertEqual(self.close(self.make(check=stub_and_unsafe, name="c"), 1),
                         (False, "verify.sh is still the stub"))
        self.assertEqual(self.close(self.make(check="sudo x", name="d"), 1),
                         (False, "verify.sh failed the screen: sudo"))

    def test_a_pass_is_recorded_with_every_field(self):
        folder = self.make()
        self.close(folder)
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {
            "idea": "Turn a text table into JSON",
            "dir": "2026-01-05-01-x",
            "date": local_date(NOW),
            "built_at": NOW,
            "verified": True,
            "verify_note": "receipt complete, check passed"})

    def test_a_failure_is_recorded_as_not_verified(self):
        self.close(self.make(), 2)
        row = self.rows()[0]
        self.assertIs(row["verified"], False)
        self.assertEqual(row["verify_note"], "check failed (exit 2)")

    def test_a_later_pass_replaces_the_row_for_the_same_folder(self):
        folder = self.make()
        self.close(folder, 2)
        self.close(folder, 0)
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]["verified"], True)

    def test_two_folders_get_two_rows(self):
        self.close(self.make(name="2026-01-05-01-a"))
        self.close(self.make(name="2026-01-05-02-b"))
        self.assertEqual(len(self.rows()), 2)

    def test_the_idea_is_cut_to_120_characters(self):
        text = FILLED.replace("# Receipt: Turn a text table into JSON", "# Receipt:    " + "w" * 200 + "   ")
        self.close(self.make(receipt_text=text))
        self.assertEqual(self.rows()[0]["idea"], "w" * 120)

    def test_the_idea_falls_back_to_the_folder_name(self):
        self.close(self.make(receipt_text=None))
        self.assertEqual(self.rows()[0]["idea"], "2026-01-05-01-x")
        self.close(self.make(receipt_text="no heading here\n", name="2026-01-05-02-y"))
        self.assertEqual(self.rows()[1]["idea"], "2026-01-05-02-y")
        self.close(self.make(receipt_text="# Receipt:   \n", name="2026-01-05-03-z"))
        self.assertEqual(self.rows()[2]["idea"], "2026-01-05-03-z")

    def test_close_never_runs_the_check_script(self):
        marker = self.path("ran-marker")
        folder = self.make(check="#!/bin/sh\ntouch %s\n" % marker)
        self.assertEqual(self.close(folder), (True, "receipt complete, check passed"))
        self.assertFalse(os.path.exists(marker))

    def test_the_default_time_is_now(self):
        folder = self.make()
        before = __import__("time").time()
        receipt.close_spike(folder, 0, self.path("spikes", "index.json"))
        after = __import__("time").time()
        self.assertTrue(before <= self.rows()[0]["built_at"] <= after)


if __name__ == "__main__":
    unittest.main()
