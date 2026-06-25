# Protocole de test — `ws`

Deux niveaux : **(A)** la suite automatisée, **(B)** un parcours manuel guidé qui
exerce chaque commande et chaque cas limite de la spec. Tout se fait dans un
`$WS_HOME` jetable : **aucune** de tes vraies configs n'est touchée.

---

## A. Suite automatisée (pytest)

```bash
cd /home/julien/dev-perso/ws

# pytest n'est pas requis au runtime ; on l'exécute via uv (présent sur la machine)
uv run --with pytest pytest -v
```

Attendu : **42 passed**. Couvre le parser JSONC (préservation commentaires/settings/`name`),
le CRUD, la réconciliation fichier↔index, l'ouverture (argv de `code` mocké) et la complétion.

---

## B. Parcours manuel

### 0. Bac à sable isolé

```bash
cd /home/julien/dev-perso/ws
export WS_HOME="$(mktemp -d)/ws"      # stockage jetable
unset XDG_CONFIG_HOME
mkdir -p /tmp/ws-demo/api /tmp/ws-demo/infra /tmp/ws-demo/train
alias ws='./ws.py'                    # ou: ./install.sh puis utilise `ws` directement
```

> Pour repartir de zéro à tout moment : `rm -rf "$WS_HOME"`.

### 1. Création (`new`)

```bash
ws new platform /tmp/ws-demo/api /tmp/ws-demo/infra --tag infra --tag platform --desc "API + infra"
ws new iris ~/dev/iris-train --tag ml --desc "Modèle iris"     # ~ doit être résolu en absolu
cat "$WS_HOME/workspaces/platform.code-workspace"               # chemins ABSOLUS, settings:{}
cat "$WS_HOME/index.json"                                       # méta + created
```

À vérifier : fichier `.code-workspace` créé, chemins absolus, `~` résolu, index renseigné.

### 2. Validations & codes de sortie

```bash
ws new "nom invalide!" /tmp/ws-demo/api ; echo "attendu 2 → $?"   # nom invalide
ws new platform /tmp/ws-demo/api        ; echo "attendu 4 → $?"   # déjà existant (+ suggère `ws add`)
ws new brisé /tmp/ws-demo/nexiste-pas   ; echo "attendu 1 → $?"   # dossier manquant, bloqué
ws new brisé /tmp/ws-demo/nexiste-pas --force ; echo "attendu 0 → $?"   # forcé : créé + avertissement
ws show fantome                         ; echo "attendu 3 → $?"   # introuvable
```

Codes attendus : `2`, `4`, `1`, `0`, `3`.

### 3. Liste & détail (`list`, `show`)

```bash
ws list                 # colonnes NOM TAGS #DOSSIERS DESCRIPTION
ws list -v              # + chemins sous chaque ligne (dossiers manquants annotés)
ws list --tag ml        # filtre : n'affiche que `iris`
ws list --json | python3 -m json.tool
ws show platform        # détail lisible + état présent/manquant des dossiers
ws show platform --json
```

### 4. Dossiers (`add`, `rm-folder`) — **préservation chirurgicale**

```bash
# On simule une édition manuelle façon VSCode : commentaires + settings + `name` par dossier
cat > "$WS_HOME/workspaces/platform.code-workspace" <<'EOF'
{
  // mon commentaire perso
  "folders": [
    { "path": "/tmp/ws-demo/api", "name": "API" }
  ],
  "settings": { "editor.tabSize": 2 },  // à préserver
  "extensions": { "recommendations": ["ms-python.python"] }
}
EOF

ws add platform /tmp/ws-demo/infra /tmp/ws-demo/api    # /api déjà présent → ignoré (dédup)
cat "$WS_HOME/workspaces/platform.code-workspace"
```

À vérifier **impérativement** après `add` :
- le commentaire `// mon commentaire perso`, `settings`, `extensions` sont **intacts** ;
- l'entrée existante garde son `"name": "API"` ;
- `/tmp/ws-demo/infra` est ajouté, `/api` n'est **pas** dupliqué.

