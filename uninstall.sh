#!/usr/bin/env bash
# Uninstall `ws`: remove the symlink, the completion and (remote mode) ws.py,
# then ASK whether to also delete your workspaces and metadata.
# Works from a clone (./uninstall.sh) as well as via curl | bash.
# Option: --purge (also delete the config, without asking / non-interactively).
set -euo pipefail

BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
COMP_DIR="${DATA_DIR}/bash-completion/completions"
LIB_DIR="${DATA_DIR}/ws-cli"
TARGET="$BIN_DIR/ws"

CONFIG_DIR="${WS_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/ws}"

PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1

# 1) symlink: removed only if it points to a ws.py we manage
if [ -L "$TARGET" ]; then
    dest="$(readlink -f "$TARGET" 2>/dev/null || true)"
    case "$dest" in
        */ws.py) rm -f "$TARGET"; echo "✓ removed: $TARGET" ;;
        *) echo "⚠ $TARGET points to $dest (unknown) — left intact." >&2 ;;
    esac
elif [ -e "$TARGET" ]; then
    echo "⚠ $TARGET exists but is not a symlink — left intact." >&2
else
    echo "· no ws symlink in $BIN_DIR"
fi

# 2) ws.py installed in remote mode
if [ -d "$LIB_DIR" ]; then
    rm -rf "$LIB_DIR"
    echo "✓ removed: $LIB_DIR"
fi

# 3) completion
if [ -f "$COMP_DIR/ws" ]; then
    rm -f "$COMP_DIR/ws"
    echo "✓ removed: $COMP_DIR/ws"
else
    echo "· no ws completion in $COMP_DIR"
fi

# 4) configuration / data — deleted on request only
if [ -d "$CONFIG_DIR" ]; then
    if [ "$PURGE" = 1 ]; then
        rm -rf "$CONFIG_DIR"
        echo "✓ configuration removed: $CONFIG_DIR"
    elif [ -t 0 ]; then
        printf "Also delete your workspaces and metadata (%s)? [y/N] " "$CONFIG_DIR"
        read -r ans
        case "$ans" in
            y|Y|yes) rm -rf "$CONFIG_DIR"; echo "✓ configuration removed: $CONFIG_DIR" ;;
            *) echo "· configuration kept: $CONFIG_DIR" ;;
        esac
    else
        echo "· configuration kept: $CONFIG_DIR (use --purge to delete it)"
    fi
else
    echo "· no configuration found ($CONFIG_DIR)"
fi

echo "Uninstalled."
