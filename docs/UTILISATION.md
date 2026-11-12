# Utilisation

## Le principe

* Chaque badge est associé à **un jeu** (système + chemin du jeu).
* Scanner un badge lance le jeu correspondant.
* Le **bouton** sert uniquement à créer ou supprimer une association.

Les associations sont stockées dans
`/recalbox/share/system/rfid/tags.json`, un fichier texte lisible et
sauvegardable (voir plus bas).

## L'installateur (`installer.html`)

Double-cliquez sur **`installer.html`** (à la racine du projet, sur votre PC) :
la page s'ouvre en local (`file://`) et se connecte à l'agent WebSocket de la
Recalbox. Aucune interface n'est hébergée par la Recalbox, aucun serveur n'est
nécessaire sur le PC.

La page tient sur un écran, sans défilement, et commence par un **choix** :

| Écran | À quoi ça sert |
| --- | --- |
| **Accueil** | deux tuiles : *Installer sur la Recalbox* ou *Gérer mes badges* |
| **Installer** | télécharger le fichier `.cmd` (3 étapes affichées), plus la copie depuis le navigateur en repli |
| **Se connecter** | adresse, port : l'autorisation se donne en gardant le bouton du boîtier appuyé 3 secondes |
| **Gestion** | trois onglets : **Badges**, **Matériel**, **Maintenance** |

Dans **Gestion**, le bandeau du haut donne l'état (connecté, service actif) et le
bouton **Déconnecter** revient à l'écran de connexion.

Champs de connexion :

| Champ | Valeur |
| --- | --- |
| Adresse | `recalbox.local` ou l'IP (menu `RÉSEAU` > `INFORMATIONS`) |
| Port | `8765` (modifiable dans `[agent]` de `config.ini`) |
| Autorisation | **rien à saisir** : cliquez sur « Se connecter », puis **gardez le bouton du boîtier appuyé 3 secondes** pendant le compte à rebours. Une seule demande à la fois, valable 30 s |

L'autorisation est **confirmée physiquement** : la page dépose une demande (une
seule à la fois, 30 s), le service de la Recalbox attend un appui long (3 s) sur
le bouton, puis autorise ce poste. Un appui commencé avant la demande, ou destiné
à une demande précédente, est refusé : on ne peut donc pas valider une demande
qui n'était pas la vôtre. La demande est aussi refusée si le service du lecteur
n'est pas démarré.

Aucun jeton n'est transmis, aucun fichier n'est écrit : l'agent tire un secret de
session en mémoire à chaque démarrage, et la page le garde dans le navigateur
(localStorage). Une actualisation de la page reconnecte donc sans rien faire. En
revanche, un **redémarrage de la Recalbox**, un redémarrage du service ou une
**mise à jour** efface ce secret : la page l'annonce (« la Recalbox demande une
nouvelle autorisation ») et il suffit de garder le bouton appuyé 3 secondes une
fois de plus.

L'installateur `.cmd` relancé après l'installation rouvre la page avec
`#host=…&port=…` : l'adresse et le port sont déjà remplis, l'autorisation se
donne toujours au bouton.

Si la page n'arrive pas à déposer sa demande, un seul repli existe : en SSH,
`rfidctl pair`. Cette commande réouvre seulement la fenêtre de 30 s ; **elle
n'affiche aucun jeton** et ne remplace pas l'appui sur le bouton.

Le bouton **« Faire un diagnostic »** (écran *Se connecter* → *La connexion ne
marche pas ?*) télécharge `diagnostic-recalbox.cmd` : double-clic, et il affiche
l'état des ports, du partage, des fichiers et des journaux de la Recalbox.

| Onglet | Actions |
| --- | --- |
| Badges | associer le prochain badge au jeu sélectionné, effacer, tableau des badges, export et import CSV |
| Matériel | état du bus SPI, du lecteur RC522, du bouton, du lancement des jeux + verdict et action à faire ; bouton **Tester avec un badge** (5 s) qui dit si une carte est vue, lue, ou pas détectée du tout |
| Maintenance | installer / mettre à jour (dossier du partage, ZIP depuis le PC, URL), redémarrer Recalbox, démarrer/arrêter/redémarrer le service, journaux en direct |

Points utiles :

* **Fichier unique** : si vous avez ouvert
  `dist\recalbox-rfid-installer-<version>.html`, une première section permet de
  **copier les fichiers** sur `\\RECALBOX\share` directement depuis la page
  (Edge/Chrome) : choisissez le partage, tout est écrit, puis redémarrez.
