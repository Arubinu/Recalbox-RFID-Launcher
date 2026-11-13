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
| **Gestion** | quatre onglets : **Badges**, **Matériel**, **Options**, **Maintenance** |

Un bouton **`FR` / `EN` / `DE` / `ES` / `IT` / `PT`** (à côté) change la langue de l'interface : un simple clic
passe à la langue suivante et **fixe** le choix. Tant qu'aucune langue n'a été
choisie, la page suit celle du **système** (la première langue disponible dans les
préférences du navigateur ; à défaut, l'anglais). Un **appui long** sur le bouton
revient à la langue du système. Chaque langue est un fichier
`i18n/<code>.json` compilé dans la page ; un texte non traduit reste en français.

Un bouton **soleil / lune** dans l'en-tête change de thème : la page suit d'abord
celui du système, un clic fixe le choix (mémorisé par le navigateur) et un
**appui long** revient au thème du système. La bascule est animée par un cercle
partant du bouton ; le schéma de câblage suit le thème choisi.

Dans **Gestion**, le bandeau du haut donne l'état (connecté, service actif) et le
bouton **Déconnecter** revient à l'écran de connexion.

Champs de connexion :

| Champ | Valeur |
| --- | --- |
| Adresse | `recalbox.local` ou l'IP (menu `RÉSEAU` > `INFORMATIONS`) |
| Port | `8765` (modifiable dans `[agent]` de `config.ini`) |
| Autorisation | **rien à saisir** : cliquez sur « Se connecter », puis **gardez le bouton du boîtier appuyé 3 secondes** pendant le compte à rebours. Une seule demande à la fois, valable 30 s |

L'autorisation est **confirmée physiquement** : la page dépose une demande (une
seule à la fois, 30 s), le service de la Recalbox attend 3 secondes d'appui sur
le bouton, puis autorise ce poste. Un appui commencé avant la demande, ou destiné
à une demande précédente, est refusé : on ne peut donc pas valider une demande
qui n'était pas la vôtre. La demande est aussi refusée si le service du lecteur
n'est pas démarré.

Aucun jeton n'est transmis, aucun fichier n'est écrit : l'agent tire un secret de
session (dans un dossier privé de la Recalbox, hors du partage réseau), et la
page le garde dans le navigateur (localStorage). Une actualisation de la page,
un redémarrage du service ou une **mise à jour** reconnectent donc sans rien
faire : l'autorisation survit. Seul un **redémarrage complet de la Recalbox**
remet le secret à zéro (il vit dans `/tmp`) : la page l'annonce (« la Recalbox
demande une nouvelle autorisation ») et il suffit de garder le bouton appuyé 3
secondes une
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
| Matériel | état du bus SPI, du lecteur RC522, du bouton, du lancement des jeux + verdict et action à faire ; bouton **Tester avec un badge** (5 s) qui dit si une carte est vue, lue, ou pas détectée du tout ; bouton **Régler automatiquement** qui mesure le lecteur et applique les bons réglages |
| Options | **tous les réglages** du lanceur, sans ouvrir de fichier : action au scan, lancement pendant une partie, arrêt du jeu au retrait du badge, délai de pose, appui d'autorisation, intervalle de lecture, anti-rebond, vitesse SPI, bips, niveau de journal. Chaque changement est enregistré sur la Recalbox et appliqué aussitôt |
| Maintenance | installer / mettre à jour (dossier du partage, ZIP depuis le PC, URL), redémarrer Recalbox, démarrer/arrêter/redémarrer le service, journaux en direct |

**Réglage automatique du lecteur** (onglet **Matériel**) — le service mesure
le matériel, puis applique trois valeurs ; rien à comprendre, il suffit de
suivre les quatre consignes (≈ 30 secondes) :

1. posez un badge, sans bouger ;
2. laissez-le en place (mesure de la présence) ;
3. retirez-le (mesure de la latence de retrait) ;
4. reposez-le (vérification).

Ce qui est mesuré puis appliqué :

| Réglage | Ce qui décide la valeur |
| --- | --- |
| Vitesse du bus SPI | la vitesse la plus rapide qui lit le lecteur 40 fois de suite sans erreur |
| Intervalle de lecture | la durée réelle d'une lecture, plus 30 ms (bornée 60–500 ms) |
| Délai d'absence | la latence mesurée au retrait, × 1,5 (bornée 1–4 s) |

* Le rapport affiche aussi la durée d'une lecture, le dialogue de présence
  (**REQA / WUPA**), la latence de repose et l'identifiant lu.
* **Rien n'est écrit si une étape échoue** : le message dit pourquoi (aucun
  badge, badge illisible, retrait manquant, lecteur muet) et les réglages
  restent ceux d'avant.
