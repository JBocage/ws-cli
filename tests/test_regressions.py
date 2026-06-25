"""Tests de régression issus de la revue adversariale."""
import json

import ws


def _write_ws(home, name, text):
    d = home / "workspaces"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.code-workspace").write_text(text)
    return d / f"{name}.code-workspace"


# --- JSONC : folders non-tableau -> pas de double clé, pas de perte -------- #
def test_add_when_folders_is_null(home, run, mkdirs):
    a, = mkdirs("a")
    _write_ws(home, "demo", '{\n  "folders": null,\n  "settings": {}\n}\n')
    code, out, err = run("add", "demo", a, "--force")
    assert code == 0
    text = (home / "workspaces" / "demo.code-workspace").read_text()
    assert text.count('"folders"') == 1  # PAS de seconde clé folders
    obj = json.loads(text)
    assert obj["folders"] == [{"path": a}]  # dossier réellement présent au reparse


def test_add_when_folders_is_object(home, run, mkdirs):
    a, = mkdirs("a")
    _write_ws(home, "demo", '{ "folders": {}, "settings": {} }')
    run("add", "demo", a, "--force")
    obj = ws.parse_jsonc((home / "workspaces" / "demo.code-workspace").read_text())
    assert obj["folders"] == [{"path": a}]


# --- Préservation des entrées sans path (groupes VSCode) ------------------- #
def test_add_preserves_pathless_group_entry(home, run, mkdirs):
    a, b = mkdirs("a", "b")
    _write_ws(
        home, "demo",
        '{\n  "folders": [\n    { "name": "Groupe" },\n'
        '    { "path": "%s" }\n  ]\n}\n' % a,
    )
    code, out, err = run("add", "demo", b)
    assert code == 0
    obj = ws.parse_jsonc((home / "workspaces" / "demo.code-workspace").read_text())
    assert {"name": "Groupe"} in obj["folders"]
    assert [e for e in obj["folders"] if e.get("path") == b]


def test_rm_folder_keeps_pathless_entry(home, run, mkdirs):
    a, = mkdirs("a")
    _write_ws(
        home, "demo",
        '{ "folders": [ { "name": "Groupe" }, { "path": "%s" } ] }' % a,
    )
    run("rm-folder", "demo", a)
    obj = ws.parse_jsonc((home / "workspaces" / "demo.code-workspace").read_text())
    assert obj["folders"] == [{"name": "Groupe"}]


# --- Chemins relatifs (fichier édité hors ws) ------------------------------ #
def test_rm_folder_relative_path(home, run):
    # le dossier 'sub' est relatif au .code-workspace
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
    _write_ws(home, "ext", '{ "folders": [ { "path": "~/projet-x" } ] }')
    code, out, err = run("show", "ext", "--json")
    data = json.loads(out)
    assert data["folders"][0].startswith(str(__import__("pathlib").Path.home()))


# --- Fichiers illisibles : pas de traceback ------------------------------- #
def test_list_skips_non_utf8_file(home, run, mkdirs):
    a, = mkdirs("a")
    run("new", "good", a)
    bad = home / "workspaces" / "bad.code-workspace"
    bad.write_bytes(b'{ "folders": [ {"path": "/caf\xe9"} ] }')  # latin-1, non UTF-8
    code, out, err = run("list", "--json")
    assert code == 0  # ne plante pas
    data = json.loads(out)
    names = {r["name"]: r for r in data}
    assert names["good"]["n_folders"] == 1
    assert names["bad"]["n_folders"] is None  # illisible, signalé proprement


def test_show_non_utf8_clean_error(home, run):
    bad = _write_ws(home, "bad", "")
    bad.write_bytes(b'{ "path": "/caf\xe9" }')
    code, out, err = run("show", "bad")
    assert code == ws.EXIT_ERROR
    assert "illisible" in err


# --- --force sur dossier manquant (add) ------------------------------------ #
def test_add_force_missing_dir(home, run, mkdirs, tmp_path):
    a, = mkdirs("a")
    run("new", "demo", a)
    missing = str(tmp_path / "nope")
    code, out, err = run("add", "demo", missing, "--force")
    assert code == 0
    obj = ws.parse_jsonc((home / "workspaces" / "demo.code-workspace").read_text())
    assert any(e.get("path") == missing for e in obj["folders"])


# --- Tags vides ignorés ---------------------------------------------------- #
def test_empty_tags_ignored(home, run, mkdirs):
    a, = mkdirs("a")
    run("new", "demo", a, "--tag", "", "--tag", "  ", "--tag", "ml")
    idx = json.loads((home / "index.json").read_text())
    assert idx["demo"]["tags"] == ["ml"]


# --- Nom à tiret initial refusé -------------------------------------------- #
def test_leading_dash_name_rejected(home, run, mkdirs):
    a, = mkdirs("a")
    code, out, err = run("new", "-bad", a)
    assert code == ws.EXIT_USAGE


