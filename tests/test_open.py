"""`open` : argv passé à `code`, flags -n/-r, mise à jour de last_opened."""
import json

import ws


class FakeProc:
    returncode = 0


def _patch_code(monkeypatch):
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)
        return FakeProc()

    monkeypatch.setattr(ws.subprocess, "run", fake_run)
    return calls


def test_open_invokes_code_and_updates_last_opened(home, run, mkdirs, monkeypatch):
    (a,) = mkdirs("a")
    run("new", "proj", a)
    calls = _patch_code(monkeypatch)
    code, out, err = run("open", "proj")
    assert code == 0
    assert calls[-1][0] == "code"
    assert calls[-1][-1] == str(home / "workspaces" / "proj.code-workspace")
    idx = json.loads((home / "index.json").read_text())
    assert "last_opened" in idx["proj"]


def test_open_new_window_flag(home, run, mkdirs, monkeypatch):
    (a,) = mkdirs("a")
    run("new", "proj", a)
    calls = _patch_code(monkeypatch)
    run("open", "proj", "-n")
    assert "-n" in calls[-1]


def test_open_reuse_flag(home, run, mkdirs, monkeypatch):
    (a,) = mkdirs("a")
    run("new", "proj", a)
    calls = _patch_code(monkeypatch)
    run("open", "proj", "-r")
    assert "-r" in calls[-1]


def test_open_not_found(home, run, monkeypatch):
    _patch_code(monkeypatch)
    code, out, err = run("open", "ghost")
    assert code == ws.EXIT_NOT_FOUND


def test_open_external_file_creates_index_entry(home, run, monkeypatch):
    d = home / "workspaces"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ext.code-workspace").write_text('{ "folders": [] }')
    _patch_code(monkeypatch)
    code, out, err = run("open", "ext")
    assert code == 0
    idx = json.loads((home / "index.json").read_text())
    assert "last_opened" in idx["ext"]