* **Associer sans le bouton** : sélectionnez un jeu dans Recalbox, ouvrez la page
  (le jeu sélectionné s'affiche), cliquez sur « Associer le prochain badge
  scanné », puis scannez le badge.
* **Débogage › Simuler le scan** : rejoue un UID sans badge physique, pratique
  pour tester une association.
* **Export CSV** : télécharge la liste des badges (sauvegarde).
* **Import CSV** : restaure une sauvegarde ou prépare une série de badges dans un
  tableur.
* La page se rafraîchit toute seule (état du service, mode armé, dernier badge).
* **Coupure de connexion** (redémarrage de la Recalbox, réseau, agent relancé) :
  le tableau de bord reste affiché mais grisé, un bandeau « hors ligne » indique
  « Connexion perdue depuis N s » et la page **se reconnecte automatiquement**
  dès que l'agent revient ; le retour est annoncé (« Connexion rétablie »). Le
  bouton « Réessayer maintenant » force une tentative immédiate.
* **Autorisation perdue** (Recalbox redémarrée, service relancé, programme mis à
  jour) : le secret de session a changé, la page l'indique et il suffit de
  garder le bouton du boîtier appuyé 3 secondes pour continuer.

**Sécurité** : l'agent n'accepte que les commandes d'une session autorisée, et
cette autorisation ne s'obtient qu'en gardant le bouton du boîtier appuyé
3 secondes :

* il n'y a **aucun secret sur le partage** : le secret de session est tiré au
  hasard à chaque démarrage de l'agent et ne vit qu'en mémoire ;
* l'agent n'écoute que le réseau local et refuse les pages web : `installer.html`
  doit être ouverte depuis le disque (`file://`) ;
* ne l'exposez jamais sur Internet : pour un accès distant, utilisez un VPN
  (WireGuard, Tailscale…) ;
* pour retirer l'autorisation d'un poste : redémarrez l'agent ou le service — un
  nouveau secret est tiré, un appui de 3 s sur le bouton est redemandé ;
* pour désactiver complètement l'agent : `enabled = 0` dans `[agent]`.

## Associer un badge

1. Dans Recalbox, placez le curseur sur le jeu voulu dans la liste (le jeu est
   « sélectionné », il n'est pas lancé). Évitez un dossier.
2. **Appui court** sur le bouton.
   * 1 bip aigu : c'est armé, vous avez **30 secondes** pour scanner.
   * 2 bips graves : aucun jeu sélectionné (ou un dossier) — recommencez.
3. **Scannez le badge**.
   * 2 bips aigus : association enregistrée, le jeu se lance pour confirmer.
   * 2 bips graves : problème (badge illisible, base non accessible…).

Un badge déjà associé est simplement réassocié : la nouvelle association
remplace l'ancienne. La fenêtre d'attente est de **10 secondes**
(`[button] arm_timeout_s`).

## Lancer un jeu

Scannez le badge. Le frontend affiche l'écran de chargement du jeu (nom,
jaquette) puis lance l'émulateur.

* Si un jeu est déjà en cours, le scan est ignoré (option
  `ignore_when_game_running`). Quittez d'abord le jeu.
* Un badge inconnu est signalé par deux bips graves et une ligne dans le
  journal.
* L'option `[launch] action = none` remplace le lancement par un simple bip de
  confirmation : le badge est reconnu, rien n'est lancé.

## Mode « cartouche » (badge laissé sur le lecteur)

Laisser le badge en place ne déclenche l'action **qu'une seule fois** : elle
n'est pas répétée tant que le badge reste posé. Pour la refaire (ou pour la
refaire après avoir changer de jeu), il suffit de **retirer le badge environ une
seconde puis de le reposer** (`[rfid] rearm_absent_ms`, `1200` ms par défaut).

C'est ce qui permet d'utiliser un badge comme une cartouche : on le pose, on
joue, on le laisse. Un autre badge posé à la place agit immédiatement.

## Effacer un badge

1. **Appui long** (environ 2 secondes) sur le bouton → 2 bips graves.
2. Scannez le badge à supprimer → confirmation sonore.

Astuce : un appui long inutile expire au bout de 30 secondes (3 bips
descendants).

## Le son

Les bips sont générés à la volée (fichiers WAV dans `/tmp`) et joués par
`paplay` (PulseAudio) ou `aplay` (ALSA). Pour les couper :

```ini
[feedback]
sound = 0
```

puis `rfidctl restart`.

## Commandes

Le raccourci est `/recalbox/share/system/rfid/rfidctl` :

```sh
RFID=/recalbox/share/system/rfid/rfidctl

$RFID test              # diagnostic materiel (SPI, badge, bouton, frontend)
$RFID list              # associations enregistrees
$RFID add <UID> --current
$RFID add <UID> <systeme> <jeu> [nom]
$RFID remove <UID>
$RFID export <fichier.csv>
$RFID import <fichier.csv> [--keep]
$RFID status            # etat du service (PID, badge, mode arme)
$RFID start|stop|restart
$RFID logs              # 40 dernieres lignes du journal
$RFID frontend          # Recalbox sait-il lancer un jeu par script ?
$RFID self-update [URL] # mise a jour
$RFID simulate          # simulation (PC, sans materiel)
$RFID config            # configuration effective
```

