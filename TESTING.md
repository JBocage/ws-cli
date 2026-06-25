# Test protocol — `ws`

Two levels: **(A)** the automated suite, **(B)** a guided manual walkthrough that
exercises every command and every edge case from the spec. Everything happens in a
throwaway `$WS_HOME`: **none** of your real configs are touched.

---

## A. Automated suite (pytest)

```bash
cd /home/julien/dev-perso/ws

# pytest is not a runtime dependency; run it via uv (already on the machine)
uv run --with pytest pytest -v
```

Expected: **71 passed**. Covers the JSONC parser (comments/settings/`name` preservation),
CRUD, file↔index reconciliation, opening (mocked `code` argv), color, completion, and uninstall.

---

## B. Manual walkthrough

### 0. Isolated sandbox

```bash
cd /home/julien/dev-perso/ws
export WS_HOME="$(mktemp -d)/ws"      # throwaway storage
unset XDG_CONFIG_HOME
mkdir -p /tmp/ws-demo/api /tmp/ws-demo/infra /tmp/ws-demo/train
alias ws='./ws.py'                    # or: ./install.sh then use `ws` directly
```

> To start over at any time: `rm -rf "$WS_HOME"`.

### 1. Creation (`new`)

```bash
ws new platform /tmp/ws-demo/api /tmp/ws-demo/infra --tag infra --tag platform --desc "API + infra"
ws new iris ~/dev/iris-train --tag ml --desc "Iris model"      # ~ must resolve to absolute
cat "$WS_HOME/workspaces/platform.code-workspace"               # ABSOLUTE paths, settings:{}
cat "$WS_HOME/index.json"                                       # metadata + created
```

Check: `.code-workspace` file created, absolute paths, `~` resolved, index populated.

### 2. Validation & exit codes

```bash
ws new "bad name!" /tmp/ws-demo/api ; echo "expected 2 → $?"     # invalid name
ws new platform /tmp/ws-demo/api    ; echo "expected 4 → $?"     # already exists (+ suggests `ws add`)
ws new broken /tmp/ws-demo/nope     ; echo "expected 1 → $?"     # missing folder, blocked
ws new broken /tmp/ws-demo/nope --force ; echo "expected 0 → $?" # forced: created + warning
ws show ghost                       ; echo "expected 3 → $?"     # not found
```

Expected codes: `2`, `4`, `1`, `0`, `3`.

### 3. List & details (`list`, `show`)

```bash
ws list                 # columns NAME TAGS #FOLDERS DESCRIPTION
ws list -v              # + paths under each row (missing folders annotated)
ws list --tag ml        # filter: shows only `iris`
ws list --json | python3 -m json.tool
ws show platform        # readable details + present/missing state of folders
ws show platform --json
```

### 4. Folders (`add`, `rm-folder`) — **surgical preservation**

```bash
# Simulate a manual VSCode-style edit: comments + settings + per-folder `name`
cat > "$WS_HOME/workspaces/platform.code-workspace" <<'EOF'
{
  // my personal comment
  "folders": [
    { "path": "/tmp/ws-demo/api", "name": "API" }
  ],
  "settings": { "editor.tabSize": 2 },  // to preserve
  "extensions": { "recommendations": ["ms-python.python"] }
}
EOF

ws add platform /tmp/ws-demo/infra /tmp/ws-demo/api    # /api already present → skipped (dedup)
cat "$WS_HOME/workspaces/platform.code-workspace"
```

You **must** verify after `add`:
- the `// my personal comment`, `settings`, `extensions` are **intact**;
- the existing entry keeps its `"name": "API"`;
- `/tmp/ws-demo/infra` is added, `/api` is **not** duplicated.

```bash
ws rm-folder platform /tmp/ws-demo/api    # remove by path
ws add platform /tmp/ws-demo/nope --force # missing folder: warned but added
```

### 5. Metadata (`set`)

```bash
ws set platform --desc "Full platform" --add-tag prod
ws set platform --rm-tag infra
ws show platform        # description and tags updated
```

### 6. Rename & delete (`rename`, `delete`)

```bash
ws rename platform plat
ws show plat                                    # metadata kept
ls "$WS_HOME/workspaces/"                        # plat.code-workspace, no more platform
ws rename plat iris ; echo "expected 4 → $?"     # collision with an existing name
ws delete plat                                   # asks for confirmation [y/N] → answer n, then retry
ws delete plat -y                                # no confirmation
ws list                                          # `plat` is gone
```

### 7. File ↔ index reconciliation (drift)

```bash
# (a) Workspace created "outside ws" (Save Workspace As): shows up with empty metadata
echo '{ "folders": [ {"path": "/tmp/ws-demo/train"} ] }' > "$WS_HOME/workspaces/external.code-workspace"
ws list                                          # `external` listed, no tags/description

# (b) Orphan index entry: ignored at display time, but KEPT (data safety)
python3 - <<'EOF'
import json, os
p = os.path.join(os.environ["WS_HOME"], "index.json")
idx = json.load(open(p)); idx["ghost"] = {"tags": ["x"]}; json.dump(idx, open(p, "w"))
EOF
ws list                                          # `ghost` absent from the list
ws set external --desc "adopted" ; cat "$WS_HOME/index.json"   # `ghost` still there (not destroyed)
```

### 8. Opening (`open`, `edit`) — requires VSCode

> These commands actually launch `code`. Do this in a graphical session.

```bash
ws open external         # a single VSCode window with the folder(s)
ws open external -n      # new window
ws show external --json  # last_opened now populated
ws edit external         # opens the .code-workspace in $EDITOR (default: code -r)
ws open                  # NO argument → fzf picker, preview = ws show; Enter to open
```

Check: `last_opened` updated after `open`; the `fzf` picker shows the preview;
if `fzf` is absent, clean fallback (message + list).

### 9. bash completion

```bash
ws completion bash | bash -n && echo "completion script: syntax OK"
ws completion install      # install it into bash-completion
ws completion names        # names (scan of the workspaces/ directory)
ws completion tags         # tags (extracted from the index)

# Interactive test (in a bash shell):
source <(ws completion bash)
ws op<TAB>                  # completes "open"
ws open <TAB>              # proposes workspace names
ws set external --add-tag <TAB>   # proposes existing tags
ws new foo <TAB>           # completes folders
```

### 10. `path` (scripting) & `$WS_HOME` override

```bash
code "$(ws path external)"       # open via the printed path
WS_HOME=/other/place ws list     # the override changes storage
```

### Cleanup

```bash
rm -rf "$WS_HOME" /tmp/ws-demo
unalias ws 2>/dev/null
```

---

## Expected outcomes summary

| Case | Expected |
|---|---|
| Nominal creation | `.code-workspace` file (absolute paths) + index entry |
| Invalid name | code **2** |
| Name already taken | code **4** + `ws add` suggestion |
| Missing folder without `--force` | code **1**, nothing created |
| Workspace not found | code **3** |
| `add`/`rm-folder` on a commented file | comments/settings/`name` **preserved** |
| Folder dedup | no duplicates |
| File without index | listed, empty metadata |
| Orphan index | ignored at display, **kept** (never destroyed by an unrelated command) |
| `open` | launches `code`, updates `last_opened` (unless `code` fails) |