* **Réinitialiser** remet la vitesse du bus, l'intervalle de lecture et le délai
  d'absence à leurs valeurs d'origine (1 MHz, 150 ms, 1,2 s) ; les valeurs
  d'avant la mesure sont gardées dans `calibration-backup.json`.
* Si la vitesse mesurée ne tient pas à la réouverture du lecteur, le service
  revient tout seul à 1 MHz.

**Onglet Options** — le tableau des réglages :

| Réglage | Ce qu'il fait | Défaut |
| --- | --- | --- |
| Action au scan d'un badge associé | `launch` lance le jeu ; `none` se contente du bip (mode cartouche) | lance le jeu |
| Ne rien lancer pendant une partie | un jeu en cours n'est jamais interrompu par un badge | activé |
| Quitter le jeu quand le badge est retiré | le jeu lancé par le badge s'arrête et Recalbox revient au menu dès que le badge quitte le lecteur | désactivé |
| Délai pour poser le badge | secondes accordées après l'appui court | 10 s |
| Appui qui autorise un navigateur | durée de maintien du bouton (l'autorisation part à ce délai, sans attendre le relâchement) | 3 s |
| Intervalle de lecture du lecteur | fréquence d'interrogation du RC522 | 150 ms |
| Anti-rebond du même badge | temps pendant lequel le même badge est ignoré | 2,5 s |
| Absence avant de pouvoir rescanner | absence nécessaire pour qu'un badge posé puisse agir de nouveau | 1 200 ms |
| Vitesse du bus SPI | réglage matériel, appliqué au redémarrage du service | 1 MHz |
| Bips sonores | confirmation sonore des gestes | activé |
| Niveau de journal | verbosité du journal du service | INFO |

* Rien n'est à ouvrir : l'enregistrement écrit dans le `config.ini` de la
  Recalbox **en gardant ses commentaires**, puis le service **relit sa
  configuration immédiatement** (pas de redémarrage, la lecture des badges
  continue).
* Une modification pas encore enregistrée est signalée (« modifications non
  enregistrées ») et **survit à un changement d'onglet** ; **Annuler** revient aux
  valeurs de la Recalbox.
* Une valeur hors bornes est ramenée dans les limites, et le service refuse ce
  qu'il ne comprend pas : dans ce cas rien n'est écrit.
* Les broches, l'adresse du frontend et le port de l'agent restent dans
  `config.ini` : ils servent une fois, à l'installation, et ne changent qu'au
  redémarrage du service.

Points utiles :

* **Fichier unique** : si vous avez ouvert
  `dist\recalbox-rfid-installer.html`, une première section permet de
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
* **Autorisation perdue** (Recalbox complètement redémarrée, programme mis à
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

Uniquement depuis l'interface : onglet **Badges** → **« Effacer un badge »**,
puis posez le badge sur le lecteur (10 secondes, 3 bips descendants si le délai
expire).

Le bouton physique a deux gestes seulement :

| Geste | Effet |
| --- | --- |
| **Appui court** | arme l'association du jeu sélectionné (1 bip aigu) ; posez le badge dans les 10 s |
| **Appui de 3 secondes** | autorise un navigateur : la validation part **dès la 3e seconde**, inutile de relâcher (un bip confirme) |

Réassocier un badge déjà connu **écrase** l'ancienne correspondance : c'est la
façon la plus simple de changer le jeu d'un badge, sans passer par l'effacement.

## Le son

Aucun son n'est émis au **lancement** d'un jeu : l'écran de chargement du jeu
sert de confirmation. Les bips restent pour ce qui ne se voit pas (association,
badge inconnu, délai dépassé).

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
RFID="sh /recalbox/share/system/rfid/rfidctl"

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
sh /recalbox/share/system/rfid/rfidctl restart
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
| `[button] hold_press_s` | `3.0` | durée de l'appui qui autorise un poste |
| `[button] arm_timeout_s` | `10` | délai pour scanner après un appui |
| `[button] debounce_ms` | `40` | anti-rebond |
| `[launch] udp_host` / `udp_port` | `127.0.0.1` / `1337` | interface du frontend |
| `[launch] action` | `launch` | `launch` = lance le jeu ; `none` = bip seulement (mode cartouche) |
| `[launch] ignore_when_game_running` | `1` | ignore les scans pendant un jeu |
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
2026-01-01 12:00:42 [INFO   ] Commande envoyee : START|snes|/recalbox/share/roms/snes/Super Mario World.smc
2026-01-01 12:00:42 [INFO   ] Lancement de Super Mario World (snes)
```
