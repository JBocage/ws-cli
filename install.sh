#!/usr/bin/env bash
# Installe `ws` : symlink dans ~/.local/bin + complétion bash.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/ws.py"

BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
COMP_DIR="${HOME}/.local/share/bash-completion/completions"

if [ ! -f "$SRC" ]; then
    echo "✗ introuvable : $SRC" >&2
    exit 1
fi

mkdir -p "$BIN_DIR" "$COMP_DIR"
chmod +x "$SRC"

TARGET="$BIN_DIR/ws"
if { [ -e "$TARGET" ] || [ -L "$TARGET" ]; } \
   && ! { [ -L "$TARGET" ] && [ "$(readlink -f "$TARGET")" = "$(readlink -f "$SRC")" ]; } \
   && [ "${1:-}" != "--force" ]; then
    echo "✗ $TARGET existe déjà et ne pointe pas vers ce dépôt." >&2
    echo "  Relancez avec --force pour l'écraser." >&2
    exit 1
fi
ln -sf "$SRC" "$TARGET"
echo "✓ ws → $TARGET"

"$SRC" completion bash > "$COMP_DIR/ws"
echo "✓ complétion bash → $COMP_DIR/ws"

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        echo "⚠ $BIN_DIR n'est pas dans le PATH."
        echo "  Ajoutez à votre ~/.bashrc : export PATH=\"\$HOME/.local/bin:\$PATH\""
        ;;
esac

echo "Terminé. Ouvrez un nouveau shell (ou : source \"$COMP_DIR/ws\")."
echo "Pour désinstaller : ./uninstall.sh"