# --- open : code retour non nul -> last_opened non mis à jour -------------- #
def test_open_failure_does_not_update_last_opened(home, run, mkdirs, monkeypatch):
    a, = mkdirs("a")
    run("new", "demo", a)

    class FakeProc:
        returncode = 3

    monkeypatch.setattr(ws.subprocess, "run", lambda *x, **k: FakeProc())
    code, out, err = run("open", "demo")
    assert code == 3  # propage l'échec de `code`
    idx = json.loads((home / "index.json").read_text())
    assert "last_opened" not in idx["demo"]


# --- edit : invoque l'éditeur ; EDITOR mal formé -> erreur propre ---------- #
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
    assert calls[-1][:2] == ["code", "-r"]  # ne tente PAS d'exécuter le fichier


# --- open -n -r mutuellement exclusifs ------------------------------------- #
def test_open_n_and_r_mutually_exclusive(home, run, mkdirs, monkeypatch):
    a, = mkdirs("a")
    run("new", "demo", a)
    monkeypatch.setattr(ws.subprocess, "run", lambda *x, **k: type("P", (), {"returncode": 0})())
    code, out, err = run("open", "demo", "-n", "-r")
    assert code == ws.EXIT_USAGE


# --- index corrompu : restauration depuis .bak ----------------------------- #
def test_corrupt_index_restored_from_backup(home, run, mkdirs):
    a, = mkdirs("a")
    run("new", "demo", a, "--desc", "v1")       # crée index.json
    run("set", "demo", "--desc", "v2")          # crée index.json.bak (= v1)
    (home / "index.json").write_text("{ corrompu ")
    code, out, err = run("show", "demo", "--json")
    assert code == 0  # restauré depuis le backup, pas de plantage
    data = json.loads(out)
    assert data["description"] in ("v1", "v2")  # métadonnées récupérées


# --- open sans workspace --------------------------------------------------- #
def test_open_no_workspace(home, run, monkeypatch):
    monkeypatch.setattr(ws.shutil, "which", lambda _x: None)  # fzf absent
    code, out, err = run("open")
    assert code == ws.EXIT_ERROR
    assert "aucun workspace" in err


# --- clé folders dupliquée : édite la dernière, pas de perte --------------- #
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
    # json.loads retient la dernière clé ; le dossier ajouté doit y être présent
    paths = [e["path"] for e in obj["folders"]]
    assert a in paths  # PAS de perte silencieuse
    assert "clé 'folders' présente 2 fois" in err  # averti


# --- fichier avec BOM UTF-8 (écrit par VSCode) lisible --------------------- #
def test_bom_file_is_readable(home, run, mkdirs):
    a, = mkdirs("a")
    bom = home / "workspaces" / "bom.code-workspace"
    bom.parent.mkdir(parents=True, exist_ok=True)
    bom.write_bytes('﻿{ "folders": [ {"path": "/x"} ] }'.encode("utf-8"))
    code, out, err = run("show", "bom", "--json")
    assert code == 0
    assert json.loads(out)["folders"] == ["/x"]
    # et on peut l'éditer sans planter
    code, out, err = run("add", "bom", a)
    assert code == 0


# --- verrou réentrant : pas d'interblocage --------------------------------- #
def test_index_lock_reentrant(home):
    with ws.index_lock():
        with ws.index_lock():  # imbrication dans le même process : ne doit pas bloquer
            assert ws._lock_depth == 2
    assert ws._lock_depth == 0
    assert ws._lock_fd is None


# --- completion install : pose le fichier dans bash-completion ------------- #
def test_completion_install(home, run, monkeypatch, tmp_path):
    data = tmp_path / "xdgdata"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    code, out, err = run("completion", "install")
    assert code == 0
    dest = data / "bash-completion" / "completions" / "ws"
    assert dest.is_file()
    assert "complete -F _ws ws" in dest.read_text()


# --- couleur : WS_COLOR=always active, NO_COLOR neutralise, JSON jamais ----- #
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


# --- astuce d'autocomplétion : une fois, en TTY seulement ------------------- #
def test_completion_hint_shown_once_on_tty(home, monkeypatch):
    import io

    class FakeTTY(io.StringIO):
        def isatty(self):
            return True

    fake = FakeTTY()
    monkeypatch.setattr(ws.sys, "stderr", fake)
    monkeypatch.delenv("NO_COLOR", raising=False)
    ws._maybe_hint_completion("list")   # 1er appel → affiché
    ws._maybe_hint_completion("list")   # 2e appel → silencieux (marqueur posé)
    assert fake.getvalue().count("ws completion install") == 1


def test_completion_hint_silent_for_completion_command(home, monkeypatch):
    import io

    class FakeTTY(io.StringIO):
        def isatty(self):
            return True

    fake = FakeTTY()
    monkeypatch.setattr(ws.sys, "stderr", fake)
    ws._maybe_hint_completion("completion")  # ne nag pas quand on gère la complétion
    assert fake.getvalue() == ""


def test_completion_hint_silent_when_not_tty(home, run, mkdirs):
    a, = mkdirs("a")
    code, out, err = run("new", "demo", a)  # capsys = non-TTY
    assert "completion install" not in err