```bash
ws rm-folder platform /tmp/ws-demo/api    # retrait par chemin
ws add platform /tmp/ws-demo/nexiste --force   # dossier manquant : averti mais ajouté
```

### 5. Métadonnées (`set`)

```bash
ws set platform --desc "Plateforme complète" --add-tag prod
ws set platform --rm-tag infra
ws show platform        # description et tags à jour
```

### 6. Renommage & suppression (`rename`, `delete`)

```bash
ws rename platform plat
ws show plat                                   # méta conservée
ls "$WS_HOME/workspaces/"                       # plat.code-workspace, plus de platform
ws rename plat iris ; echo "attendu 4 → $?"     # collision avec un nom existant
ws delete plat                                  # demande confirmation [y/N] → réponds n puis recommence
ws delete plat -y                               # sans confirmation
ws list                                         # `plat` a disparu
```

### 7. Réconciliation fichier ↔ index (drift)

```bash
# (a) Workspace créé "hors ws" (façon Save Workspace As) : apparaît avec méta vide
echo '{ "folders": [ {"path": "/tmp/ws-demo/train"} ] }' > "$WS_HOME/workspaces/externe.code-workspace"
ws list                                         # `externe` listé, sans tags ni description

# (b) Entrée d'index orpheline : ignorée à l'affichage, mais CONSERVÉE (sécurité)
python3 - <<'EOF'
import json, os
p = os.path.join(os.environ["WS_HOME"], "index.json")
idx = json.load(open(p)); idx["fantome"] = {"tags": ["x"]}; json.dump(idx, open(p, "w"))
EOF
ws list                                         # `fantome` absent de la liste
ws set externe --desc "adopté" ; cat "$WS_HOME/index.json"   # `fantome` toujours là (non détruit)
```

### 8. Ouverture (`open`, `edit`) — nécessite VSCode

> Ces commandes lancent réellement `code`. À faire dans une session graphique.

```bash
ws open externe          # une seule fenêtre VSCode avec le(s) dossier(s)
ws open externe -n       # nouvelle fenêtre
ws show externe --json   # last_opened désormais renseigné
ws edit externe          # ouvre le .code-workspace dans $EDITOR (défaut: code -r)
ws open                  # SANS argument → picker fzf, preview = ws show ; Entrée pour ouvrir
```

À vérifier : `last_opened` mis à jour après `open` ; le picker `fzf` montre la preview ;
si `fzf` est absent, repli propre (message + liste).

### 9. Complétion bash

```bash
ws completion bash | bash -n && echo "script de complétion : syntaxe OK"
ws completion names        # noms (scan du dossier workspaces/)
ws completion tags         # tags (extraits de l'index)

# Test interactif (dans un shell bash) :
source <(ws completion bash)
ws op<TAB>                  # complète "open"
ws open <TAB>              # propose les noms de workspaces
ws set externe --add-tag <TAB>   # propose les tags existants
ws new foo <TAB>           # complète des dossiers
```

### 10. `path` (scripting) & override `$WS_HOME`

```bash
code "$(ws path externe)"   # ouvrir via le chemin imprimé
WS_HOME=/autre/endroit ws list   # l'override change bien le stockage
```

### Nettoyage

```bash
rm -rf "$WS_HOME" /tmp/ws-demo
unalias ws 2>/dev/null
```

---

## Récapitulatif des attendus

| Cas | Attendu |
|---|---|
| Création nominale | fichier `.code-workspace` (chemins absolus) + entrée d'index |
| Nom invalide | code **2** |
| Nom déjà pris | code **4** + suggestion `ws add` |
| Dossier manquant sans `--force` | code **1**, rien créé |
| Workspace introuvable | code **3** |
| `add`/`rm-folder` sur fichier commenté | commentaires/settings/`name` **préservés** |
| Dédup des dossiers | aucun doublon |
| Fichier sans index | listé, méta vide |
| Index orphelin | ignoré à l'affichage, **conservé** (jamais détruit par une commande sans rapport) |
| `open` | lance `code`, met à jour `last_opened` (sauf si `code` échoue) |
