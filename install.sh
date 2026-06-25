#!/usr/bin/env bash
# Install `ws`. Two modes:
#   - from a clone   : ./install.sh           (symlink to the local ws.py)
#   - via curl | bash: curl -fsSL <raw>/install.sh | bash   (downloads ws.py)
# Options: --force (overwrite an existing ws not managed by this script)
set -euo pipefail

REPO="JBocage/ws-cli"
BRANCH="main"
RAW="https://raw.githubusercontent.com/${REPO}/${BRANCH}"

BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
COMP_DIR="${DATA_DIR}/bash-completion/completions"
LIB_DIR="${DATA_DIR}/ws-cli"          # where ws.py lives in remote mode

FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

# --- prerequisites --------------------------------------------------------- #
if ! command -v python3 >/dev/null 2>&1; then
    echo "✗ python3 not found (Python 3.10+ required)." >&2
    exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    echo "✗ Python 3.10+ required (found: $(python3 --version 2>&1))." >&2
    exit 1
fi

mkdir -p "$BIN_DIR" "$COMP_DIR"
TARGET="$BIN_DIR/ws"

# refuse to overwrite a ws not managed by this script (unless --force)
if [ -e "$TARGET" ] && [ ! -L "$TARGET" ] && [ "$FORCE" != 1 ]; then
    echo "✗ $TARGET already exists (a file, not a symlink). Re-run with --force." >&2
    exit 1
fi

# --- source: local clone, otherwise download ------------------------------- #
SELF="${BASH_SOURCE[0]:-}"
SCRIPT_DIR=""
if [ -n "$SELF" ] && [ "$SELF" != "bash" ] && [ "$SELF" != "/dev/stdin" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$SELF")" 2>/dev/null && pwd || true)"
fi

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/ws.py" ]; then
    SRC="$SCRIPT_DIR/ws.py"
    echo "→ Installing from local clone ($SRC)"
else
    echo "→ Downloading ws from github.com/$REPO …"
    mkdir -p "$LIB_DIR"
    fetch() {  # fetch URL DEST
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL "$1" -o "$2"
        elif command -v wget >/dev/null 2>&1; then
            wget -qO "$2" "$1"
        else
            echo "✗ curl or wget required for remote installation." >&2
            exit 1
        fi
    }
    fetch "$RAW/ws.py" "$LIB_DIR/ws.py"
    fetch "$RAW/uninstall.sh" "$LIB_DIR/uninstall.sh" || true
    chmod +x "$LIB_DIR/uninstall.sh" 2>/dev/null || true
    SRC="$LIB_DIR/ws.py"
fi

chmod +x "$SRC"
ln -sf "$SRC" "$TARGET"
echo "✓ ws → $TARGET"

# --- bash completion ------------------------------------------------------- #
"$SRC" completion bash > "$COMP_DIR/ws"
echo "✓ bash completion → $COMP_DIR/ws"

# --- PATH ------------------------------------------------------------------ #
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        echo "⚠ $BIN_DIR is not in your PATH."
        echo "  Add to your ~/.bashrc: export PATH=\"\$HOME/.local/bin:\$PATH\""
        ;;
esac

echo
echo "Done. Open a new shell (or: source \"$COMP_DIR/ws\")."
if [ -f "$LIB_DIR/uninstall.sh" ]; then
    echo "Uninstall: ws uninstall   (or: curl -fsSL $RAW/uninstall.sh | bash)"
else
    echo "Uninstall: ws uninstall   (or: ./uninstall.sh)"
fi
