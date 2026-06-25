"""Regression tests from the adversarial review."""
import json

import ws


def _write_ws(home, name, text):
    d = home / "workspaces"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.code-workspace").write_text(text)
    return d / f"{name}.code-workspace"


# --- JSONC: non-array folders -> no double key, no loss --------------------- #
def test_add_when_folders_is_null(home, run, mkdirs):
    a, = mkdirs("a")
    _write_ws(home, "demo", '{\n  "folders": null,\n  "settings": {}\n}\n')
    code, out, err = run("add", "demo", a, "--force")
    assert code == 0
    text = (home / "workspaces" / "demo.code-workspace").read_text()
    assert text.count('"folders"') == 1  # NO second folders key
    obj = json.loads(text)
    assert obj["folders"] == [{"path": a}]  # folder actually present after reparse


def test_add_when_folders_is_object(home, run, mkdirs):
    a, = mkdirs("a")
    _write_ws(home, "demo", '{ "folders": {}, "settings": {} }')
    run("add", "demo", a, "--force")
    obj = ws.parse_jsonc((home / "workspaces" / "demo.code-workspace").read_text())
    assert obj["folders"] == [{"path": a}]


# --- Preservation of pathless entries (VSCode groups) ---------------------- #
def test_add_preserves_pathless_group_entry(home, run, mkdirs):
    a, b = mkdirs("a", "b")
    _write_ws(
        home, "demo",
        '{\n  "folders": [\n    { "name": "Group" },\n'
        '    { "path": "%s" }\n  ]\n}\n' % a,
    )
    code, out, err = run("add", "demo", b)
    assert code == 0
    obj = ws.parse_jsonc((home / "workspaces" / "demo.code-workspace").read_text())
    assert {"name": "Group"} in obj["folders"]
    assert [e for e in obj["folders"] if e.get("path") == b]


def test_rm_folder_keeps_pathless_entry(home, run, mkdirs):
    a, = mkdirs("a")
    _write_ws(
        home, "demo",
        '{ "folders": [ { "name": "Group" }, { "path": "%s" } ] }' % a,
    )
    run("rm-folder", "demo", a)
    obj = ws.parse_jsonc((home / "workspaces" / "demo.code-workspace").read_text())
    assert obj["folders"] == [{"name": "Group"}]


# --- Relative paths (file edited outside ws) ------------------------------- #
def test_rm_folder_relative_path(home, run):
    # the 'sub' folder is relative to the .code-workspace
    wsdir = home / "workspaces"
    wsdir.mkdir(parents=True, exist_ok=True)
    (wsdir / "sub").mkdir()
    _write_ws(home, "ext", '{ "folders": [ { "path": "./sub" } ] }')
    target = str((wsdir / "sub"))
    code, out, err = run("rm-folder", "ext", target)
    assert code == 0
    obj = ws.parse_jsonc((wsdir / "ext.code-workspace").read_text())
    assert obj["folders"] == []


def test_show_resolves_tilde(home, run, monkeypatch):
    _write_ws(home, "ext", '{ "folders": [ { "path": "~/project-x" } ] }')
    code, out, err = run("show", "ext", "--json")
    data = json.loads(out)
    assert data["folders"][0].startswith(str(__import__("pathlib").Path.home()))


# --- Unreadable files: no traceback ---------------------------------------- #
def test_list_skips_non_utf8_file(home, run, mkdirs):
    a, = mkdirs("a")
    run("new", "good", a)
    bad = home / "workspaces" / "bad.code-workspace"
    bad.write_bytes(b'{ "folders": [ {"path": "/caf\xe9"} ] }')  # latin-1, not UTF-8
    code, out, err = run("list", "--json")
    assert code == 0  # does not crash
    data = json.loads(out)
    names = {r["name"]: r for r in data}
    assert names["good"]["n_folders"] == 1
    assert names["bad"]["n_folders"] is None  # unreadable, reported cleanly


def test_show_non_utf8_clean_error(home, run):
    bad = _write_ws(home, "bad", "")
    bad.write_bytes(b'{ "path": "/caf\xe9" }')
    code, out, err = run("show", "bad")
    assert code == ws.EXIT_ERROR
    assert "unreadable" in err


# --- --force on missing folder (add) --------------------------------------- #
def test_add_force_missing_dir(home, run, mkdirs, tmp_path):
    a, = mkdirs("a")
    run("new", "demo", a)
    missing = str(tmp_path / "nope")
    code, out, err = run("add", "demo", missing, "--force")
    assert code == 0
    obj = ws.parse_jsonc((home / "workspaces" / "demo.code-workspace").read_text())
    assert any(e.get("path") == missing for e in obj["folders"])


