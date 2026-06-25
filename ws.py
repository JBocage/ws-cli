#!/usr/bin/env python3
"""ws — CLI manager for multi-folder VSCode workspaces.

A `ws` workspace = a native `.code-workspace` file (source of truth: existence +
folders) + a metadata entry in `index.json`.

Stdlib only. See SPEC.md.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # non-POSIX: no inter-process lock
    fcntl = None

# --------------------------------------------------------------------------- #
# Exit codes
# --------------------------------------------------------------------------- #
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_EXISTS = 4


class WsError(Exception):
    """Business error; `code` is the associated exit code."""

    code = EXIT_ERROR

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UsageError(WsError):
    code = EXIT_USAGE


class NotFound(WsError):
    code = EXIT_NOT_FOUND


class AlreadyExists(WsError):
    code = EXIT_EXISTS


NAME_RE = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._-]*$")
WORKSPACE_SUFFIX = ".code-workspace"

SUBCOMMANDS = [
    "new", "open", "list", "show", "edit", "add",
    "rm-folder", "set", "rename", "delete", "path", "completion", "uninstall",
]


# --------------------------------------------------------------------------- #
# Paths / configuration
# --------------------------------------------------------------------------- #
def ws_home() -> Path:
    """Config directory: $WS_HOME › $XDG_CONFIG_HOME/ws › ~/.config/ws."""
    override = os.environ.get("WS_HOME")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "ws"


def workspaces_dir() -> Path:
    return ws_home() / "workspaces"


def index_path() -> Path:
    return ws_home() / "index.json"


def workspace_path(name: str) -> Path:
    return workspaces_dir() / f"{name}{WORKSPACE_SUFFIX}"


def workspace_exists(name: str) -> bool:
    return workspace_path(name).is_file()


def list_workspace_names() -> list[str]:
    """Names = scan of the `workspaces/` directory (always current). Sorted."""
    d = workspaces_dir()
    if not d.is_dir():
        return []
    return sorted(
        p.name[: -len(WORKSPACE_SUFFIX)]
        for p in d.glob(f"*{WORKSPACE_SUFFIX}")
        if not p.name.startswith(".tmp-ws-")  # ignore write-time temporaries
    )


# --------------------------------------------------------------------------- #
# Path resolution
# --------------------------------------------------------------------------- #
def resolve_path(p: str) -> str:
    """Absolute, ~ and $VAR expanded, symlinks NOT followed (faithful to input)."""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(p)))


def dedup_preserve(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def normalize_folder_path(raw: str, ws_file: Path) -> str:
    """Normalized folder path: ~ and $VAR expanded; a relative path is resolved
    against the directory of the .code-workspace file (as VSCode does)."""
    p = os.path.expanduser(os.path.expandvars(raw))
    if not os.path.isabs(p):
        p = str(ws_file.parent / p)
    return os.path.normpath(p)


def clean_tags(tags) -> list[str]:
    """Strip + dedup + drop empty tags."""
    out = []
    for t in tags or []:
        t = t.strip()
        if t and t not in out:
            out.append(t)
    return out


_lock_fd = None
_lock_depth = 0


@contextlib.contextmanager
def index_lock():
    """Exclusive inter-process lock covering a load→modify→save cycle.

    Reentrant within a single process (counter): `flock` on two distinct open
    file descriptions of the same file would otherwise deadlock against itself.
    """
    global _lock_fd, _lock_depth
    if fcntl is None:
        yield
        return
    if _lock_depth == 0:
        ws_home().mkdir(parents=True, exist_ok=True)
        _lock_fd = os.open(str(ws_home() / ".lock"), os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(_lock_fd, fcntl.LOCK_EX)
    _lock_depth += 1
    try:
        yield
    finally:
        _lock_depth -= 1
        if _lock_depth == 0:
            try:
                fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(_lock_fd)
                _lock_fd = None


# --------------------------------------------------------------------------- #
# JSONC: tolerant read + surgical editing of `folders`
# --------------------------------------------------------------------------- #
def strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments while respecting strings.

    Comments are dropped; strings (which may contain // or /*) are kept as-is.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            out.append(c)
            i += 1
            while i < n:
                ch = text[i]
                out.append(ch)
                if ch == "\\":
                    i += 1
                    if i < n:
                        out.append(text[i])
                        i += 1
                    continue
                i += 1
                if ch == '"':
                    break
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas (before ] or }), while respecting strings."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            out.append(c)
            i += 1
            while i < n:
                ch = text[i]
                out.append(ch)
                if ch == "\\":
                    i += 1
                    if i < n:
                        out.append(text[i])
                        i += 1
                    continue
                i += 1
                if ch == '"':
                    break
            continue
        if c == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "]}":
                i += 1  # skip the comma
                continue
        out.append(c)
        i += 1
    return "".join(out)


def parse_jsonc(text: str) -> dict:
    """Parse JSONC (comments + trailing commas) into a dict."""
    cleaned = _strip_trailing_commas(strip_jsonc(text))
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise WsError(f"invalid .code-workspace file: {exc}") from exc
    if not isinstance(data, dict):
        raise WsError("invalid .code-workspace file: the root must be an object {}")
    return data


def read_workspace(name: str) -> tuple[Path, str, dict]:
    """Return (path, raw text, parsed object) or raise NotFound."""
    path = workspace_path(name)
    if not path.is_file():
        raise NotFound(f"workspace not found: {name}")
    try:
        text = path.read_text(encoding="utf-8-sig")  # tolerate a possible BOM
    except (OSError, UnicodeDecodeError) as exc:
        raise WsError(f"{name}: unreadable file ({exc})") from exc
    return path, text, parse_jsonc(text)


def folder_entries(obj: dict) -> list:
    """RAW list of `folders` entries, kept as-is: dicts with or without `path`,
    bare strings, VSCode virtual groups. ws discards none of them."""
    raw = obj.get("folders", [])
    return list(raw) if isinstance(raw, list) else []


def entry_path(entry) -> str | None:
    """Raw path of a folders entry, or None (e.g. a virtual group without path)."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and isinstance(entry.get("path"), str):
        return entry["path"]
    return None


