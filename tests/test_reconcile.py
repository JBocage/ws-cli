"""File ↔ index reconciliation: drift, orphans, purge, external file."""
import json

import ws


def _write_ws(home, name, text):
    d = home / "workspaces"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.code-workspace").write_text(text)


def test_file_without_index_entry_shows_empty_meta(home, run, mkdirs):
    # workspace created "outside ws" (e.g. Save Workspace As), with no index entry
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
    # inject an orphan entry (no matching file)
    idx_path = home / "index.json"
    idx = json.loads(idx_path.read_text())
    idx["ghost"] = {"description": "phantom", "tags": ["z"]}
    idx_path.write_text(json.dumps(idx))
    code, out, err = run("list", "--json")
    data = json.loads(out)
    assert {r["name"] for r in data} == {"real"}


def test_orphan_preserved_not_destroyed(home, run, mkdirs):
    # Data safety: an UNRELATED write must NOT destroy the metadata
    # of an entry whose file is (temporarily) absent.
    (a,) = mkdirs("a")
    run("new", "real", a)
    idx_path = home / "index.json"
    idx = json.loads(idx_path.read_text())
    idx["ghost"] = {"tags": ["z"], "description": "to preserve"}
    idx_path.write_text(json.dumps(idx))
    run("set", "real", "--desc", "x")
    idx = json.loads(idx_path.read_text())
    assert idx["ghost"] == {"tags": ["z"], "description": "to preserve"}
    assert idx["real"]["description"] == "x"
    # ... but the orphan stays invisible in the display
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
        '{\n  // comment\n  "folders": [ {"path": "/a"}, ],\n}\n',
    )
    code, out, err = run("list", "--json")
    assert code == 0
    data = json.loads(out)
    assert next(r for r in data if r["name"] == "withcomments")["n_folders"] == 1