# --- Empty tags ignored ---------------------------------------------------- #
def test_empty_tags_ignored(home, run, mkdirs):
    a, = mkdirs("a")
    run("new", "demo", a, "--tag", "", "--tag", "  ", "--tag", "ml")
    idx = json.loads((home / "index.json").read_text())
    assert idx["demo"]["tags"] == ["ml"]


# --- Leading-dash name rejected -------------------------------------------- #
def test_leading_dash_name_rejected(home, run, mkdirs):
    a, = mkdirs("a")
    code, out, err = run("new", "-bad", a)
    assert code == ws.EXIT_USAGE


# --- open: non-zero return code -> last_opened not updated ------------------ #
def test_open_failure_does_not_update_last_opened(home, run, mkdirs, monkeypatch):
    a, = mkdirs("a")
    run("new", "demo", a)

    class FakeProc:
        returncode = 3

    monkeypatch.setattr(ws.subprocess, "run", lambda *x, **k: FakeProc())
    code, out, err = run("open", "demo")
    assert code == 3  # propagates the failure of `code`
    idx = json.loads((home / "index.json").read_text())
    assert "last_opened" not in idx["demo"]


# --- edit: invokes the editor; malformed EDITOR -> clean error ------------- #
def test_edit_invokes_editor(home, run, mkdirs, monkeypatch):
    a, = mkdirs("a")
    run("new", "demo", a)
    calls = []
    monkeypatch.setattr(ws.subprocess, "run",
                        lambda cmd, *x, **k: calls.append(cmd) or type("P", (), {"returncode": 0})())
    monkeypatch.setenv("EDITOR", "myeditor --flag")
    code, out, err = run("edit", "demo")
    assert code == 0
    assert calls[-1][:2] == ["myeditor", "--flag"]
    assert calls[-1][-1].endswith("demo.code-workspace")


def test_edit_unbalanced_quote_clean_error(home, run, mkdirs, monkeypatch):
    a, = mkdirs("a")
    run("new", "demo", a)
    monkeypatch.setenv("EDITOR", 'vim "')
    code, out, err = run("edit", "demo")
    assert code == ws.EXIT_USAGE


def test_edit_blank_editor_falls_back(home, run, mkdirs, monkeypatch):
    a, = mkdirs("a")
    run("new", "demo", a)
    calls = []
    monkeypatch.setattr(ws.subprocess, "run",
                        lambda cmd, *x, **k: calls.append(cmd) or type("P", (), {"returncode": 0})())
    monkeypatch.setenv("EDITOR", "   ")
    run("edit", "demo")
    assert calls[-1][:2] == ["code", "-r"]  # does NOT try to execute the file


# --- open -n -r mutually exclusive ----------------------------------------- #
def test_open_n_and_r_mutually_exclusive(home, run, mkdirs, monkeypatch):
    a, = mkdirs("a")
    run("new", "demo", a)
    monkeypatch.setattr(ws.subprocess, "run", lambda *x, **k: type("P", (), {"returncode": 0})())
    code, out, err = run("open", "demo", "-n", "-r")
    assert code == ws.EXIT_USAGE


# --- corrupt index: restored from .bak ------------------------------------- #
def test_corrupt_index_restored_from_backup(home, run, mkdirs):
    a, = mkdirs("a")
    run("new", "demo", a, "--desc", "v1")       # creates index.json
    run("set", "demo", "--desc", "v2")          # creates index.json.bak (= v1)
    (home / "index.json").write_text("{ corrupt ")
    code, out, err = run("show", "demo", "--json")
    assert code == 0  # restored from the backup, no crash
    data = json.loads(out)
    assert data["description"] in ("v1", "v2")  # metadata recovered


# --- open with no workspace ------------------------------------------------ #
def test_open_no_workspace(home, run, monkeypatch):
    monkeypatch.setattr(ws.shutil, "which", lambda _x: None)  # fzf absent
    code, out, err = run("open")
    assert code == ws.EXIT_ERROR
    assert "no workspace" in err


# --- duplicate folders key: edits the last one, no loss -------------------- #
def test_add_with_duplicate_folders_key(home, run, mkdirs):
    a, = mkdirs("a")
    _write_ws(
        home, "dup",
        '{\n  "folders": [{"path": "/one"}],\n'
        '  "folders": [{"path": "/two"}],\n  "settings": {}\n}\n',
    )
    code, out, err = run("add", "dup", a)
    assert code == 0
    obj = ws.parse_jsonc((home / "workspaces" / "dup.code-workspace").read_text())
    # json.loads keeps the last key; the added folder must be present in it
    paths = [e["path"] for e in obj["folders"]]
    assert a in paths  # NO silent loss
    assert "'folders' key present 2 times" in err  # warned


