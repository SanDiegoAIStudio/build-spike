import io
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

import support
from support import TempCase, write
import index

BUILT = 1_700_000_000.0


def read_rows(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class RecordTests(TempCase):
    def setUp(self):
        super().setUp()
        self.index = self.path("spikes", "index.json")

    def test_record_appends(self):
        index.record(self.index, {"idea": "a", "dir": "x", "built_at": BUILT})
        index.record(self.index, {"idea": "b", "dir": "y", "built_at": BUILT})
        self.assertEqual([row["idea"] for row in read_rows(self.index)], ["a", "b"])

    def test_the_folder_for_the_index_is_created(self):
        index.record(self.path("deep", "er", "index.json"), {"idea": "a"})
        self.assertTrue(os.path.isfile(self.path("deep", "er", "index.json")))

    def test_a_row_with_no_folder_is_appended_every_time(self):
        index.record(self.index, {"idea": "a"})
        index.record(self.index, {"idea": "a"})
        index.record(self.index, {"idea": "b", "dir": ""})
        index.record(self.index, {"idea": "c", "dir": "   "})
        index.record(self.index, {"idea": "d", "dir": None})
        self.assertEqual(len(read_rows(self.index)), 5)

    def test_dirless_record_survives_and_has_the_fate_no_dir(self):
        index.record(self.index, {"idea": "no folder", "built_at": BUILT, "verified": True})
        rows = index.fates(self.index)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fate"], "no-dir")
        self.assertEqual(rows[0]["idea"], "no folder")

    def test_recording_the_same_folder_again_replaces_its_row(self):
        os.makedirs(self.path("spikes", "one"))
        index.record(self.index, {"idea": "first", "dir": self.path("spikes", "one"), "verified": False})
        index.record(self.index, {"idea": "second", "dir": self.path("spikes", "one"), "verified": True})
        rows = read_rows(self.index)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["idea"], "second")

    def test_replacement_keeps_the_position_of_the_row(self):
        for name in ("a", "b", "c"):
            os.makedirs(self.path("spikes", name))
            index.record(self.index, {"idea": name, "dir": self.path("spikes", name)})
        index.record(self.index, {"idea": "b2", "dir": self.path("spikes", "b")})
        self.assertEqual([row["idea"] for row in read_rows(self.index)], ["a", "b2", "c"])

    def test_the_same_folder_written_two_ways_is_one_row(self):
        os.makedirs(self.path("spikes", "one"))
        index.record(self.index, {"idea": "a", "dir": self.path("spikes", "one")})
        index.record(self.index, {"idea": "b", "dir": self.path("spikes", "sub", "..", "one")})
        self.assertEqual(len(read_rows(self.index)), 1)

    def test_a_spike_inside_the_root_is_stored_relative(self):
        os.makedirs(self.path("spikes", "one"))
        index.record(self.index, {"idea": "a", "dir": self.path("spikes", "one")})
        self.assertEqual(read_rows(self.index)[0]["dir"], "one")

    def test_a_spike_outside_the_root_is_stored_absolute(self):
        outside = self.path("elsewhere", "one")
        os.makedirs(outside)
        index.record(self.index, {"idea": "a", "dir": outside})
        stored = read_rows(self.index)[0]["dir"]
        self.assertTrue(os.path.isabs(stored))
        self.assertEqual(os.path.realpath(stored), os.path.realpath(outside))

    def test_a_relative_dir_in_the_entry_is_resolved_from_the_current_folder(self):
        os.makedirs(self.path("spikes", "one"))
        before = os.getcwd()
        os.chdir(self.path("spikes"))
        try:
            index.record(self.index, {"idea": "a", "dir": "one"})
        finally:
            os.chdir(before)
        self.assertEqual(read_rows(self.index)[0]["dir"], "one")

    def test_a_relative_row_is_still_found_after_the_root_is_renamed(self):
        os.makedirs(self.path("spikes", "one"))
        index.record(self.index, {"idea": "a", "dir": self.path("spikes", "one"), "built_at": BUILT})
        os.rename(self.path("spikes"), self.path("moved"))
        rows = index.fates(self.path("moved", "index.json"))
        self.assertEqual(rows[0]["fate"], "untouched")

    def test_an_entry_that_is_not_a_dict_is_refused(self):
        with self.assertRaises(TypeError):
            index.record(self.index, ["not", "a", "dict"])
        self.assertFalse(os.path.exists(self.index))

    def test_the_callers_entry_is_not_changed(self):
        os.makedirs(self.path("spikes", "one"))
        entry = {"idea": "a", "dir": self.path("spikes", "one")}
        index.record(self.index, entry)
        self.assertEqual(entry["dir"], self.path("spikes", "one"))

    def test_the_written_file_is_a_json_list_ending_in_a_newline(self):
        index.record(self.index, {"idea": "a"})
        with open(self.index, encoding="utf-8") as handle:
            text = handle.read()
        self.assertTrue(text.endswith("\n"))
        self.assertIsInstance(json.loads(text), list)

    def test_no_temporary_files_are_left_behind(self):
        for n in range(3):
            index.record(self.index, {"idea": str(n)})
        self.assertEqual(sorted(os.listdir(self.path("spikes"))), ["index.json", "index.json.lock"])

    def test_text_outside_ascii_is_kept(self):
        idea = "caf\u00e9 \u4e2d\u6587"
        index.record(self.index, {"idea": idea})
        self.assertEqual(read_rows(self.index)[0]["idea"], idea)

    def test_record_syncs_the_temporary_file_before_the_rename(self):
        """source: record fsyncs the temporary file while that file still exists."""
        seen = []
        real_fsync = index.os.fsync

        def recording_fsync(fd):
            temps = [name for name in os.listdir(self.path("spikes")) if name.endswith(".tmp")]
            seen.append((fd, temps))
            return real_fsync(fd)

        with mock.patch("index.os.fsync", side_effect=recording_fsync):
            index.record(self.index, {"idea": "synced"})
        self.assertTrue(any(temps for _, temps in seen), seen)
        self.assertEqual(read_rows(self.index)[0]["idea"], "synced")


