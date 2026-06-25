# `ws` — Gestionnaire de workspaces VSCode en CLI

> Spec v0.1 — document de travail. Statut : à valider.

## 1. Objectif

Un CLI léger pour **créer, administrer et ouvrir** des workspaces multi-dossiers VSCode,
avec autocomplétion bash à chaque commande.

```bash
ws open platform        # ouvre platform-api + platform-infra dans une seule fenêtre VSCode
ws list                 # liste les workspaces (nom, tags, nb dossiers, description)
ws new iris-model ~/dev/iris-train ~/dev/iris-serve --tag ml --desc "Modèle iris"
ws edit platform        # édite le workspace
ws delete old-thing     # supprime
```

### Non-objectifs

- Ne **pas** réimplémenter le multi-root de VSCode : on s'appuie sur le format natif `.code-workspace`.
- Pas de gestion de repos git / clone (c'est le rôle de `ghq`, `gh repo clone`, etc.).
- Pas (en v1) de complétion zsh/fish — l'environnement cible est **bash**.

## 2. Décision structurante

⚠️ `code dossierA dossierB` n'ouvre **pas** un workspace multi-root : ça ouvre des fenêtres
séparées. Le seul moyen fiable d'avoir **une fenêtre unique avec plusieurs dossiers** est un
fichier `.code-workspace`. Toute l'architecture en découle :

> **Un workspace `ws` = un fichier `.code-workspace` natif + une entrée de métadonnées.**

## 3. Stockage

Répertoire de config (respecte `$XDG_CONFIG_HOME`, défaut `~/.config`) :

```
$XDG_CONFIG_HOME/ws/
├── workspaces/
│   ├── platform.code-workspace
│   └── iris-model.code-workspace
└── index.json            # métadonnées par nom de workspace
```

Override possible via `$WS_HOME` (utile pour les tests).

### 3.1 Fichier `.code-workspace` (source de vérité : existence + dossiers)

Format 100 % natif VSCode, jamais pollué par `ws` (on ne touche que `folders`) :

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

- Chemins **absolus** (robuste, indépendant du cwd). Les `~` et variables d'env sont résolus
  à la création.
- Le **nom du workspace = le `stem` du fichier** (`platform.code-workspace` → `platform`).
- On peut éditer le fichier dans VSCode (ajout de dossiers, settings, extensions, launch) :
  `ws` n'écrase jamais ces clés, il édite seulement `folders` de façon chirurgicale.

### 3.2 `index.json` (métadonnées)

```jsonc
{
  "platform": {
    "description": "API + infra de la plateforme",
    "tags": ["platform", "infra"],
    "created": "2026-06-25T10:00:00Z",
    "last_opened": "2026-06-25T14:30:00Z"
  },
  "iris-model": { "description": "Modèle iris", "tags": ["ml"] }
}
```

Règles de réconciliation (le dossier `workspaces/` prime) :
- Un `.code-workspace` **sans** entrée d'index → affiché avec méta vide (ex. « Save Workspace As » depuis VSCode).
- Une entrée d'index **sans** fichier → orpheline, ignorée à l'affichage. ⚠️ **Décision révisée
  (impl. v1)** : l'orpheline est **conservée** et non purgée automatiquement — la purge en aveugle
  à chaque écriture détruisait les métadonnées d'un workspace temporairement absent (FS réseau,
  fichier en cours d'édition/renommé à la main). Seuls `delete`/`rename` retirent explicitement
  une clé. Un `ws prune` dédié reste possible (post-v1) pour un nettoyage volontaire.
- Écritures **atomiques** (fichier temporaire + `rename`) pour ne jamais corrompre l'index.

## 4. Surface CLI

| Commande | Description | Options clés |
|---|---|---|
| `ws new <nom> <dir…>` | Crée un workspace | `--desc TEXT`, `--tag T` (répétable), `--open`, `--force` (dossiers manquants) |
| `ws open [nom]` | Ouvre le workspace ; sans `nom` → picker `fzf` | `-n` nouvelle fenêtre, `-r` réutiliser |
| `ws list` | Liste : `NOM  TAGS  #DOSSIERS  DESCRIPTION` | `--tag T` (filtre), `--json`, `-v` (chemins) |
| `ws show <nom>` | Détail d'un workspace (dossiers + méta) | `--json` |
| `ws edit <nom>` | Ouvre le `.code-workspace` dans `$EDITOR` (défaut `code -r`) | `--editor CMD` |
| `ws add <nom> <dir…>` | Ajoute des dossiers (dédup) | `--force` |
| `ws rm-folder <nom> <dir…>` | Retire des dossiers | |
| `ws set <nom>` | Édite les métadonnées | `--desc`, `--add-tag`, `--rm-tag` |
| `ws rename <old> <new>` | Renomme (fichier + clé d'index) | |
| `ws delete <nom>` | Supprime (fichier + entrée d'index) | `-y` (sans confirmation) |
| `ws path <nom>` | Imprime le chemin du `.code-workspace` (scripting) | |
| `ws completion bash` | Imprime le script de complétion | |

### Comportements

- **`ws open`** : `code [-n|-r] <path>`, puis met à jour `last_opened`. Sans flag, on laisse le
  comportement par défaut de `code` (réutilise la fenêtre courante si pertinent).
- **`ws new`** : valide le nom (`[A-Za-z0-9._-]+`, unique), résout/déduplique/vérifie les dossiers
  (avertit si un dossier manque, sauf `--force`), écrit le fichier puis l'entrée d'index.
- **Codes de sortie** : `0` ok, `1` erreur générique, `2` mauvais usage, `3` workspace introuvable,
  `4` workspace déjà existant. (Facilite le scripting.)

## 5. Complétion bash

Fonction `_ws` (issue de `ws completion bash`, posée dans
`~/.local/share/bash-completion/completions/ws`) :

- 1er token → sous-commandes (`open`, `list`, `new`, …).
- `open|edit|delete|rename|path|show|set|add|rm-folder <TAB>` → **noms de workspaces** (scan de `workspaces/`).
- `--tag <TAB>` → tags existants (extraits de `index.json`).
- `new <nom> <TAB>` → complétion de **dossiers** standard.

La source des noms est le scan du dossier `workspaces/` → toujours à jour, y compris pour les
workspaces créés depuis VSCode.

## 6. Intégration `fzf` (`ws open` sans argument)

`ws open` → `fzf` sur la liste des workspaces, avec fenêtre de preview affichant description +
dossiers (via `ws show`). Entrée = ouvrir. Repli propre si `fzf` absent (message + `ws list`).

## 7. Installation & distribution

Cible : **partage via GitHub, install facile, zéro dépendance tierce**.

- **Chemin principal** : `git clone` + `./install.sh`
  - symlink de `ws` (script Python mono-fichier, exécutable) dans `~/.local/bin`,
  - pose la complétion dans `~/.local/share/bash-completion/completions/ws`,
  - vérifie/avertit que `~/.local/bin` est dans le `PATH`.
- **Bonus** : `pyproject.toml` avec `[project.scripts] ws = "..."` pour les machines qui
  préfèrent `pipx install git+…` ou `uv tool install`.
- Aucun `pip`/`venv` requis sur la machine de dev (pipx y est absent de toute façon).

## 8. Choix techniques

- **Langage** : Python 3.10+, **stdlib uniquement** (`argparse`, `json`, `pathlib`, `subprocess`,
  `os`, `shutil`). Pas de TOML (donc pas besoin d'un writer tiers) : tout est en JSON.
- **Mono-fichier** : un seul exécutable `ws` → install/partage triviaux.
- **Pourquoi pas Go** : meilleur pour des binaires uniques en release, mais la toolchain est
  absente et Python suffit largement pour un outil qui orchestre `code` + manipule du JSON.
  À reconsidérer si on veut des releases binaires GitHub Actions.

## 9. Cas limites & décisions

- **Nom déjà pris** → erreur (code 4), suggère `ws add`.
- **Dossier inexistant à la création** → avertissement, bloque sauf `--force`.
- **Dossier manquant à l'ouverture** → on ouvre quand même (VSCode l'affiche grisé), avertit.
- **`~` / `$VAR` dans les args** → résolus et stockés en absolu.
- **Drift fichier/index** → `ws list` se base sur les fichiers ; entrées d'index orphelines ignorées
  à l'affichage mais conservées (cf. §3.2, sécurité des données ; jamais détruites en aveugle).
- **`ws import <path>`** (post-v1) : adopter un `.code-workspace` existant situé ailleurs.

## 10. Roadmap

- **v1** : `new`/`open`/`list`/`show`/`edit`/`add`/`rm-folder`/`set`/`rename`/`delete`/`path`
  + métadonnées (desc, tags) + complétion bash + picker `fzf` + `install.sh`.
- **v1.1** : `ws import`, tri par `last_opened`, filtre `--tag` enrichi, `pyproject.toml`.
- **v2** : complétion zsh/fish, releases binaires, tests d'intégration.
