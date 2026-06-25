# `ws` — gestionnaire de workspaces VSCode en CLI

Crée, administre et ouvre des **workspaces multi-dossiers VSCode** en une commande,
avec autocomplétion bash. Un workspace `ws` = un fichier `.code-workspace` natif
(source de vérité) + une entrée de métadonnées.

```bash
ws new platform ~/dev/platform-api ~/dev/platform-infra --tag infra --desc "API + infra"
ws open platform     # une seule fenêtre VSCode, les deux dossiers
ws list              # NOM  TAGS  #DOSSIERS  DESCRIPTION
ws open              # sans nom → picker fzf avec preview
```

## Installation

```bash
git clone https://github.com/JBocage/ws-cli.git && cd ws-cli
./install.sh
```

`install.sh` pose un symlink `ws` dans `~/.local/bin`, installe la complétion bash
dans `~/.local/share/bash-completion/completions/ws`, et vérifie le `PATH`.
Ouvrez ensuite un nouveau shell.

Alternative (machines avec `uv` ou `pipx`) :

```bash
uv tool install git+https://github.com/JBocage/ws-cli
# ou : pipx install git+https://github.com/JBocage/ws-cli
```

Aucune dépendance tierce au runtime — Python 3.10+ et la stdlib suffisent.

### Désinstallation

```bash
./uninstall.sh        # retire le symlink + la complétion, puis DEMANDE
                      # si vous voulez aussi supprimer vos workspaces/métadonnées
                      # (--purge pour forcer en non-interactif)
```

Installé via uv : `uv tool uninstall ws-vscode`.

## Commandes

| Commande | Description |
|---|---|
| `ws new <nom> <dir…>` | crée un workspace (`--desc`, `--tag`, `--open`, `--force`) |
| `ws open [nom]` | ouvre (sans nom → fzf) ; `-n` nouvelle fenêtre, `-r` réutilise |
| `ws list` | liste (`--tag`, `--json`, `-v` chemins) |
| `ws show <nom>` | détail (`--json`) |
| `ws edit <nom>` | ouvre le `.code-workspace` dans `$EDITOR` (défaut `code -r`) |
| `ws add <nom> <dir…>` | ajoute des dossiers (dédup, `--force`) |
| `ws rm-folder <nom> <dir…>` | retire des dossiers |
| `ws set <nom>` | métadonnées (`--desc`, `--add-tag`, `--rm-tag`) |
| `ws rename <old> <new>` | renomme |
| `ws delete <nom>` | supprime (`-y`) |
| `ws path <nom>` | imprime le chemin du `.code-workspace` |
| `ws completion bash` | imprime le script de complétion |

Codes de sortie : `0` ok, `1` erreur, `2` mauvais usage, `3` introuvable, `4` déjà existant.

## Stockage

```
$XDG_CONFIG_HOME/ws/            (défaut ~/.config/ws, override $WS_HOME)
├── workspaces/<nom>.code-workspace   # source de vérité (existence + dossiers)
└── index.json                        # métadonnées (desc, tags, dates)
```

Le dossier `workspaces/` prime : un `.code-workspace` créé depuis VSCode apparaît
automatiquement ; une entrée d'index sans fichier est **ignorée à l'affichage** mais
**conservée** (jamais détruite par une commande sans rapport — sécurité des données).
`ws` n'édite **que** la clé `folders` du fichier — vos `settings`, `extensions`,
`launch` et commentaires sont préservés.

Robustesse : écritures atomiques (`fsync` + `rename`), sauvegarde `index.json.bak`
restaurée automatiquement si `index.json` est corrompu, et verrou inter-processus
pour les écritures concurrentes.

## Développement

```bash
pip install -e ".[dev]"   # ou: uv pip install pytest
pytest
```
