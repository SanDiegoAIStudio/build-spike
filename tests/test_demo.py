import os
import subprocess
import unittest

import support
from support import TempCase

DEMO = os.path.join(support.EXAMPLES, "demo.sh")


def snapshot(root):
    found = []
    for folder, names, files in os.walk(root):
        names[:] = [n for n in names if n not in (".git", "__pycache__")]
        for name in files:
            full = os.path.join(folder, name)
            found.append((os.path.relpath(full, root), os.path.getsize(full), os.path.getmtime(full)))
    return sorted(found)


class DemoTests(TempCase):
    def run_demo(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR=self.tmp)
        env.pop("SPIKE_ROOT", None)
        return subprocess.run(["bash", DEMO], cwd=self.tmp, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True, timeout=120)

    def test_the_demo_runs_every_command_and_leaves_nothing_behind(self):
        before = snapshot(support.ROOT)
        run = self.run_demo()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        for word in ("BUILD:", "ASK:", "OK", "UNSAFE:", "FAILED:", "BUILT:", "to-do share:",
                     "spike(s) recorded", "demo finished"):
            self.assertIn(word, run.stdout)
        self.assertEqual(snapshot(support.ROOT), before)
        self.assertEqual(os.listdir(self.tmp), [], "the demo left files in its temporary folder")

    def test_the_demo_stops_when_a_step_gives_the_wrong_exit_code(self):
        broken = self.path("kit")
        os.makedirs(os.path.join(broken, "examples"))
        for name in os.listdir(support.EXAMPLES):
            source = os.path.join(support.EXAMPLES, name)
            if os.path.isfile(source):
                with open(source, "rb") as src, open(os.path.join(broken, "examples", name), "wb") as dst:
                    dst.write(src.read())
        for name in ("gate.py", "screen.py", "index.py", "receipt.py", "count.py", "spike.py"):
            with open(os.path.join(support.ROOT, name), "rb") as src, open(os.path.join(broken, name), "wb") as dst:
                dst.write(src.read())
        with open(os.path.join(broken, "examples", "plan-build.json"), "w") as handle:
            handle.write('{"cheapness": 1, "stakes": "low", "action": "x"}')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR=self.tmp)
        run = subprocess.run(["bash", os.path.join(broken, "examples", "demo.sh")], cwd=self.tmp, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=120)
        self.assertEqual(run.returncode, 1)
        self.assertIn("expected exit 0, got 1", run.stderr)

    def test_the_demo_screens_the_sample_check_before_running_it(self):
        """source: the demo screens the copied verify.sh and prints OK before its exit code."""
        run = self.run_demo()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        heading = "== fill the folder with the sample spike, screen its check, then run it"
        self.assertIn(heading, run.stdout)
        after = run.stdout.split(heading, 1)[1]
        ok_at = after.find("OK")
        verify_at = after.find("verify.sh exit code:")
        self.assertGreater(ok_at, -1, run.stdout)
        self.assertGreater(verify_at, ok_at, run.stdout)


class ExampleFileTests(unittest.TestCase):
    def test_the_sample_spike_is_complete(self):
        import receipt
        folder = os.path.join(support.EXAMPLES, "sample-spike")
        with open(os.path.join(folder, "RECEIPT.md"), encoding="utf-8") as handle:
            self.assertIsNone(receipt.receipt_problem(handle.read()))
        with open(os.path.join(folder, "verify.sh"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn(receipt.STUB_MARK, text)
        import screen
        self.assertIsNone(screen.unsafe_shell(text))

    def test_the_bad_example_is_caught_and_the_good_one_is_not(self):
        import screen
        with open(os.path.join(support.EXAMPLES, "verify-bad.sh"), encoding="utf-8") as handle:
            self.assertIsNotNone(screen.unsafe_shell(handle.read()))
        with open(os.path.join(support.EXAMPLES, "verify-good.sh"), encoding="utf-8") as handle:
            self.assertIsNone(screen.unsafe_shell(handle.read()))


if __name__ == "__main__":
    unittest.main()