def folder_paths(obj: dict, ws_file: Path) -> list[str]:
    """Paths of folders that have a `path`, normalized (~/$VAR/relative resolved)."""
    out = []
    for entry in folder_entries(obj):
        raw = entry_path(entry)
        if raw is not None:
            out.append(normalize_folder_path(raw, ws_file))
    return out


# --- surgical editing -------------------------------------------------------- #
def _skip_ws_comments(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        break
    return i


def _match_pair(text: str, i: int, opener: str, closer: str) -> int:
    """`i` points at `opener`. Return the index just AFTER the matching `closer`."""
    n = len(text)
    depth = 0
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if c == '"':
            i += 1
            while i < n:
                ch = text[i]
                if ch == "\\":
                    i += 2
                    continue
                i += 1
                if ch == '"':
                    break
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise WsError("corrupt .code-workspace file: unbalanced delimiter")


def _value_end(text: str, i: int) -> int:
    """`i` points at the start of a JSON value. Return the index just after it."""
    c = text[i]
    if c == "[":
        return _match_pair(text, i, "[", "]")
    if c == "{":
        return _match_pair(text, i, "{", "}")
    if c == '"':
        n = len(text)
        i += 1
        while i < n:
            ch = text[i]
            if ch == "\\":
                i += 2
                continue
            i += 1
            if ch == '"':
                break
        return i
    # scalar: null / true / false / number — up to the separator
    n = len(text)
    while i < n and text[i] not in ",}]" and text[i] not in " \t\r\n":
        if text[i] == "/" and i + 1 < n and text[i + 1] in "/*":
            break
        i += 1
    return i


def _find_folders_value_span(text: str) -> tuple[int, int, int] | None:
    """(start, end, count) of the VALUE of the root `folders` key (whatever its
    type: array, null, object…), or None if the key is absent.

    With duplicate `folders` keys, returns the span of the LAST one — that's the
    one json.loads and VSCode keep — and `count` > 1 flags it.
    """
    i, n = 0, len(text)
    obj_depth = 0
    arr_depth = 0
    found = None
    count = 0
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if c == '"':
            i += 1
            buf = []
            while i < n:
                ch = text[i]
                if ch == "\\":
                    i += 1
                    if i < n:
                        buf.append(text[i])
                        i += 1
                    continue
                if ch == '"':
                    i += 1
                    break
                buf.append(ch)
                i += 1
            value = "".join(buf)
            if obj_depth == 1 and arr_depth == 0 and value == "folders":
                j = _skip_ws_comments(text, i)
                if j < n and text[j] == ":":
                    j = _skip_ws_comments(text, j + 1)
                    if j < n:
                        found = (j, _value_end(text, j))
                        count += 1
            continue
        if c == "{":
            obj_depth += 1
        elif c == "}":
            obj_depth -= 1
        elif c == "[":
            arr_depth += 1
        elif c == "]":
            arr_depth -= 1
        i += 1
    if found is None:
        return None
    return found[0], found[1], count


def _line_indent(text: str, pos: int) -> str:
    line_start = text.rfind("\n", 0, pos) + 1
    prefix = text[line_start:pos]
    return prefix[: len(prefix) - len(prefix.lstrip())]


def render_folders_array(folders: list[dict], base_indent: str) -> str:
    """Render the `folders` array; one entry per line, key order preserved."""
    if not folders:
        return "[]"
    unit = base_indent if base_indent else "  "
    item_indent = base_indent + unit
    lines = ["["]
    last = len(folders) - 1
    for k, entry in enumerate(folders):
        rendered = json.dumps(entry, ensure_ascii=False)
        comma = "" if k == last else ","
        lines.append(f"{item_indent}{rendered}{comma}")
    lines.append(f"{base_indent}]")
    return "\n".join(lines)


def _insert_folders(text: str, folders: list[dict]) -> str:
    """Rare case: `folders` absent → insert it at the start of the root object."""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] in "/*":
            i = _skip_ws_comments(text, i)
            continue
        if c == "{":
            base_indent = _line_indent(text, i)
            unit = "  "
            inner = base_indent + unit
            block = render_folders_array(folders, inner)
            insertion = f"\n{inner}\"folders\": {block},"
            return text[: i + 1] + insertion + text[i + 1:]
        i += 1
    raise WsError("invalid .code-workspace file: root object not found")


