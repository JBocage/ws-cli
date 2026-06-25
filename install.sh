#!/usr/bin/env bash
# Installe `ws`. Deux modes :
#   - depuis un clone   : ./install.sh           (symlink vers le ws.py local)
#   - via curl | bash   : curl -fsSL <raw>/install.sh | bash   (télécharge ws.py)
# Options : --force (écrase un ws existant non géré par ce script)
set -euo pipefail

REPO="JBocage/ws-cli"
BRANCH="main"
RAW="https://raw.githubusercontent.com/${REPO}/${BRANCH}"

BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
COMP_DIR="${DATA_DIR}/bash-completion/completions"
LIB_DIR="${DATA_DIR}/ws-cli"          # emplacement de ws.py en mode distant

FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

# --- prérequis ------------------------------------------------------------- #
if ! command -v python3 >/dev/null 2>&1; then
    echo "✗ python3 introuvable (Python 3.10+ requis)." >&2
    exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    echo "✗ Python 3.10+ requis (trouvé : $(python3 --version 2>&1))." >&2
    exit 1
fi

mkdir -p "$BIN_DIR" "$COMP_DIR"
TARGET="$BIN_DIR/ws"

# refuse d'écraser un ws non géré par ce script (sauf --force)
if [ -e "$TARGET" ] && [ ! -L "$TARGET" ] && [ "$FORCE" != 1 ]; then
    echo "✗ $TARGET existe déjà (fichier, pas un symlink). Relancez avec --force." >&2
    exit 1
fi

# --- source : clone local sinon téléchargement ----------------------------- #
SELF="${BASH_SOURCE[0]:-}"
SCRIPT_DIR=""
if [ -n "$SELF" ] && [ "$SELF" != "bash" ] && [ "$SELF" != "/dev/stdin" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$SELF")" 2>/dev/null && pwd || true)"
fi

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/ws.py" ]; then
    SRC="$SCRIPT_DIR/ws.py"
    echo "→ Installation depuis le dépôt local ($SRC)"
else
    echo "→ Téléchargement de ws depuis github.com/$REPO …"
    mkdir -p "$LIB_DIR"
    fetch() {  # fetch URL DEST
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL "$1" -o "$2"
        elif command -v wget >/dev/null 2>&1; then
            wget -qO "$2" "$1"
        else
            echo "✗ curl ou wget requis pour l'installation distante." >&2
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

# --- complétion bash ------------------------------------------------------- #
"$SRC" completion bash > "$COMP_DIR/ws"
echo "✓ complétion bash → $COMP_DIR/ws"

# --- PATH ------------------------------------------------------------------ #
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        echo "⚠ $BIN_DIR n'est pas dans le PATH."
        echo "  Ajoutez à votre ~/.bashrc : export PATH=\"\$HOME/.local/bin:\$PATH\""
        ;;
esac

echo
echo "Terminé. Ouvrez un nouveau shell (ou : source \"$COMP_DIR/ws\")."
if [ -f "$LIB_DIR/uninstall.sh" ]; then
    echo "Désinstallation : curl -fsSL $RAW/uninstall.sh | bash   (ou : $LIB_DIR/uninstall.sh)"
else
    echo "Désinstallation : ./uninstall.sh"
fi