class DamagedIndexTests(TempCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("sys.stderr", io.StringIO())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.index = self.path("spikes", "index.json")

    def test_corrupt_index_returns_empty(self):
        write(self.index, "{ this is not json")
        self.assertEqual(index.fates(self.index), [])

    def test_a_missing_index_returns_empty(self):
        self.assertEqual(index.fates(self.index), [])

    def test_an_index_that_is_not_a_list_returns_empty(self):
        write(self.index, '{"rows": []}')
        self.assertEqual(index.fates(self.index), [])

    def test_a_damaged_index_is_renamed_aside_and_the_new_row_is_written(self):
        write(self.index, "{ this is not json")
        index.record(self.index, {"idea": "kept"})
        names = sorted(os.listdir(self.path("spikes")))
        asides = [name for name in names if name.startswith("index.json.corrupt-")]
        self.assertEqual(len(asides), 1, names)
        with open(self.path("spikes", asides[0])) as handle:
            self.assertEqual(handle.read(), "{ this is not json")
        self.assertEqual([row["idea"] for row in read_rows(self.index)], ["kept"])

    def test_an_index_that_is_valid_json_but_not_a_list_is_also_moved_aside(self):
        write(self.index, '{"rows": [1, 2]}')
        index.record(self.index, {"idea": "kept"})
        asides = [n for n in os.listdir(self.path("spikes")) if n.startswith("index.json.corrupt-")]
        self.assertEqual(len(asides), 1)
        self.assertEqual(len(read_rows(self.index)), 1)

    def test_two_damaged_files_in_one_second_keep_separate_names(self):
        for text in ("first damage", "second damage"):
            write(self.index, text)
            index.record(self.index, {"idea": "x"})
        asides = sorted(n for n in os.listdir(self.path("spikes")) if n.startswith("index.json.corrupt-"))
        self.assertEqual(len(asides), 2)
        contents = set()
        for name in asides:
            with open(self.path("spikes", name)) as handle:
                contents.add(handle.read())
        self.assertEqual(contents, {"first damage", "second damage"})

    def test_a_warning_goes_to_stderr(self):
        write(self.index, "damaged")
        code = ("import sys; sys.path.insert(0, %r); import index; index.record(sys.argv[1], {'idea': 'x'})"
                % support.ROOT)
        run = subprocess.run([sys.executable, "-c", code, self.index], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, universal_newlines=True,
                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("warning", run.stderr)
        self.assertIn("index.json.corrupt-", run.stderr)
        self.assertEqual(run.stdout, "")


class AtomicWriteTests(TempCase):
    def test_it_writes_the_text(self):
        index.atomic_write(self.path("f.txt"), "hello")
        with open(self.path("f.txt")) as handle:
            self.assertEqual(handle.read(), "hello")

    def test_it_replaces_an_existing_file(self):
        write(self.path("f.txt"), "old")
        index.atomic_write(self.path("f.txt"), "new")
        with open(self.path("f.txt")) as handle:
            self.assertEqual(handle.read(), "new")

    def test_a_failed_write_keeps_the_old_file_and_leaves_no_temporary(self):
        write(self.path("f.txt"), "old")
        with self.assertRaises(TypeError):
            index.atomic_write(self.path("f.txt"), 12345)
        with open(self.path("f.txt")) as handle:
            self.assertEqual(handle.read(), "old")
        self.assertEqual(os.listdir(self.tmp), ["f.txt"])

    def test_a_failed_rename_removes_the_temporary(self):
        os.makedirs(self.path("target"))
        write(self.path("target", "inner"), "x")
        with self.assertRaises(OSError):
            index.atomic_write(self.path("target"), "text")
        self.assertEqual(os.listdir(self.tmp), ["target"])


class ConcurrencyTests(TempCase):
    WRITERS = 8
    ROWS = 25

    def test_parallel_writers_lose_no_rows(self):
        target = self.path("spikes", "index.json")
        code = ("import sys, time; sys.path.insert(0, %r); import index\n"
                "path, name, start, rows = sys.argv[1], sys.argv[2], float(sys.argv[3]), int(sys.argv[4])\n"
                "time.sleep(max(0.0, start - time.time()))\n"
                "for n in range(rows):\n"
                "    index.record(path, {'idea': '%%s-%%d' %% (name, n), 'pad': 'x' * 6000})\n"
                % support.ROOT)
        start = time.time() + 1.0
        procs = [subprocess.Popen([sys.executable, "-c", code, target, "w%d" % w, str(start), str(self.ROWS)],
                                  stderr=subprocess.PIPE, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
                 for w in range(self.WRITERS)]
        errors = [proc.communicate()[1] for proc in procs]
        self.assertEqual([proc.returncode for proc in procs], [0] * self.WRITERS, errors)
        ideas = [row["idea"] for row in read_rows(target)]
        expected = {"w%d-%d" % (w, n) for w in range(self.WRITERS) for n in range(self.ROWS)}
        self.assertEqual(len(ideas), self.WRITERS * self.ROWS)
        self.assertEqual(set(ideas), expected)


class FateTests(TempCase):
    def setUp(self):
        super().setUp()
        self.index = self.path("spikes", "index.json")

    def make(self, name, built_at=BUILT, files=("a.txt",), mtime=None):
        folder = self.path("spikes", name)
        os.makedirs(folder, exist_ok=True)
        for file_name in files:
            target = write(os.path.join(folder, file_name), "x")
            os.utime(target, (mtime if mtime is not None else built_at,) * 2)
        index.record(self.index, {"idea": name, "dir": folder, "built_at": built_at})
        return folder

    def fate(self, **kwargs):
        rows = index.fates(self.index, **kwargs)
        self.assertEqual(len(rows), 1)
        return rows[0]["fate"]

    def test_fates_deleted_and_untouched(self):
        self.make("kept")
        self.make("gone")
        os.rename(self.path("spikes", "gone"), self.path("elsewhere"))
        by_idea = {row["idea"]: row["fate"] for row in index.fates(self.index)}
        self.assertEqual(by_idea, {"kept": "untouched", "gone": "deleted"})

    def test_later_edit_marks_touched(self):
        folder = self.make("edited")
        os.utime(os.path.join(folder, "a.txt"), (BUILT + 4000, BUILT + 4000))
        self.assertEqual(self.fate(), "touched")

    def test_an_edit_inside_the_grace_period_does_not_count(self):
        self.make("quick", mtime=BUILT + 299)
        self.assertEqual(self.fate(), "untouched")

    def test_an_edit_exactly_at_the_end_of_the_grace_period_does_not_count(self):
        self.make("edge", mtime=BUILT + 300)
        self.assertEqual(self.fate(), "untouched")

    def test_an_edit_just_after_the_grace_period_counts(self):
        self.make("edge", mtime=BUILT + 301)
        self.assertEqual(self.fate(), "touched")

    def test_the_grace_period_can_be_changed(self):
        self.make("g", mtime=BUILT + 100)
        self.assertEqual(self.fate(grace_seconds=50), "touched")
        self.assertEqual(self.fate(grace_seconds=200), "untouched")

    def test_a_file_in_a_nested_folder_counts(self):
        folder = self.make("nested")
        os.makedirs(os.path.join(folder, "sub", "deeper"))
        deep = write(os.path.join(folder, "sub", "deeper", "late.txt"), "x")
        os.utime(deep, (BUILT + 9000, BUILT + 9000))
        self.assertEqual(self.fate(), "touched")

    def test_the_newest_file_is_what_counts(self):
        folder = self.make("two", files=("old.txt", "new.txt"))
        os.utime(os.path.join(folder, "new.txt"), (BUILT + 9000, BUILT + 9000))
        os.utime(os.path.join(folder, "old.txt"), (BUILT, BUILT))
        self.assertEqual(self.fate(), "touched")

    def test_an_empty_folder_is_untouched(self):
        self.make("empty", files=())
        self.assertEqual(self.fate(), "untouched")

    def test_an_index_row_may_point_at_a_single_file(self):
        target = write(self.path("spikes", "loose.txt"), "x")
        os.utime(target, (BUILT + 9000, BUILT + 9000))
        index.record(self.index, {"idea": "file", "dir": target, "built_at": BUILT})
        self.assertEqual(self.fate(), "touched")

    def test_a_row_with_no_built_at_counts_from_zero(self):
        folder = self.path("spikes", "old")
        os.makedirs(folder)
        write(os.path.join(folder, "a.txt"), "x")
        os.utime(os.path.join(folder, "a.txt"), (100, 100))
        index.record(self.index, {"idea": "old", "dir": folder})
        self.assertEqual(self.fate(), "untouched")

    def test_a_built_at_that_is_not_a_number_counts_as_zero(self):
        folder = self.make("odd", built_at=BUILT, mtime=BUILT)
        write(self.index, json.dumps([{"idea": "odd", "dir": "odd", "built_at": "soon"}]))
        self.assertEqual(self.fate(), "touched")
        self.assertTrue(os.path.isdir(folder))

    def test_the_stored_rows_are_not_changed_by_reading_fates(self):
        self.make("kept")
        with open(self.index) as handle:
            before = handle.read()
        index.fates(self.index)
        with open(self.index) as handle:
            self.assertEqual(handle.read(), before)

    def test_rows_that_are_not_objects_are_skipped(self):
        self.make("kept")
        rows = read_rows(self.index)
        write(self.index, json.dumps(["text", 5, None] + rows))
        self.assertEqual([row["idea"] for row in index.fates(self.index)], ["kept"])

    def test_every_other_field_comes_through(self):
        self.make("kept")
        row = index.fates(self.index)[0]
        self.assertEqual(row["built_at"], BUILT)
        self.assertEqual(row["dir"], "kept")


class SummaryTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(index.summary([]), "0 spike(s) recorded, verified 0 (0%)")

    def test_counts_and_percent(self):
        rows = [{"verified": True, "fate": "touched"}, {"verified": False, "fate": "untouched"},
                {"verified": True, "fate": "touched"}, {"verified": True, "fate": "deleted"}]
        self.assertEqual(index.summary(rows),
                         "4 spike(s) recorded, verified 3 (75%), deleted 1, touched 2, untouched 1")

    def test_only_a_true_value_counts_as_verified(self):
        rows = [{"verified": "yes", "fate": "untouched"}, {"verified": 1, "fate": "untouched"},
                {"fate": "untouched"}, {"verified": None, "fate": "untouched"}]
        self.assertEqual(index.summary(rows), "4 spike(s) recorded, verified 0 (0%), untouched 4")

    def test_percent_is_rounded_to_a_whole_number(self):
        rows = [{"verified": True, "fate": "a"}, {"verified": False, "fate": "a"}, {"verified": False, "fate": "a"}]
        self.assertIn("verified 1 (33%)", index.summary(rows))


if __name__ == "__main__":
    unittest.main()
