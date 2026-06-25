#!/usr/bin/env bash
# Désinstalle `ws` : retire le symlink, la complétion et (mode distant) ws.py,
# puis DEMANDE si vous voulez aussi supprimer vos workspaces et métadonnées.
# Marche en local (./uninstall.sh) comme via curl | bash.
# Option : --purge (supprime aussi la config sans demander / en non-interactif).
set -euo pipefail

BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
COMP_DIR="${DATA_DIR}/bash-completion/completions"
LIB_DIR="${DATA_DIR}/ws-cli"
TARGET="$BIN_DIR/ws"

CONFIG_DIR="${WS_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/ws}"

PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1

# 1) symlink : on le retire s'il pointe vers un ws.py qu'on gère
if [ -L "$TARGET" ]; then
    dest="$(readlink -f "$TARGET" 2>/dev/null || true)"
    case "$dest" in
        */ws.py) rm -f "$TARGET"; echo "✓ supprimé : $TARGET" ;;
        *) echo "⚠ $TARGET pointe vers $dest (inconnu) — laissé intact." >&2 ;;
    esac
elif [ -e "$TARGET" ]; then
    echo "⚠ $TARGET existe mais n'est pas un symlink — laissé intact." >&2
else
    echo "· aucun symlink ws dans $BIN_DIR"
fi

# 2) ws.py installé en mode distant
if [ -d "$LIB_DIR" ]; then
    rm -rf "$LIB_DIR"
    echo "✓ supprimé : $LIB_DIR"
fi

# 3) complétion
if [ -f "$COMP_DIR/ws" ]; then
    rm -f "$COMP_DIR/ws"
    echo "✓ supprimé : $COMP_DIR/ws"
else
    echo "· aucune complétion ws dans $COMP_DIR"
fi

# 4) configuration / données — sur demande uniquement
if [ -d "$CONFIG_DIR" ]; then
    if [ "$PURGE" = 1 ]; then
        rm -rf "$CONFIG_DIR"
        echo "✓ configuration supprimée : $CONFIG_DIR"
    elif [ -t 0 ]; then
        printf "Supprimer aussi vos workspaces et métadonnées (%s) ? [y/N] " "$CONFIG_DIR"
        read -r ans
        case "$ans" in
            y|Y|yes|o|O|oui) rm -rf "$CONFIG_DIR"; echo "✓ configuration supprimée : $CONFIG_DIR" ;;
            *) echo "· configuration conservée : $CONFIG_DIR" ;;
        esac
    else
        echo "· configuration conservée : $CONFIG_DIR (non interactif ; --purge pour la supprimer)"
    fi
else
    echo "· aucune configuration trouvée ($CONFIG_DIR)"
fi

echo "Désinstallé."
