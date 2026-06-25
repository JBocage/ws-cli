"""Completion: valid bash script + names/tags outputs."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import ws

WS_PY = str(Path(__file__).resolve().parent.parent / "ws.py")


def test_bash_completion_is_valid_syntax(run):
    code, out, err = run("completion", "bash")
    assert code == 0
    assert "complete -F _ws ws" in out
    bash = shutil.which("bash")
    if not bash:
        return  # no bash → we just check the content
    proc = subprocess.run([bash, "-n"], input=out, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr


def test_completion_names(home, run, mkdirs):
    (a,) = mkdirs("a")
    run("new", "alpha", a)
    run("new", "beta", a)
    code, out, err = run("completion", "names")
    assert code == 0
    assert out.split() == ["alpha", "beta"]


def test_completion_tags(home, run, mkdirs):
    (a,) = mkdirs("a")
    run("new", "alpha", a, "--tag", "ml", "--tag", "infra")
    run("new", "beta", a, "--tag", "ml")
    code, out, err = run("completion", "tags")
    assert code == 0
    assert out.split() == ["infra", "ml"]


def test_cli_exit_codes_via_subprocess(home, tmp_path):
    env = dict(os.environ, WS_HOME=str(home))
    env.pop("XDG_CONFIG_HOME", None)
    # workspace not found → 3
    r = subprocess.run([sys.executable, WS_PY, "show", "ghost"], env=env, capture_output=True)
    assert r.returncode == ws.EXIT_NOT_FOUND
