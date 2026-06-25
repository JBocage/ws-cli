"""Réconciliation fichier ↔ index : drift, orphelins, purge, fichier externe."""
import json

import ws


def _write_ws(home, name, text):
    d = home / "workspaces"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.code-workspace").write_text(text)


def test_file_without_index_entry_shows_empty_meta(home, run, mkdirs):
    # workspace créé « hors ws » (genre Save Workspace As), sans entrée d'index
    _write_ws(home, "external", '{\n  "folders": [ {"path": "/x"} ]\n}\n')
    code, out, err = run("list", "--json")
    data = json.loads(out)
    row = next(r for r in data if r["name"] == "external")
    assert row["tags"] == []
    assert row["description"] == ""
    assert row["n_folders"] == 1


def test_orphan_index_entry_ignored_in_list(home, run, mkdirs):
    (a,) = mkdirs("a")
    run("new", "real", a)
    # injecte une entrée orpheline (aucun fichier correspondant)
    idx_path = home / "index.json"
    idx = json.loads(idx_path.read_text())
    idx["ghost"] = {"description": "fantôme", "tags": ["z"]}
    idx_path.write_text(json.dumps(idx))
    code, out, err = run("list", "--json")
    data = json.loads(out)
    assert {r["name"] for r in data} == {"real"}


def test_orphan_preserved_not_destroyed(home, run, mkdirs):
    # Sécurité des données : une écriture SANS RAPPORT ne doit PAS détruire les
    # métadonnées d'une entrée dont le fichier est (temporairement) absent.
    (a,) = mkdirs("a")
    run("new", "real", a)
    idx_path = home / "index.json"
    idx = json.loads(idx_path.read_text())
    idx["ghost"] = {"tags": ["z"], "description": "à préserver"}
    idx_path.write_text(json.dumps(idx))
    run("set", "real", "--desc", "x")
    idx = json.loads(idx_path.read_text())
    assert idx["ghost"] == {"tags": ["z"], "description": "à préserver"}
    assert idx["real"]["description"] == "x"
    # ... mais l'orphelin reste invisible à l'affichage
    code, out, err = run("list", "--json")
    assert {r["name"] for r in json.loads(out)} == {"real"}


def test_corrupt_index_raises(home, run, mkdirs):
    (a,) = mkdirs("a")
    run("new", "real", a)
    (home / "index.json").write_text("{ not json ")
    code, out, err = run("list")
    assert code == ws.EXIT_ERROR
    assert "index.json" in err


def test_jsonc_file_listed_without_crash(home, run):
    _write_ws(
        home, "withcomments",
        '{\n  // commentaire\n  "folders": [ {"path": "/a"}, ],\n}\n',
    )
    code, out, err = run("list", "--json")
    assert code == 0
    data = json.loads(out)
    assert next(r for r in data if r["name"] == "withcomments")["n_folders"] == 1
