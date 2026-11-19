"""A pattern screen for check scripts.

A check script is the one place where a build's output turns into shell
commands, so it is read before anything runs it. This module only reads text.
It never runs a script, and a script that passes is not thereby safe.
"""
import re
from typing import Optional

UNSAFE = (
    # Reads rm when one option is recursive (a short flag containing r or R,
    # a cluster, or --recursive), with other options and -- allowed, then a
    # path starting with ~, /, .., $HOME or ${HOME}. A .. path counts when the
    # next character is /, a quote, a space or the end of the line.
    (r"\brm(?:\s+(?:-[A-Za-z]+|--[A-Za-z]+(?:-[A-Za-z]+)*|--))*"
     r"\s+(?:-[A-Za-z]*[rR][A-Za-z]*|--recursive)"
     r"(?:\s+(?:-[A-Za-z]+|--[A-Za-z]+(?:-[A-Za-z]+)*|--))*"
     r"\s+[\"']?(?:~|/|\.\.(?:/|[\"']|\s|$)|\$\{HOME\}|\$HOME)",
     "rm -rf on an absolute/home path"),
    (r"\bsudo\b", "sudo"),
    (r"(?m)(curl|wget)[^\n|]*\|\s*(?:ba|z|da|k)?sh\b"
     r"|(curl|wget)[^\n|]*\|\s*(?:\S*/)?(?:\benv\b(?:\s+(?:-\S+|\S*=\S*))*\s+)?"
     r"(?:(?:zsh|bash|dash|ksh|sh)\b(?=[\s;&)<>|]|$)"
     r"|(?:fish|perl|ruby|node|php|python(?:[23](?:\.\d+)?)?)\b"
     r"(?:\s+-\S+)*(?:(?=\s*(?:$|[;&)#<>|]|&&|\|\||\d+>))"
     r"|\s+(?:-|/dev/stdin)(?!\S)))"
     r"|\b(?:bash|zsh|dash|ksh|sh)\s+-c\s+[\"']\$\((?:curl|wget)"
     r"|\beval\s+[\"']?\$\(\s*(?:curl|wget)"
     r"|\b(?:bash|dash|ksh|sh|source)\s*<\(\s*(?:curl|wget)"
     r"|\.\s*<\(\s*(?:curl|wget)",
     "pipe-to-shell"),
    (r"\bgit\s+push\b", "git push"),
    (r"\b(shutdown|reboot|kill(all)?\s+-9|launchctl|systemctl)\b", "system control"),
    (r"\b(ssh|scp|rsync)\b", "remote access"),
    (r"\.ssh|\.env\b|1password|\bop\s+item\b|keychain", "secret material"),
    (r">\s*/(etc|usr|bin|var)/", "writes outside the workspace"),
    (r"\bcrontab\b|\bat\s+now\b", "schedules work"),
)


def unsafe_shell(script: str) -> Optional[str]:
    """Return the reason a check script must not be run, or None if it is clean.

    Patterns are tried in order, ignoring case, and the first match wins.
    """
    for pattern, reason in UNSAFE:
        if re.search(pattern, script, re.I):
            return reason
    return None
