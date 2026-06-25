"""new / add / rm-folder / set / rename / delete / path / list / show."""
import json

import ws


def _index(home):
    return json.loads((home / "index.json").read_text())


def test_new_creates_file_and_index(home, run, mkdirs):
    (a,) = mkdirs("a")
    code, out, err = run("new", "proj", a, "--desc", "my desc", "--tag", "x", "--tag", "y")
    assert code == 0
    wsfile = home / "workspaces" / "proj.code-workspace"
    assert wsfile.is_file()
    obj = json.loads(wsfile.read_text())
    assert obj["folders"] == [{"path": a}]
    idx = _index(home)
    assert idx["proj"]["description"] == "my desc"
    assert idx["proj"]["tags"] == ["x", "y"]
    assert "created" in idx["proj"]


def test_new_invalid_name(home, run, mkdirs):
    (a,) = mkdirs("a")
    code, out, err = run("new", "bad name!", a)
    assert code == ws.EXIT_USAGE


def test_new_duplicate(home, run, mkdirs):
    (a,) = mkdirs("a")
    run("new", "proj", a)
    code, out, err = run("new", "proj", a)
    assert code == ws.EXIT_EXISTS
    assert "add" in err


def test_new_missing_dir_blocks_without_force(home, run, tmp_path):
    missing = str(tmp_path / "nope")
    code, out, err = run("new", "proj", missing)
    assert code == ws.EXIT_ERROR
    assert not (home / "workspaces" / "proj.code-workspace").exists()


def test_new_missing_dir_with_force(home, run, tmp_path):
    missing = str(tmp_path / "nope")
    code, out, err = run("new", "proj", missing, "--force")
    assert code == 0
    assert (home / "workspaces" / "proj.code-workspace").is_file()


def test_new_dedup_and_resolve(home, run, mkdirs, monkeypatch):
    (a,) = mkdirs("a")
    monkeypatch.setenv("MYVAR", a)
    code, out, err = run("new", "proj", a, "$MYVAR", a)
    assert code == 0
    obj = json.loads((home / "workspaces" / "proj.code-workspace").read_text())
    assert obj["folders"] == [{"path": a}]


def test_add_dedup(home, run, mkdirs):
    a, b = mkdirs("a", "b")
    run("new", "proj", a)
    run("add", "proj", b, a)  # a already present
    obj = json.loads((home / "workspaces" / "proj.code-workspace").read_text())
    assert [f["path"] for f in obj["folders"]] == [a, b]


def test_rm_folder(home, run, mkdirs):
    a, b = mkdirs("a", "b")
    run("new", "proj", a, b)
    code, out, err = run("rm-folder", "proj", a)
    assert code == 0
    obj = json.loads((home / "workspaces" / "proj.code-workspace").read_text())
    assert [f["path"] for f in obj["folders"]] == [b]


def test_set_metadata(home, run, mkdirs):
    (a,) = mkdirs("a")
    run("new", "proj", a)
    run("set", "proj", "--desc", "new one", "--add-tag", "ml", "--add-tag", "infra")
    run("set", "proj", "--rm-tag", "ml")
    idx = _index(home)
    assert idx["proj"]["description"] == "new one"
    assert idx["proj"]["tags"] == ["infra"]


def test_rename(home, run, mkdirs):
    (a,) = mkdirs("a")
    run("new", "old", a, "--tag", "t")
    code, out, err = run("rename", "old", "new")
    assert code == 0
    assert not (home / "workspaces" / "old.code-workspace").exists()
    assert (home / "workspaces" / "new.code-workspace").is_file()
    idx = _index(home)
    assert "old" not in idx
    assert idx["new"]["tags"] == ["t"]


def test_rename_collision(home, run, mkdirs):
    a, b = mkdirs("a", "b")
    run("new", "p1", a)
    run("new", "p2", b)
    code, out, err = run("rename", "p1", "p2")
    assert code == ws.EXIT_EXISTS


def test_delete_with_yes(home, run, mkdirs):
    (a,) = mkdirs("a")
    run("new", "proj", a)
    code, out, err = run("delete", "proj", "-y")
    assert code == 0
    assert not (home / "workspaces" / "proj.code-workspace").exists()
    assert "proj" not in _index(home)


def test_delete_not_found(home, run):
    code, out, err = run("delete", "ghost", "-y")
    assert code == ws.EXIT_NOT_FOUND


def test_path(home, run, mkdirs):
    (a,) = mkdirs("a")
    run("new", "proj", a)
    code, out, err = run("path", "proj")
    assert code == 0
    assert out.strip() == str(home / "workspaces" / "proj.code-workspace")


def test_list_and_json(home, run, mkdirs):
    a, b = mkdirs("a", "b")
    run("new", "alpha", a, "--tag", "x", "--desc", "A")
    run("new", "beta", a, b, "--tag", "y")
    code, out, err = run("list", "--json")
    assert code == 0
    data = json.loads(out)
    names = {r["name"]: r for r in data}
    assert names["alpha"]["n_folders"] == 1
    assert names["beta"]["n_folders"] == 2
    assert names["alpha"]["tags"] == ["x"]


def test_list_filter_tag(home, run, mkdirs):
    (a,) = mkdirs("a")
    run("new", "alpha", a, "--tag", "x")
    run("new", "beta", a, "--tag", "y")
    code, out, err = run("list", "--tag", "x", "--json")
    data = json.loads(out)
    assert [r["name"] for r in data] == ["alpha"]


def test_show_json(home, run, mkdirs):
    (a,) = mkdirs("a")
    run("new", "proj", a, "--desc", "D")
    code, out, err = run("show", "proj", "--json")
    assert code == 0
    data = json.loads(out)
    assert data["name"] == "proj"
    assert data["folders"] == [a]
    assert data["description"] == "D"


def test_show_not_found(home, run):
    code, out, err = run("show", "ghost")
    assert code == ws.EXIT_NOT_FOUND
