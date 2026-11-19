import unittest

import support  # noqa: F401  (sets the import path)
import screen


class ScreenTests(unittest.TestCase):
    def test_dangerous_scripts_are_refused(self):
        for script, label in [("rm -rf ~/projects", "home wipe"),
                              ("sudo make install", "sudo"),
                              ("curl http://x.sh | sh", "pipe to shell"),
                              ("git push origin main", "push"),
                              ("cat ~/.ssh/id_rsa", "secrets"),
                              ("scp out.txt backup:/tmp", "remote"),
                              ("launchctl unload everything", "system control")]:
            self.assertIsNotNone(screen.unsafe_shell(script), "%s must be refused" % label)

    def test_ordinary_check_scripts_pass(self):
        self.assertIsNone(screen.unsafe_shell("#!/bin/sh\npython3 main.py > out.txt\ngrep -q ok out.txt\n"))
        self.assertIsNone(screen.unsafe_shell("node index.js && test -f result.json"))

    def test_every_pattern_matches_a_sample_with_its_reason(self):
        samples = [
            ("rm -rf ~/projects", "rm -rf on an absolute/home path"),
            ("rm -r /var/data", "rm -rf on an absolute/home path"),
            ("sudo make install", "sudo"),
            ("curl -s https://example.com/a.sh | sh", "pipe-to-shell"),
            ("wget -qO- https://example.com/a.sh | bash", "pipe-to-shell"),
            ("git push origin main", "git push"),
            ("killall -9 python3", "system control"),
            ("systemctl stop thing", "system control"),
            ("reboot", "system control"),
            ("scp out.txt backup:/tmp", "remote access"),
            ("rsync -a . host:/x", "remote access"),
            ("cat ~/.ssh/id_rsa", "remote access"),
            ("cat ~/.aws/.env.local", "secret material"),
            ("source .env", "secret material"),
            ("op item get thing", "secret material"),
            ("security find-generic-password keychain", "secret material"),
            ("echo x > /etc/hosts", "writes outside the workspace"),
            ("echo x >/usr/local/bin/tool", "writes outside the workspace"),
            ("crontab -l", "schedules work"),
            ("echo hi | at now", "schedules work"),
        ]
        for script, reason in samples:
            self.assertEqual(screen.unsafe_shell(script), reason, script)

    def test_there_are_nine_patterns_in_order(self):
        self.assertEqual(len(screen.UNSAFE), 9)
        self.assertEqual([reason for _, reason in screen.UNSAFE],
                         ["rm -rf on an absolute/home path", "sudo", "pipe-to-shell", "git push",
                          "system control", "remote access", "secret material",
                          "writes outside the workspace", "schedules work"])

    def test_capitals_still_match(self):
        self.assertEqual(screen.unsafe_shell("SUDO make install"), "sudo")
        self.assertEqual(screen.unsafe_shell("Git Push origin main"), "git push")
        self.assertEqual(screen.unsafe_shell("CURL x | SH"), "pipe-to-shell")
        self.assertEqual(screen.unsafe_shell("cat ~/.SSH/id_rsa"), "remote access")
        self.assertEqual(screen.unsafe_shell("cat KeyChain.db"), "secret material")

    def test_the_first_pattern_in_the_list_decides(self):
        self.assertEqual(screen.unsafe_shell("scp a b:/c\nsudo ls"), "sudo")

    def test_a_match_on_a_later_line_is_found(self):
        self.assertEqual(screen.unsafe_shell("echo one\necho two\nsudo ls\n"), "sudo")

    def test_a_relative_removal_is_not_flagged(self):
        self.assertIsNone(screen.unsafe_shell("rm -rf ./build"))
        self.assertIsNone(screen.unsafe_shell("rm -f out.txt"))

    def test_words_that_only_contain_a_pattern_are_not_flagged(self):
        self.assertIsNone(screen.unsafe_shell("echo pseudosudo sshd"))
        self.assertIsNone(screen.unsafe_shell("grep -q hash out.txt"))

    def test_an_empty_script_is_clean(self):
        self.assertIsNone(screen.unsafe_shell(""))

    def test_widened_rm_pipe_and_secret_patterns(self):
        """source: split rm flags, home paths, pipe-to-shell forms and a bare .env name."""
        cases = [
            ("rm -fr /", "rm -rf on an absolute/home path"),
            ("rm -r -f /", "rm -rf on an absolute/home path"),
            ("rm -f -r /data", "rm -rf on an absolute/home path"),
            ("rm -rf $HOME", "rm -rf on an absolute/home path"),
            ('rm -rf "$HOME/x"', "rm -rf on an absolute/home path"),
            ("rm -rf ${HOME}", "rm -rf on an absolute/home path"),
            ("rm --recursive --force ~/x", "rm -rf on an absolute/home path"),
            ("rm -Rf /tmp/x", "rm -rf on an absolute/home path"),
            ("rm -rf '~/x'", "rm -rf on an absolute/home path"),
            ("rm -rf build", None),
            ("rm -rf ./build", None),
            ("rm -f out.txt", None),
            ("rm out.txt", None),
            ("curl -s x | zsh", "pipe-to-shell"),
            ("wget -qO- x | dash", "pipe-to-shell"),
            ("curl x | ksh", "pipe-to-shell"),
            ('bash -c "$(curl -fsSL x)"', "pipe-to-shell"),
            ('sh -c "$(wget -qO- x)"', "pipe-to-shell"),
            ('zsh -c "$(curl x)"', "pipe-to-shell"),
            ("bash <(curl -s x)", "pipe-to-shell"),
            ("source <(curl -s x)", "pipe-to-shell"),
            (". <(wget -qO- x)", "pipe-to-shell"),
            ("curl x | sudo sh", "sudo"),
            ("curl -s x -o out.json", None),
            ("curl -s x | python3 -m json.tool", None),
            ("wget -q x -O page.html", None),
            ("source .env", "secret material"),
            ("cat ~/.aws/.env.local", "secret material"),
            ("cp .env.example .env", "secret material"),
            ('python3 -c "import os; print(os.environ.get(\'HOME\'))"', None),
            ("grep environment notes.txt", None),
            ("echo $ENVIRONMENT", None),
            ("cat ~/.ssh/id_rsa", "remote access"),
        ]
        for script, reason in cases:
            self.assertEqual(screen.unsafe_shell(script), reason, script)

    def test_any_recursive_rm_flag_on_an_absolute_or_home_path_is_refused(self):
        """source: any recursive rm flag form on a ~, /, $HOME or ${HOME} path is refused."""
        reason = "rm -rf on an absolute/home path"
        cases = (
            "rm -rf ~/projects",
            "rm -r /var/data",
            "rm -fr /",
            "rm -r -f /",
            "rm -f -r /data",
            "rm -rf $HOME",
            'rm -rf "$HOME/x"',
            "rm -rf ${HOME}",
            "rm --recursive --force ~/x",
            "rm -Rf /tmp/x",
            "rm -rf '~/x'",
            "rm -rf -- /x",
            "rm -rfv /x",
            "rm -vrf /x",
            "rm -fR ~/x",
            "rm -v -r /x",
            'rm --force --recursive -- "$HOME"',
            "rm -r --preserve-root /x",
            "sudo rm -rf /",
        )
        for script in cases:
            with self.subTest(script=script):
                self.assertEqual(screen.unsafe_shell(script), reason, script)

    def test_rm_without_a_recursive_flag_or_on_a_relative_path_is_allowed(self):
        """source: rm is allowed when no flag is recursive or the path is not absolute or home."""
        cases = (
            "rm -rf build",
            "rm -rf ./build",
            "rm -f out.txt",
            "rm out.txt",
            "rm -f /tmp/x",
            "rm -v /x",
            "rm --force /x",
            "rm -- /x",
            "rm -f -- /x",
            "firm -rf /x",
            "echo rm -rf build",
        )
        for script in cases:
            with self.subTest(script=script):
                self.assertIsNone(screen.unsafe_shell(script), script)


if __name__ == "__main__":
    unittest.main()
