#!/usr/bin/env bash
# Désinstalle `ws` : retire le symlink et la complétion posés par install.sh,
# puis DEMANDE si vous voulez aussi supprimer vos workspaces et métadonnées.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/ws.py"

BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
COMP_DIR="${HOME}/.local/share/bash-completion/completions"
TARGET="$BIN_DIR/ws"

# Répertoire de config (même logique que ws.py)
CONFIG_DIR="${WS_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/ws}"

# 1) symlink
if [ -L "$TARGET" ] && [ "$(readlink -f "$TARGET")" = "$(readlink -f "$SRC")" ]; then
    rm -f "$TARGET"
    echo "✓ supprimé : $TARGET"
elif [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
    echo "⚠ $TARGET existe mais ne pointe pas vers ce dépôt — laissé intact." >&2
else
    echo "· aucun symlink ws dans $BIN_DIR"
fi

# 2) complétion
if [ -f "$COMP_DIR/ws" ]; then
    rm -f "$COMP_DIR/ws"
    echo "✓ supprimé : $COMP_DIR/ws"
else
    echo "· aucune complétion ws dans $COMP_DIR"
fi

# 3) configuration / données — suppression sur demande seulement
if [ -d "$CONFIG_DIR" ]; then
    if [ "${1:-}" = "--purge" ]; then
        rm -rf "$CONFIG_DIR"
        echo "✓ configuration supprimée : $CONFIG_DIR"
    elif [ -t 0 ]; then
        printf "Supprimer aussi vos workspaces et métadonnées (%s) ? [y/N] " "$CONFIG_DIR"
        read -r ans
        case "$ans" in
            y|Y|yes|o|O|oui)
                rm -rf "$CONFIG_DIR"
                echo "✓ configuration supprimée : $CONFIG_DIR"
                ;;
            *)
                echo "· configuration conservée : $CONFIG_DIR"
                ;;
        esac
    else
        echo "· configuration conservée : $CONFIG_DIR (non interactif ; --purge pour la supprimer)"
    fi
else
    echo "· aucune configuration trouvée ($CONFIG_DIR)"
fi

echo "Désinstallé."
