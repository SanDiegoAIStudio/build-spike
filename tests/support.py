"""Shared helpers for the tests: import path, temporary folders and a command-line runner."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SPIKE = os.path.join(ROOT, "spike.py")
EXAMPLES = os.path.join(ROOT, "examples")


class TempCase(unittest.TestCase):
    """A test case with a fresh temporary folder in self.tmp, removed afterwards."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="spike-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)


class CliCase(TempCase):
    """A test case that runs spike.py as a subprocess from inside self.tmp."""

    def cli(self, *args, stdin=None, env=None, drop_root_env=True):
        full_env = dict(os.environ)
        if drop_root_env:
            full_env.pop("SPIKE_ROOT", None)
        full_env["PYTHONDONTWRITEBYTECODE"] = "1"
        if env:
            full_env.update(env)
        return subprocess.run([sys.executable, SPIKE] + list(args), cwd=self.tmp, env=full_env,
                              input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=60)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path