# --- file with UTF-8 BOM (written by VSCode) is readable ------------------- #
def test_bom_file_is_readable(home, run, mkdirs):
    a, = mkdirs("a")
    bom = home / "workspaces" / "bom.code-workspace"
    bom.parent.mkdir(parents=True, exist_ok=True)
    bom.write_bytes('﻿{ "folders": [ {"path": "/x"} ] }'.encode("utf-8"))
    code, out, err = run("show", "bom", "--json")
    assert code == 0
    assert json.loads(out)["folders"] == ["/x"]
    # and we can edit it without crashing
    code, out, err = run("add", "bom", a)
    assert code == 0


# --- reentrant lock: no deadlock ------------------------------------------- #
def test_index_lock_reentrant(home):
    with ws.index_lock():
        with ws.index_lock():  # nesting in the same process: must not block
            assert ws._lock_depth == 2
    assert ws._lock_depth == 0
    assert ws._lock_fd is None


# --- completion install: places the file in bash-completion ---------------- #
def test_completion_install(home, run, monkeypatch, tmp_path):
    data = tmp_path / "xdgdata"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    code, out, err = run("completion", "install")
    assert code == 0
    dest = data / "bash-completion" / "completions" / "ws"
    assert dest.is_file()
    assert "complete -F _ws ws" in dest.read_text()


# --- color: WS_COLOR=always enables, NO_COLOR neutralizes, JSON never ------- #
def test_list_color_forced(home, run, mkdirs, monkeypatch):
    a, = mkdirs("a")
    run("new", "demo", a, "--tag", "ml")
    monkeypatch.setenv("WS_COLOR", "always")
    code, out, err = run("list")
    assert "\033[" in out


def test_no_color_overrides_ws_color(home, run, mkdirs, monkeypatch):
    a, = mkdirs("a")
    run("new", "demo", a)
    monkeypatch.setenv("WS_COLOR", "always")
    monkeypatch.setenv("NO_COLOR", "1")
    code, out, err = run("list")
    assert "\033[" not in out


def test_json_never_colored(home, run, mkdirs, monkeypatch):
    a, = mkdirs("a")
    run("new", "demo", a, "--tag", "ml")
    monkeypatch.setenv("WS_COLOR", "always")
    _, out_list, _ = run("list", "--json")
    _, out_show, _ = run("show", "demo", "--json")
    assert "\033[" not in out_list
    assert "\033[" not in out_show


# --- no autocompletion nag at runtime -------------------------------------- #
def test_no_completion_nag_on_normal_command(home, run, mkdirs):
    a, = mkdirs("a")
    code, out, err = run("new", "demo", a)
    assert "completion install" not in err
    assert "completion install" not in out
    code, out, err = run("list")
    assert "completion install" not in err and "completion install" not in out


# --- ws uninstall: removes the install, keeps the config (non-tty) --------- #
def test_uninstall_removes_artifacts_keeps_config(home, run, mkdirs):
    run("completion", "install")                 # places the completion (isolated XDG_DATA_HOME)
    comp = ws.completion_install_path()
    assert comp.exists()
    lib = ws.lib_dir()                           # simulates the remote install artifact
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "ws.py").write_text("# fake ws.py\n")
    link = ws.bin_dir() / "ws"                   # simulates the install symlink
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(lib / "ws.py")
    a, = mkdirs("a")
    run("new", "demo", a)
    assert ws.ws_home().is_dir()

    code, out, err = run("uninstall")            # non-tty → keeps the config
    assert code == 0
    assert not link.exists()
    assert not lib.exists()
    assert not comp.exists()
    assert ws.ws_home().is_dir()                 # data preserved


def test_uninstall_purge_removes_config(home, run, mkdirs):
    a, = mkdirs("a")
    run("new", "demo", a)
    code, out, err = run("uninstall", "--purge")
    assert code == 0
    assert not ws.ws_home().exists()


def test_uninstall_detects_uv_install(home, run, monkeypatch):
    fake = "/home/u/.local/share/uv/tools/ws-vscode/lib/python3.12/site-packages/ws.py"
    monkeypatch.setattr(ws, "__file__", fake)
    code, out, err = run("uninstall")
    assert code == 0
    assert "uv tool uninstall ws-vscode" in out
