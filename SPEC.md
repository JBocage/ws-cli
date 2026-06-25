# `ws` — CLI manager for VSCode workspaces

> Spec v0.1 — working document. Status: to be validated.

## 1. Goal

A lightweight CLI to **create, manage and open** multi-folder VSCode workspaces,
with bash completion on every command.

```bash
ws open platform        # opens platform-api + platform-infra in a single VSCode window
ws list                 # lists workspaces (name, tags, folder count, description)
ws new iris-model ~/dev/iris-train ~/dev/iris-serve --tag ml --desc "Iris model"
ws edit platform        # edit the workspace
ws delete old-thing     # delete
```

### Non-goals

- Do **not** reimplement VSCode multi-root: we rely on the native `.code-workspace` format.
- No git repo / clone management (that's the job of `ghq`, `gh repo clone`, etc.).
- No (in v1) zsh/fish completion — the target environment is **bash**.

## 2. Key decision

⚠️ `code folderA folderB` does **not** open a multi-root workspace: it opens separate
windows. The only reliable way to get **a single window with multiple folders** is a
`.code-workspace` file. The whole architecture follows from this:

> **A `ws` workspace = a native `.code-workspace` file + a metadata entry.**

## 3. Storage

Config directory (honors `$XDG_CONFIG_HOME`, default `~/.config`):

```
$XDG_CONFIG_HOME/ws/
├── workspaces/
│   ├── platform.code-workspace
│   └── iris-model.code-workspace
└── index.json            # metadata per workspace name
```

Can be overridden via `$WS_HOME` (handy for tests).

### 3.1 `.code-workspace` file (source of truth: existence + folders)

100% native VSCode format, never polluted by `ws` (we only touch `folders`):

```jsonc
// workspaces/platform.code-workspace
{
  "folders": [
    { "path": "/home/julien/dev/platform-api" },
    { "path": "/home/julien/dev/platform-infra" }
  ],
  "settings": {}
}
```

- **Absolute** paths (robust, independent of cwd). `~` and env vars are resolved at
  creation time.
- The **workspace name = the file `stem`** (`platform.code-workspace` → `platform`).
- You can edit the file in VSCode (adding folders, settings, extensions, launch):
  `ws` never overwrites those keys, it only edits `folders` surgically.

### 3.2 `index.json` (metadata)

```jsonc
{
  "platform": {
    "description": "Platform API + infra",
    "tags": ["platform", "infra"],
    "created": "2026-06-25T10:00:00Z",
    "last_opened": "2026-06-25T14:30:00Z"
  },
  "iris-model": { "description": "Iris model", "tags": ["ml"] }
}
```

Reconciliation rules (the `workspaces/` directory wins):
- A `.code-workspace` **without** an index entry → shown with empty metadata (e.g. "Save Workspace As" from VSCode).
- An index entry **without** a file → orphan, ignored at display time. ⚠️ **Revised decision
  (v1 impl.)**: the orphan is **kept** and not pruned automatically — blind pruning on every
  write destroyed the metadata of a temporarily absent workspace (network FS, file being
  edited / manually renamed). Only `delete`/`rename` remove a key explicitly. A dedicated
  `ws prune` remains possible (post-v1) for deliberate cleanup.
- **Atomic** writes (temp file + `rename`) so the index is never corrupted.

## 4. CLI surface

| Command | Description | Key options |
|---|---|---|
| `ws new <name> <dir…>` | Create a workspace | `--desc TEXT`, `--tag T` (repeatable), `--open`, `--force` (missing folders) |
| `ws open [name]` | Open the workspace; without `name` → `fzf` picker | `-n` new window, `-r` reuse |
| `ws list` | List: `NAME  TAGS  #FOLDERS  DESCRIPTION` | `--tag T` (filter), `--json`, `-v` (paths) |
| `ws show <name>` | Workspace details (folders + metadata) | `--json` |
| `ws edit <name>` | Open the `.code-workspace` in `$EDITOR` (default `code -r`) | `--editor CMD` |
| `ws add <name> <dir…>` | Add folders (dedup) | `--force` |
| `ws rm-folder <name> <dir…>` | Remove folders | |
| `ws set <name>` | Edit metadata | `--desc`, `--add-tag`, `--rm-tag` |
| `ws rename <old> <new>` | Rename (file + index key) | |
| `ws delete <name>` | Delete (file + index entry) | `-y` (no confirmation) |
| `ws path <name>` | Print the `.code-workspace` path (scripting) | |
| `ws completion bash` | Print the completion script | |

### Behaviors

- **`ws open`**: `code [-n|-r] <path>`, then update `last_opened`. Without a flag, we keep
  `code`'s default behavior (reuses the current window if relevant).
- **`ws new`**: validates the name (`[A-Za-z0-9._-]+`, unique), resolves/dedups/checks folders
  (warns if a folder is missing, unless `--force`), writes the file then the index entry.
- **Exit codes**: `0` ok, `1` generic error, `2` misuse, `3` workspace not found,
  `4` workspace already exists. (Makes scripting easier.)

## 5. bash completion

`_ws` function (from `ws completion bash`, placed in
`~/.local/share/bash-completion/completions/ws`):

- 1st token → subcommands (`open`, `list`, `new`, …).
- `open|edit|delete|rename|path|show|set|add|rm-folder <TAB>` → **workspace names** (scan of `workspaces/`).
- `--tag <TAB>` → existing tags (extracted from `index.json`).
- `new <name> <TAB>` → standard **folder** completion.

The source of names is the scan of the `workspaces/` directory → always current, including
for workspaces created from VSCode.

## 6. `fzf` integration (`ws open` without argument)

`ws open` → `fzf` over the list of workspaces, with a preview window showing description +
folders (via `ws show`). Enter = open. Clean fallback if `fzf` is absent (message + `ws list`).

## 7. Installation & distribution

Target: **share via GitHub, easy install, zero third-party dependency**.

- **Main path**: `git clone` + `./install.sh` (or `curl -fsSL <raw>/install.sh | bash`)
  - symlink `ws` (single-file executable Python script) into `~/.local/bin`,
  - install the completion into `~/.local/share/bash-completion/completions/ws`,
  - check/warn that `~/.local/bin` is in `PATH`.
- **Bonus**: `pyproject.toml` with `[project.scripts] ws = "..."` for machines that prefer
  `pipx install git+…` or `uv tool install`.
- No `pip`/`venv` required on the dev machine (pipx is absent there anyway).

## 8. Technical choices

- **Language**: Python 3.10+, **stdlib only** (`argparse`, `json`, `pathlib`, `subprocess`,
  `os`, `shutil`). No TOML (so no third-party writer needed): everything is JSON.
- **Single file**: a single `ws` executable → trivial install/sharing.
- **Why not Go**: better for single binaries in releases, but the toolchain is absent and
  Python is more than enough for a tool that orchestrates `code` + manipulates JSON.
  To reconsider if we want binary GitHub Actions releases.

## 9. Edge cases & decisions

- **Name already taken** → error (code 4), suggests `ws add`.
- **Folder missing at creation** → warning, blocks unless `--force`.
- **Folder missing at open** → open anyway (VSCode greys it out), warn.
- **`~` / `$VAR` in args** → resolved and stored as absolute.
- **File/index drift** → `ws list` is based on the files; orphan index entries ignored at
  display time but kept (see §3.2, data safety; never destroyed blindly).
- **`ws import <path>`** (post-v1): adopt an existing `.code-workspace` located elsewhere.

## 10. Roadmap

- **v1**: `new`/`open`/`list`/`show`/`edit`/`add`/`rm-folder`/`set`/`rename`/`delete`/`path`
  + metadata (desc, tags) + bash completion + `fzf` picker + `install.sh` + `curl|bash`
  installer + `ws uninstall`.
- **v1.1**: `ws import`, sort by `last_opened`, richer `--tag` filter, `pyproject.toml`.
- **v2**: zsh/fish completion, binary releases, integration tests.
