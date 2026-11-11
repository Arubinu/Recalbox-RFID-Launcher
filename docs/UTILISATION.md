# Utilisation

## Le principe

* Chaque badge est associé à **un jeu** (système + chemin du jeu).
* Scanner un badge lance le jeu correspondant.
* Le **bouton** sert uniquement à créer ou supprimer une association.

Les associations sont stockées dans
`/recalbox/share/system/rfid/tags.json`, un fichier texte lisible et
sauvegardable (voir plus bas).

## L'interface web

Ouvrez **`http://recalbox.local:8080`** (ou l'adresse IP de la Recalbox) depuis
n'importe quel navigateur du réseau : téléphone, tablette, PC.

> L'installation et les mises à jour sont automatiques au démarrage de Recalbox
> (voir `INSTALLATION.md`). L'interface web sert à **vérifier**, **gérer les
> badges** et **dépanner** ; elle permet aussi de réinstaller à la main si
> l'automatique a échoué.

| Section | Actions |
| --- | --- |
| Installation & mise à jour | installer / mettre à jour (ZIP depuis le PC ou URL), redémarrer Recalbox, suivre le journal en direct |
| Matériel | état du bus SPI, du lecteur RC522, du bouton, du frontend |
| Badges | associer le prochain badge au jeu sélectionné, ajouter/modifier/supprimer, export et import CSV |
| Service | démarrer / arrêter / redémarrer, consulter le journal |

Points utiles :

* **Associer sans le bouton** : sélectionnez un jeu dans Recalbox, ouvrez la page
  (le jeu sélectionné s'affiche), cliquez sur « Associer le prochain badge
  scanné », puis scannez le badge. Ou saisissez directement l'UID (visible dans
  « Dernier badge » ou dans le journal).
* **Débogage › Simuler le scan** : rejoue un UID sans badge physique, pratique
  pour tester une association.
* **Export CSV** : télécharge la liste des badges (sauvegarde).
* **Import CSV** : restaure une sauvegarde ou prépare une série de badges dans un
  tableur.
* La page se rafraîchit toute seule (état du service, mode armé, dernier badge).

**Sécurité** : la page est ouverte à tout le réseau local, comme la console
elle-même. Pour la protéger, mettez un mot de passe dans `config.ini` :

```ini
[web]
password = monmotdepasse
```

puis `rfidctl restart` (le navigateur demandera le mot de passe, l'utilisateur
n'a pas d'importance). Pour désactiver complètement l'interface :
`enabled = 0`.

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
remplace l'ancienne.

## Lancer un jeu

Scannez le badge. Le frontend affiche l'écran de chargement du jeu (nom,
jaquette) puis lance l'émulateur.

* Si un jeu est déjà en cours, le scan est ignoré (option
  `ignore_when_game_running`). Quittez d'abord le jeu.
* Un badge inconnu est signalé par deux bips graves et une ligne dans le
  journal.

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
| `[button] enabled` | `1` | `0` pour désactiver le bouton |
| `[button] pin` | `17` | broche du bouton (BCM) |
| `[button] long_press_s` | `2.0` | durée d'un appui long |
| `[button] arm_timeout_s` | `30` | délai pour scanner après un appui |
| `[button] debounce_ms` | `40` | anti-rebond |
| `[launch] udp_host` / `udp_port` | `127.0.0.1` / `1337` | interface du frontend |
| `[launch] ignore_when_game_running` | `1` | ignore les scans pendant un jeu |
| `[launch] launch_after_bind` | `1` | lance le jeu après une association |
| `[feedback] sound` | `1` | bips |
| `[feedback] sound_player` | `auto` | `paplay`, `aplay` ou `none` |
| `[web] enabled` | `1` | interface web |
| `[web] host` | `0.0.0.0` | écoute sur le réseau local |
| `[web] port` | `8080` | port de l'interface |
| `[web] password` | vide | mot de passe HTTP Basic (facultatif) |
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