def splice_folders(text: str, folders: list[dict]) -> str:
    """Replace ONLY the value of `folders`; everything else is preserved.

    If `folders` exists but is not an array (e.g. `null`), its value is replaced
    — we never insert a second `folders` key.
    """
    span = _find_folders_value_span(text)
    if span is None:
        return _insert_folders(text, folders)
    start, end, count = span
    if count > 1:
        warn(f"'folders' key present {count} times; editing the last one "
             "(the one VSCode keeps)")
    base_indent = _line_indent(text, start)
    rendered = render_folders_array(folders, base_indent)
    return text[:start] + rendered + text[end:]


def new_workspace_text(folders: list[dict]) -> str:
    """Template for a workspace created by ws (clean JSON)."""
    return json.dumps({"folders": folders, "settings": {}}, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- #
# Atomic write
# --------------------------------------------------------------------------- #
def _fsync_dir(d: Path) -> None:
    try:
        fd = os.open(str(d), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass  # some filesystems disallow fsync on a directory


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # neutral suffix (.tmp): never matches the *.code-workspace glob
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-ws-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())  # data on disk BEFORE the rename
        os.replace(tmp, path)
        _fsync_dir(path.parent)  # durable rename
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------- #
# Index (metadata)
# --------------------------------------------------------------------------- #
META_FIELDS = ("description", "tags", "created", "last_opened")


def _index_bak() -> Path:
    p = index_path()
    return p.with_name(p.name + ".bak")


def _parse_index(text: str, source: str) -> dict:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise WsError(f"invalid {source}: the root must be an object {{}}")
    return data


def load_index() -> dict:
    p = index_path()
    if not p.is_file():
        return {}
    try:
        return _parse_index(p.read_text(encoding="utf-8"), "index.json")
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        bak = _index_bak()
        if bak.is_file():
            try:
                data = _parse_index(bak.read_text(encoding="utf-8"), "index.json.bak")
            except (json.JSONDecodeError, OSError, UnicodeDecodeError, WsError):
                raise WsError(
                    f"index.json and its backup are unreadable ({exc})."
                ) from exc
            warn(f"index.json unreadable ({exc}) — restored from {bak.name}")
            atomic_write(p, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            return data
        raise WsError(
            f"index.json unreadable or corrupt ({exc}). "
            "Fix it, or delete it to start over from the files alone."
        ) from exc


def _normalize_meta(meta: dict) -> dict:
    out = {}
    for field in META_FIELDS:
        if field in meta and meta[field] not in (None, "", []):
            out[field] = meta[field]
    return out


def save_index(idx: dict) -> None:
    """Write the index atomically, keeping an `index.json.bak` backup.

    NO automatic pruning: an entry whose file is temporarily absent is kept (and
    simply ignored at display time by list/show). Only `delete`/`rename` remove a
    key explicitly. This avoids destroying the metadata of a momentarily
    unavailable workspace.
    """
    ordered = {name: _normalize_meta(idx[name]) for name in sorted(idx)}
    p = index_path()
    if p.is_file():
        try:
            shutil.copy2(p, _index_bak())  # last known-good version
        except OSError:
            pass
    atomic_write(p, json.dumps(ordered, indent=2, ensure_ascii=False) + "\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- #
# Display / shared helpers
# --------------------------------------------------------------------------- #
# --- color (TTY only; respects $NO_COLOR, and $WS_COLOR=always) ------------- #
_ANSI = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m", "cyan": "\033[36m",
}


def _use_color(stream=None) -> bool:
    stream = stream if stream is not None else sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("WS_COLOR") == "always":
        return True
    return hasattr(stream, "isatty") and stream.isatty()


def paint(s: str, *styles: str, enabled: bool | None = None) -> str:
    if enabled is None:
        enabled = _use_color()
    if not enabled or not styles:
        return s
    prefix = "".join(_ANSI[st] for st in styles)
    return f"{prefix}{s}{_ANSI['reset']}"


def warn(msg: str) -> None:
    prefix = paint("⚠", "yellow", enabled=_use_color(sys.stderr))
    print(f"{prefix} {msg}", file=sys.stderr)


def ok(msg: str) -> None:
    print(f"{paint('✓', 'green')} {msg}")


def validate_name(name: str) -> None:
    if not NAME_RE.match(name):
        raise UsageError(
            f"invalid name: {name!r} (allowed: letters, digits, . _ -)"
        )


def run_external(cmd: list[str]) -> int:
    try:
        return subprocess.run(cmd).returncode
    except FileNotFoundError as exc:
        raise WsError(f"command not found: {cmd[0]} ({exc})") from exc
    except OSError as exc:
        raise WsError(f"cannot run {cmd[0]} ({exc})") from exc


def open_workspace(name: str, new_window: bool, reuse: bool) -> int:
    path, _, obj = read_workspace(name)
    for p in folder_paths(obj, path):
        if not os.path.isdir(p):
            warn(f"missing folder (opened anyway, greyed out in VSCode): {p}")
    cmd = ["code"]
    if new_window:
        cmd.append("-n")
    elif reuse:
        cmd.append("-r")
    cmd.append(str(path))
    rc = run_external(cmd)
    if rc == 0:
        # update last_opened (create a minimal entry if needed)
        with index_lock():
            idx = load_index()
            entry = idx.get(name, {})
            entry["last_opened"] = now_iso()
            idx[name] = entry
            save_index(idx)
    else:
        warn(f"`code` returned exit code {rc}; last_opened not updated")
    return rc


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_new(args) -> int:
    name = args.name
    validate_name(name)
    with index_lock():
        if workspace_exists(name):
            raise AlreadyExists(
                f"workspace already exists: {name}. Use `ws add {name} <dir…>`."
            )
        resolved = dedup_preserve(resolve_path(d) for d in args.dirs)
        missing = [p for p in resolved if not os.path.isdir(p)]
        if missing:
            for p in missing:
                warn(f"missing folder: {p}")
            if not args.force:
                raise WsError(
                    "creation blocked: missing folder(s). Re-run with --force."
                )
        folders = [{"path": p} for p in resolved]
        atomic_write(workspace_path(name), new_workspace_text(folders))

        idx = load_index()
        meta = {}
        if args.desc:
            meta["description"] = args.desc
        tags = clean_tags(args.tag)
        if tags:
            meta["tags"] = tags
        meta["created"] = now_iso()
        idx[name] = meta
        save_index(idx)

    ok(f"created workspace: {name} ({len(folders)} folder(s))")
    if args.open:
        open_workspace(name, new_window=False, reuse=False)
    return EXIT_OK


def cmd_open(args) -> int:
    name = args.name
    if not name:
        name = pick_workspace()
        if not name:
            return EXIT_OK  # cancelled / fallback already shown
    if not workspace_exists(name):
        raise NotFound(f"workspace not found: {name}")
    return open_workspace(name, new_window=args.new_window, reuse=args.reuse)


def _workspace_rows():
    """Iterate (name, path, obj, meta) for workspaces present on disk."""
    idx = load_index()
    for name in list_workspace_names():
        path = workspace_path(name)
        try:
            obj = parse_jsonc(path.read_text(encoding="utf-8-sig"))
        except (WsError, OSError, UnicodeDecodeError) as exc:
            warn(f"{name}: unreadable ({exc})")
            obj = None
        yield name, path, obj, idx.get(name, {})


def cmd_list(args) -> int:
    rows = []
    for name, path, obj, meta in _workspace_rows():
        tags = meta.get("tags", []) or []
        if args.tag and args.tag not in tags:
            continue
        paths = folder_paths(obj, path) if obj is not None else None
        rows.append({
            "name": name,
            "tags": tags,
            "folders": paths,
            "n_folders": len(paths) if paths is not None else None,
            "description": meta.get("description", ""),
        })

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return EXIT_OK

    if not rows:
        print("No workspaces." + (f" (tag filter={args.tag})" if args.tag else ""))
        return EXIT_OK

    name_w = max(len("NAME"), max(len(r["name"]) for r in rows))
    tags_w = max(len("TAGS"), max(len(",".join(r["tags"])) for r in rows))
    col = _use_color()
    header = f"{'NAME':<{name_w}}  {'TAGS':<{tags_w}}  {'#':>3}  DESCRIPTION"
    print(paint(header, "dim", enabled=col))
    for r in rows:
        n = "?" if r["n_folders"] is None else str(r["n_folders"])
        # pad BEFORE coloring to keep alignment intact
        name_cell = paint(f"{r['name']:<{name_w}}", "cyan", "bold", enabled=col)
        tags_cell = paint(f"{','.join(r['tags']):<{tags_w}}", "yellow", enabled=col)
        print(f"{name_cell}  {tags_cell}  {n:>3}  {r['description']}")
        if args.verbose and r["folders"]:
            for p in r["folders"]:
                if os.path.isdir(p):
                    print(f"    {p}")
                else:
                    print(f"    {paint(p + '  (missing)', 'red', enabled=col)}")
    return EXIT_OK


def cmd_show(args) -> int:
    path, _, obj = read_workspace(args.name)
    idx = load_index()
    meta = idx.get(args.name, {})
    paths = folder_paths(obj, path)

    if args.json:
        out = {
            "name": args.name,
            "path": str(path),
            "folders": paths,
            "description": meta.get("description", ""),
            "tags": meta.get("tags", []),
            "created": meta.get("created"),
            "last_opened": meta.get("last_opened"),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return EXIT_OK

    col = _use_color()
    print(paint(args.name, "cyan", "bold", enabled=col))
    print(f"  file        : {path}")
    if meta.get("description"):
        print(f"  description : {meta['description']}")
    if meta.get("tags"):
        print(f"  tags        : {paint(', '.join(meta['tags']), 'yellow', enabled=col)}")
    if meta.get("created"):
        print(f"  created     : {meta['created']}")
    if meta.get("last_opened"):
        print(f"  last opened : {meta['last_opened']}")
    print(f"  folders ({len(paths)}):")
    for p in paths:
        if os.path.isdir(p):
            print(f"    - {p}")
        else:
            print(f"    - {paint(p + '  (missing)', 'red', enabled=col)}")
    return EXIT_OK


def cmd_edit(args) -> int:
    path = workspace_path(args.name)
    if not path.is_file():
        raise NotFound(f"workspace not found: {args.name}")
    editor = (args.editor or os.environ.get("EDITOR") or "").strip() or "code -r"
    try:
        parts = shlex.split(editor)
    except ValueError as exc:
        raise UsageError(f"invalid editor command: {editor!r} ({exc})") from exc
    if not parts:
        parts = ["code", "-r"]
    return run_external(parts + [str(path)])


def cmd_add(args) -> int:
    with index_lock():
        path, text, obj = read_workspace(args.name)
        entries = folder_entries(obj)
        existing = {
            normalize_folder_path(p, path)
            for p in (entry_path(e) for e in entries)
            if p is not None
        }
        # full validation BEFORE any mutation
        to_add = []
        for d in args.dirs:
            rp = resolve_path(d)
            if rp in existing or rp in to_add:
                warn(f"already present (skipped): {rp}")
                continue
            if not os.path.isdir(rp):
                warn(f"missing folder: {rp}")
                if not args.force:
                    raise WsError(
                        f"add blocked: {rp} does not exist. Re-run with --force."
                    )
            to_add.append(rp)

        if to_add:
            # existing entries preserved as-is, new ones appended
            new_entries = entries + [{"path": p} for p in to_add]
            atomic_write(path, splice_folders(text, new_entries))
    ok(f"added {len(to_add)} folder(s) to {args.name}")
    return EXIT_OK


def cmd_rm_folder(args) -> int:
    with index_lock():
        path, text, obj = read_workspace(args.name)
        entries = folder_entries(obj)
        targets = {resolve_path(d) for d in args.dirs}

        present = set()
        kept = []
        removed = 0
        for e in entries:
            raw = entry_path(e)
            norm = normalize_folder_path(raw, path) if raw is not None else None
            if norm is not None:
                present.add(norm)
            if norm is not None and norm in targets:
                removed += 1
            else:
                kept.append(e)  # entries without a path (groups) are kept
        for p in sorted(targets - present):
            warn(f"folder not in workspace (skipped): {p}")

        if removed:
            atomic_write(path, splice_folders(text, kept))
    ok(f"removed {removed} folder(s) from {args.name}")
    return EXIT_OK


def cmd_set(args) -> int:
    if not args.name:
        raise UsageError("workspace name required")
    if not workspace_exists(args.name):
        raise NotFound(f"workspace not found: {args.name}")
    if args.desc is None and not args.add_tag and not args.rm_tag:
        raise UsageError("nothing to change (use --desc / --add-tag / --rm-tag)")

    with index_lock():
        idx = load_index()
        meta = idx.get(args.name, {})
        if args.desc is not None:
            meta["description"] = args.desc
        tags = list(meta.get("tags", []) or [])
        for t in clean_tags(args.add_tag):
            if t not in tags:
                tags.append(t)
        for t in (s.strip() for s in args.rm_tag or []):
            if t in tags:
                tags.remove(t)
        meta["tags"] = tags
        idx[args.name] = meta
        save_index(idx)
    ok(f"metadata updated: {args.name}")
    return EXIT_OK


def cmd_rename(args) -> int:
    old, new = args.old, args.new
    validate_name(new)
    with index_lock():
        if not workspace_exists(old):
            raise NotFound(f"workspace not found: {old}")
        if workspace_exists(new):
            raise AlreadyExists(f"workspace already exists: {new}")
        idx = load_index()  # loaded before replace: if unreadable, we don't rename
        os.replace(workspace_path(old), workspace_path(new))
        if old in idx:
            idx[new] = idx.pop(old)
        save_index(idx)
    ok(f"renamed: {old} → {new}")
    return EXIT_OK


def cmd_delete(args) -> int:
    name = args.name
    if not workspace_exists(name):
        raise NotFound(f"workspace not found: {name}")
    if not args.yes:
        if not sys.stdin.isatty():
            raise WsError("deletion not confirmed (pass -y in non-interactive mode)")
        resp = input(f"Delete workspace '{name}'? [y/N] ").strip().lower()
        if resp not in ("y", "yes"):
            print("Cancelled.")
            return EXIT_OK
    with index_lock():
        wp = workspace_path(name)
        if wp.is_file():
            wp.unlink()
        idx = load_index()
        idx.pop(name, None)
        save_index(idx)
    ok(f"deleted: {name}")
    return EXIT_OK


def cmd_path(args) -> int:
    if not workspace_exists(args.name):
        raise NotFound(f"workspace not found: {args.name}")
    print(str(workspace_path(args.name)))
    return EXIT_OK


def bin_dir() -> Path:
    return Path(os.environ.get("XDG_BIN_HOME") or (Path.home() / ".local" / "bin"))


def lib_dir() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "ws-cli"


def completion_install_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "bash-completion" / "completions" / "ws"


def cmd_completion(args) -> int:
    if args.what == "bash":
        print(BASH_COMPLETION, end="")
    elif args.what == "install":
        dest = completion_install_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(BASH_COMPLETION, encoding="utf-8")
        ok(f"bash completion installed: {dest}")
        print(f"Enable it now: source {dest}   (or open a new shell)")
    elif args.what == "names":
        for n in list_workspace_names():
            print(n)
    elif args.what == "tags":
        idx = load_index()
        tags = set()
        for meta in idx.values():
            for t in meta.get("tags", []) or []:
                tags.add(t)
        for t in sorted(tags):
            print(t)
    else:
        raise UsageError(f"unknown completion target: {args.what}")
    return EXIT_OK


def cmd_uninstall(args) -> int:
    self_path = str(Path(__file__).resolve())
    if "/uv/tools/" in self_path:
        manager = "uv tool uninstall ws-vscode"
    elif "/pipx/" in self_path:
        manager = "pipx uninstall ws-vscode"
    else:
        manager = None

    # completion: removable in all cases
    comp = completion_install_path()
    if comp.exists():
        comp.unlink()
        ok(f"completion removed: {comp}")

    if manager:
        warn("ws was installed via a package manager; its executable is not removed here.")
        print(f"  Remove it with: {manager}")
    else:
        # install.sh / curl: symlink in ~/.local/bin (+ ws.py in ws-cli/ for remote mode)
        link = bin_dir() / "ws"
        if link.is_symlink():
            target = os.path.realpath(link)
            if target.endswith("ws.py"):
                link.unlink()
                ok(f"executable removed: {link}")
            else:
                warn(f"{link} points to {target} (unknown) — left intact.")
        elif link.exists():
            warn(f"{link} is not a symlink (installed via uv/pipx?) — left intact.")
            print("  If installed via uv: uv tool uninstall ws-vscode")
        ld = lib_dir()
        if ld.is_dir():
            shutil.rmtree(ld)
            ok(f"files removed: {ld}")

    # workspaces / metadata: deleted only on request
    cfg = ws_home()
    if cfg.is_dir():
        if args.purge:
            shutil.rmtree(cfg)
            ok(f"configuration removed: {cfg}")
        elif sys.stdin.isatty():
            resp = input(f"Also delete your workspaces and metadata ({cfg})? [y/N] ").strip().lower()
            if resp in ("y", "yes"):
                shutil.rmtree(cfg)
                ok(f"configuration removed: {cfg}")
            else:
                print(f"· configuration kept: {cfg}")
        else:
            print(f"· configuration kept: {cfg} (use --purge to delete it)")

    print("Uninstalled.")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# fzf
# --------------------------------------------------------------------------- #
def pick_workspace() -> str | None:
    names = list_workspace_names()
    if not names:
        raise WsError("no workspace to open")
    if not shutil.which("fzf"):
        warn("fzf not found — here are the workspaces:")
        for n in names:
            print(n)
        return None
    script = os.path.realpath(__file__)
    preview = f"{shlex.quote(sys.executable)} {shlex.quote(script)} show {{}}"
    try:
        proc = subprocess.run(
            ["fzf", "--prompt", "ws> ", "--height", "40%", "--reverse",
             "--preview", preview, "--preview-window", "right:60%"],
            input="\n".join(names),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise WsError(f"fzf not found: {exc}") from exc
    if proc.returncode != 0:
        return None  # cancelled (Esc → 130)
    return proc.stdout.strip() or None


# --------------------------------------------------------------------------- #
# bash completion script
# --------------------------------------------------------------------------- #
BASH_COMPLETION = r"""# bash completion for `ws` — generated by `ws completion bash`
_ws() {
    local cur prev cmd
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    local subcommands="new open list show edit add rm-folder set rename delete path completion uninstall"

    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$subcommands" -- "$cur") )
        return 0
    fi

    cmd="${COMP_WORDS[1]}"

    case "$prev" in
        --tag|--add-tag|--rm-tag)
            local _tags; _tags="$(ws completion tags 2>/dev/null)"
            local IFS=$'\n'
            mapfile -t COMPREPLY < <(compgen -W "$_tags" -- "$cur")
            return 0
            ;;
    esac

    case "$cmd" in
        open|edit|delete|rename|path|show|set|add|rm-folder)
            if [ "$COMP_CWORD" -eq 2 ]; then
                local _names; _names="$(ws completion names 2>/dev/null)"
                local IFS=$'\n'
                mapfile -t COMPREPLY < <(compgen -W "$_names" -- "$cur")
                return 0
            fi
            ;;
    esac

    case "$cmd" in
        new)
            if [ "$COMP_CWORD" -ge 3 ]; then
                COMPREPLY=( $(compgen -d -- "$cur") )
                return 0
            fi
            ;;
        add|rm-folder)
            if [ "$COMP_CWORD" -ge 3 ]; then
                COMPREPLY=( $(compgen -d -- "$cur") )
                return 0
            fi
            ;;
        completion)
            if [ "$COMP_CWORD" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "bash install names tags" -- "$cur") )
                return 0
            fi
            ;;
    esac

    return 0
}
complete -F _ws ws
"""


# --------------------------------------------------------------------------- #
# CLI / dispatch
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ws",
        description="Manager for multi-folder VSCode workspaces.",
    )
    sub = p.add_subparsers(dest="command", metavar="<command>")

    sp = sub.add_parser("new", help="create a workspace")
    sp.add_argument("name")
    sp.add_argument("dirs", nargs="+", metavar="dir")
    sp.add_argument("--desc", help="description")
    sp.add_argument("--tag", action="append", help="tag (repeatable)")
    sp.add_argument("--open", action="store_true", help="open after creation")
    sp.add_argument("--force", action="store_true", help="allow missing folders")
    sp.set_defaults(func=cmd_new)

    sp = sub.add_parser("open", help="open a workspace (no name → fzf)")
    sp.add_argument("name", nargs="?")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("-n", "--new-window", action="store_true", help="new window")
    g.add_argument("-r", "--reuse", action="store_true", help="reuse the window")
    sp.set_defaults(func=cmd_open)

    sp = sub.add_parser("list", help="list workspaces")
    sp.add_argument("--tag", help="filter by tag")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("-v", "--verbose", action="store_true", help="show paths")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("show", help="workspace details")
    sp.add_argument("name")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("edit", help="edit the .code-workspace in $EDITOR")
    sp.add_argument("name")
    sp.add_argument("--editor", help="edit command (default: $EDITOR or 'code -r')")
    sp.set_defaults(func=cmd_edit)

    sp = sub.add_parser("add", help="add folders")
    sp.add_argument("name")
    sp.add_argument("dirs", nargs="+", metavar="dir")
    sp.add_argument("--force", action="store_true", help="allow missing folders")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("rm-folder", help="remove folders")
    sp.add_argument("name")
    sp.add_argument("dirs", nargs="+", metavar="dir")
    sp.set_defaults(func=cmd_rm_folder)

    sp = sub.add_parser("set", help="edit metadata")
    sp.add_argument("name")
    sp.add_argument("--desc", help="description")
    sp.add_argument("--add-tag", action="append", help="add a tag (repeatable)")
    sp.add_argument("--rm-tag", action="append", help="remove a tag (repeatable)")
    sp.set_defaults(func=cmd_set)

    sp = sub.add_parser("rename", help="rename a workspace")
    sp.add_argument("old")
    sp.add_argument("new")
    sp.set_defaults(func=cmd_rename)

    sp = sub.add_parser("delete", help="delete a workspace")
    sp.add_argument("name")
    sp.add_argument("-y", "--yes", action="store_true", help="no confirmation")
    sp.set_defaults(func=cmd_delete)

    sp = sub.add_parser("path", help="print the .code-workspace path")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_path)

    sp = sub.add_parser("completion", help="shell completion")
    sp.add_argument("what", choices=["bash", "install", "names", "tags"],
                    help="bash: print the script; install: place it in bash-completion")
    sp.set_defaults(func=cmd_completion)

    sp = sub.add_parser("uninstall", help="uninstall ws (executable + completion)")
    sp.add_argument("--purge", action="store_true",
                    help="also delete your workspaces and metadata")
    sp.set_defaults(func=cmd_uninstall)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.func(args)
    except WsError as exc:
        print(f"ws: {exc.message}", file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_ERROR
    except (OSError, ValueError) as exc:
        print(f"ws: unexpected error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
