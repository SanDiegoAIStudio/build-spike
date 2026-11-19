import json
import os
import unittest

import support
from support import TempCase, write
import count


class LoadRowsTests(TempCase):
    def test_json_lines(self):
        path = write(self.path("a.jsonl"), '{"kind": "a"}\n\n{"kind": "b"}\n')
        self.assertEqual(count.load_rows(path), [{"kind": "a"}, {"kind": "b"}])

    def test_json_list(self):
        path = write(self.path("a.json"), '  [{"kind": "a"}, {"kind": "b"}]')
        self.assertEqual(count.load_rows(path), [{"kind": "a"}, {"kind": "b"}])

    def test_a_multi_line_json_list(self):
        path = write(self.path("a.json"), '[\n  {"kind": "a"},\n  {"kind": "b"}\n]\n')
        self.assertEqual(len(count.load_rows(path)), 2)

    def test_a_byte_order_mark_is_ignored(self):
        path = self.path("bom.jsonl")
        with open(path, "wb") as handle:
            handle.write(b'\xef\xbb\xbf{"kind": "a"}\n')
        self.assertEqual(count.load_rows(path), [{"kind": "a"}])

    def test_an_empty_file_has_no_rows(self):
        self.assertEqual(count.load_rows(write(self.path("e.jsonl"), "")), [])
        self.assertEqual(count.load_rows(write(self.path("e2.jsonl"), "\n\n  \n")), [])

    def test_a_bad_line_names_its_line_number(self):
        path = write(self.path("a.jsonl"), '{"kind": "a"}\n\nnot json\n{"kind": "b"}\n')
        with self.assertRaises(ValueError) as caught:
            count.load_rows(path)
        self.assertEqual(str(caught.exception), "line 3 is not valid JSON")

    def test_a_line_that_is_not_an_object_names_its_line_number(self):
        path = write(self.path("a.jsonl"), '{"kind": "a"}\n[1, 2]\n')
        with self.assertRaises(ValueError) as caught:
            count.load_rows(path)
        self.assertEqual(str(caught.exception), "line 2 is not a JSON object")

    def test_a_list_item_that_is_not_an_object_names_its_position(self):
        path = write(self.path("a.json"), '[{"kind": "a"}, 7]')
        with self.assertRaises(ValueError) as caught:
            count.load_rows(path)
        self.assertEqual(str(caught.exception), "item 2 is not a JSON object")

    def test_a_broken_list_is_a_value_error(self):
        path = write(self.path("a.json"), '[{"kind": "a"},')
        with self.assertRaises(ValueError) as caught:
            count.load_rows(path)
        self.assertTrue(str(caught.exception).startswith("not valid JSON"))

    def test_a_missing_file_raises_os_error(self):
        with self.assertRaises(OSError):
            count.load_rows(self.path("nothing.jsonl"))


class CountKindsTests(unittest.TestCase):
    ROWS = [{"kind": "a"}, {"kind": "a"}, {"kind": "b"}, {"other": 1}, {"kind": None}]

    def test_counts_by_key_with_a_missing_bucket(self):
        self.assertEqual(count.count_kinds(self.ROWS, "kind"), {"a": 2, "b": 1, "(missing)": 2})

    def test_a_dotted_key_reaches_into_nested_objects(self):
        rows = [{"meta": {"kind": "x"}}, {"meta": {"kind": "x"}}, {"meta": {}}, {"meta": "text"}, {"meta": None}]
        self.assertEqual(count.count_kinds(rows, "meta.kind"), {"x": 2, "(missing)": 3})

    def test_a_dotted_key_does_not_match_a_flat_key_with_a_dot(self):
        self.assertEqual(count.count_kinds([{"a.b": "x"}], "a.b"), {"(missing)": 1})

    def test_values_that_are_not_text_are_counted_by_their_json_text(self):
        rows = [{"k": 1}, {"k": 1}, {"k": True}, {"k": 1.5}, {"k": [1, 2]}, {"k": {"a": 1}}, {"k": ""}]
        self.assertEqual(count.count_kinds(rows, "k"),
                         {"1": 2, "true": 1, "1.5": 1, "[1, 2]": 1, '{"a": 1}': 1, "": 1})

    def test_no_rows_gives_no_counts(self):
        self.assertEqual(count.count_kinds([], "kind"), {})

    def test_the_total_equals_the_number_of_rows(self):
        self.assertEqual(sum(count.count_kinds(self.ROWS, "kind").values()), len(self.ROWS))


class TodoShareTests(unittest.TestCase):
    def test_share_of_the_named_kinds(self):
        self.assertEqual(count.todo_share({"a": 3, "b": 1}, ["a"]), 0.75)
        self.assertEqual(count.todo_share({"a": 3, "b": 1}, ["a", "b"]), 1.0)

    def test_a_kind_named_twice_counts_once(self):
        self.assertEqual(count.todo_share({"a": 3, "b": 1}, ["a", "a"]), 0.75)

    def test_a_kind_that_never_occurs_adds_nothing(self):
        self.assertEqual(count.todo_share({"a": 3, "b": 1}, ["zzz"]), 0.0)

    def test_no_rows_is_zero_not_an_error(self):
        self.assertEqual(count.todo_share({}, ["a"]), 0.0)

    def test_the_missing_bucket_can_be_named(self):
        self.assertEqual(count.todo_share({"(missing)": 1, "a": 1}, ["(missing)"]), 0.5)


class ExampleDataTests(unittest.TestCase):
    def test_the_bundled_rows_match_the_documented_counts(self):
        rows = count.load_rows(os.path.join(support.EXAMPLES, "actions.jsonl"))
        self.assertEqual(len(rows), 175)
        counts = count.count_kinds(rows, "kind")
        self.assertEqual(counts["backlog_entry"], 127)
        self.assertEqual(round(100 * count.todo_share(counts, ["backlog_entry"]), 1), 72.6)
        self.assertEqual(sum(count.count_kinds(rows, "night").values()), 175)
        self.assertEqual(len(count.count_kinds(rows, "night")), 24)
        verdicts = count.count_kinds(rows, "verdict")
        self.assertEqual((verdicts["SEED"], verdicts["SHELVE"], verdicts["ACT"], verdicts["KILL"]),
                         (106, 64, 3, 2))


if __name__ == "__main__":
    unittest.main()