L'UID d'un badge est affiché par `rfidctl test` ou dans le journal après un
scan, sous la forme `A1:B2:C3:D4` (les formats `A1B2C3D4`, `a1-b2-c3-d4`,
`A1 B2 C3 D4` sont acceptés par les commandes).

### Ajouter un badge au jeu sélectionné, sans bouton

```sh
$RFID add A1B2C3D4 --current
```

Le jeu en cours de sélection dans Recalbox est lu dans `/tmp/es_state.inf`.
Pratique pour préparer une série de badges depuis un téléphone en SSH.

### Le fichier CSV

```csv
uid;system;game;name
A1:B2:C3:D4;snes;Super Mario World.smc;Super Mario World
01:02:03:04:05:06:07;nes;Zelda.nes;Zelda
```

* Séparateur `;` (comme Excel en français), le séparateur `,` est aussi accepté
  à l'import.
* `system` : identifiant court du système Recalbox (`snes`, `nes`, `megadrive`,
  `arcade`, `gba`…). Il est visible dans le journal lors d'une association.
* `game` : chemin du jeu **relatif au dossier du système**, extension comprise.
  Exemples : `Super Mario World.smc`, `Classiques/jeu.smc`.
* `name` : nom lisible (facultatif, utilisé par `list`).

## Configuration

Fichier : `/recalbox/share/system/rfid/config.ini` (modifiable depuis le
partage réseau, avec le Bloc-notes par exemple). Après modification :

```sh
/recalbox/share/system/rfid/rfidctl restart
```

| Clé | Défaut | Rôle |
| --- | --- | --- |
| `[general] log_level` | `INFO` | `DEBUG` pour tracer en détail |
| `[general] log_max_bytes` | `1048576` | rotation du journal |
| `[rfid] spi_device` | `/dev/spidev0.0` | port du lecteur (CE0) |
| `[rfid] spi_speed_hz` | `1000000` | baisser à `500000` en cas de fils longs |
| `[rfid] reset_pin` | `25` | broche RST du RC522 (`-1` si non branché) |
| `[rfid] poll_interval_ms` | `150` | fréquence d'interrogation du lecteur |
| `[rfid] same_tag_cooldown_s` | `2.5` | ignore les relectures du même badge |
| `[rfid] rearm_absent_ms` | `1200` | **mode cartouche** : temps d'absence du badge (ms) avant de pouvoir refaire l'action |
| `[button] enabled` | `1` | `0` pour désactiver le bouton |
| `[button] pin` | `17` | broche du bouton (BCM) |
| `[button] long_press_s` | `2.0` | durée d'un appui long |
| `[button] hold_press_s` | `3.0` | durée de l'appui qui autorise un poste |
| `[button] arm_timeout_s` | `10` | délai pour scanner après un appui |
| `[button] debounce_ms` | `40` | anti-rebond |
| `[launch] udp_host` / `udp_port` | `127.0.0.1` / `1337` | interface du frontend |
| `[launch] action` | `launch` | `launch` = lance le jeu ; `none` = bip seulement (mode cartouche) |
| `[launch] ignore_when_game_running` | `1` | ignore les scans pendant un jeu |
| `[launch] launch_after_bind` | `1` | lance le jeu après une association |
| `[feedback] sound` | `1` | bips |
| `[feedback] sound_player` | `auto` | `paplay`, `aplay` ou `none` |
| `[agent] enabled` | `1` | agent WebSocket (installateur / gestion) |
| `[agent] port` | `8765` | port de l'agent |
| `[update] url` | vide | URL du ZIP de mise à jour |
| `[update] check_on_start` | `0` | réservé |

## Sauvegarde et restauration

* **Sauvegarde** : copiez `/recalbox/share/system/rfid/tags.json` (et
  éventuellement `config.ini`) où vous voulez. `rfidctl export` produit aussi un
  CSV.
* **Restauration** : recopiez le fichier, ou `rfidctl import fichier.csv`.
* À chaque enregistrement, l'ancienne version de `tags.json` est conservée dans
  `tags.json.bak`.

## Journal

```sh
$RFID logs
# ou
cat /recalbox/share/system/rfid/logs/rfid.log
```

Exemples de lignes :

```
2026-01-01 12:00:00 [INFO   ] Lecteur RC522 pret (version 0x92)
2026-01-01 12:00:42 [INFO   ] Badge detecte : A1:B2:C3:D4
2026-01-01 12:00:42 [INFO   ] Commande envoyee : START|snes|Super Mario World.smc
2026-01-01 12:00:42 [INFO   ] Lancement de Super Mario World (snes)
```
