"""Cœur JSONC : lecture tolérante + édition chirurgicale de `folders`."""
import json

import ws


def test_strip_jsonc_keeps_strings_with_slashes():
    src = '{"url": "http://x//y", "k": 1} // trailing\n'
    cleaned = ws.strip_jsonc(src)
    assert "http://x//y" in cleaned
    assert "// trailing" not in cleaned


def test_strip_jsonc_block_comment_in_string():
    src = '{"a": "/* not a comment */", /* real */ "b": 2}'
    obj = ws.parse_jsonc(ws.strip_jsonc(src))
    assert obj == {"a": "/* not a comment */", "b": 2}


def test_parse_jsonc_trailing_comma():
    src = '{\n "folders": [ {"path": "/a"}, {"path": "/b"}, ],\n}'
    obj = ws.parse_jsonc(src)
    assert obj["folders"] == [{"path": "/a"}, {"path": "/b"}]


def test_parse_jsonc_comma_inside_string_preserved():
    src = '{"a": "x,]y", "folders": []}'
    obj = ws.parse_jsonc(src)
    assert obj["a"] == "x,]y"


def test_splice_preserves_comments_and_settings():
    src = (
        "{\n"
        "  // mon commentaire\n"
        '  "folders": [\n'
        '    { "path": "/old" }\n'
        "  ],\n"
        '  "settings": { "editor.tabSize": 2 }, // garde\n'
        '  "extensions": { "recommendations": ["x"] }\n'
        "}\n"
    )
    out = ws.splice_folders(src, [{"path": "/new1"}, {"path": "/new2"}])
    assert "// mon commentaire" in out
    assert '"editor.tabSize": 2' in out
    assert "// garde" in out
    assert '"recommendations": ["x"]' in out
    assert "/old" not in out
    obj = ws.parse_jsonc(out)
    assert [f["path"] for f in obj["folders"]] == ["/new1", "/new2"]
    assert obj["settings"] == {"editor.tabSize": 2}


def test_splice_preserves_per_folder_name():
    src = '{\n  "folders": [\n    { "path": "/a", "name": "Alpha" }\n  ]\n}\n'
    obj = ws.parse_jsonc(src)
    entries = ws.folder_entries(obj)
    entries.append({"path": "/b"})
    out = ws.splice_folders(src, entries)
    obj2 = ws.parse_jsonc(out)
    assert obj2["folders"][0] == {"path": "/a", "name": "Alpha"}
    assert obj2["folders"][1] == {"path": "/b"}


def test_splice_does_not_touch_nested_folders_key():
    # une clé "folders" imbriquée dans settings ne doit pas être ciblée
    src = (
        "{\n"
        '  "folders": [ {"path": "/real"} ],\n'
        '  "settings": { "search.folders": [ "/decoy" ] }\n'
        "}\n"
    )
    out = ws.splice_folders(src, [{"path": "/changed"}])
    obj = ws.parse_jsonc(out)
    assert obj["folders"] == [{"path": "/changed"}]
    assert obj["settings"]["search.folders"] == ["/decoy"]


def test_splice_empty_folders():
    src = '{\n  "folders": [ {"path": "/a"} ],\n  "settings": {}\n}\n'
    out = ws.splice_folders(src, [])
    obj = ws.parse_jsonc(out)
    assert obj["folders"] == []


def test_insert_folders_when_absent():
    src = '{\n  "settings": {}\n}\n'
    out = ws.splice_folders(src, [{"path": "/a"}])
    obj = ws.parse_jsonc(out)
    assert obj["folders"] == [{"path": "/a"}]
    assert "settings" in obj


def test_new_workspace_text_roundtrip():
    txt = ws.new_workspace_text([{"path": "/a"}])
    obj = json.loads(txt)
    assert obj == {"folders": [{"path": "/a"}], "settings": {}}
