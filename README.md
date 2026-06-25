# `ws` — CLI manager for VSCode workspaces

Create, manage and open **multi-folder VSCode workspaces** in one command, with
bash completion. A `ws` workspace = a native `.code-workspace` file (source of
truth) + a metadata entry.

```bash
ws new platform ~/dev/platform-api ~/dev/platform-infra --tag infra --desc "API + infra"
ws open platform     # a single VSCode window, both folders
ws list              # NAME  TAGS  #FOLDERS  DESCRIPTION
ws open              # no name → fzf picker with preview
```

## Installation

Simplest — installs the executable **and** bash completion in one command:

```bash
curl -fsSL https://raw.githubusercontent.com/JBocage/ws-cli/main/install.sh | bash
```

The script downloads `ws.py`, creates a `ws` symlink in `~/.local/bin`, installs the
completion into `~/.local/share/bash-completion/completions/ws`, and checks your `PATH`.
Then open a new shell. (As with any `curl | bash`, inspect the script first if you like.)

From a clone (to hack / contribute) — same script, uses the local `ws.py`:

```bash
git clone https://github.com/JBocage/ws-cli.git && cd ws-cli
./install.sh
```

Via `uv` or `pipx` (installs the executable only; completion is set up afterwards):

```bash
uv tool install git+https://github.com/JBocage/ws-cli
# or: pipx install git+https://github.com/JBocage/ws-cli
ws completion install
```

No third-party runtime dependency — Python 3.10+ and the stdlib are enough.
`ws list`/`ws show` output is colored in a terminal (disable with `NO_COLOR=1`).

### Uninstall

```bash
ws uninstall            # removes the executable + completion; asks about your data
ws uninstall --purge    # also removes your workspaces and metadata
```

`ws uninstall` detects the install method: for a `uv`/`pipx` install it points you to
`uv tool uninstall ws-vscode` (resp. `pipx uninstall ws-vscode`).

If `ws` is no longer runnable, the script is still available:

```bash
curl -fsSL https://raw.githubusercontent.com/JBocage/ws-cli/main/uninstall.sh | bash
# (or ./uninstall.sh from a clone; --purge to also delete your data)
```

## Commands

| Command | Description |
|---|---|
| `ws new <name> <dir…>` | create a workspace (`--desc`, `--tag`, `--open`, `--force`) |
| `ws open [name]` | open (no name → fzf); `-n` new window, `-r` reuse |
| `ws list` | list (`--tag`, `--json`, `-v` paths, `-vv` full details) |
| `ws show <name>` | details (`--json`) |
| `ws edit <name>` | open the `.code-workspace` in `$EDITOR` (default `code -r`) |
| `ws add <name> <dir…>` | add folders (dedup, `--force`) |
| `ws rm-folder <name> <dir…>` | remove folders |
| `ws set <name>` | metadata (`--desc`, `--add-tag`, `--rm-tag`) |
| `ws rename <old> <new>` | rename |
| `ws delete <name>` | delete (`-y`) |
| `ws path <name>` | print the `.code-workspace` path |
| `ws completion bash` | print the completion script |
| `ws uninstall` | uninstall ws (`--purge` to also remove your data) |

Exit codes: `0` ok, `1` error, `2` misuse, `3` not found, `4` already exists.

## Storage

```
$XDG_CONFIG_HOME/ws/            (default ~/.config/ws, override with $WS_HOME)
├── workspaces/<name>.code-workspace   # source of truth (existence + folders)
└── index.json                         # metadata (desc, tags, dates)
```

The `workspaces/` directory wins: a `.code-workspace` created from VSCode shows up
automatically; an index entry with no file is **ignored at display time** but **kept**
(never destroyed by an unrelated command — data safety). `ws` edits **only** the
`folders` key of the file — your `settings`, `extensions`, `launch` and comments are
preserved.

Robustness: atomic writes (`fsync` + `rename`), an `index.json.bak` backup restored
automatically if `index.json` is corrupt, and an inter-process lock for concurrent writes.

## Development

```bash
pip install -e ".[dev]"   # or: uv pip install pytest
pytest
```
