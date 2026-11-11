# Recalbox RFID Launcher

Scannez un badge RFID → le jeu Recalbox associé se lance.

* **Zéro dépendance** : uniquement Python 3, déjà présent dans Recalbox. Pas de
  paquet à installer, pas de compilation, pas de modification de l'OS.
* **Base de correspondances** badge ↔ jeu, dans un simple fichier JSON (lisible,
  sauvegardable, exportable en CSV).
* **Bouton poussoir** (sans résistance, pull-up interne du Raspberry Pi) pour
  associer un badge au jeu actuellement sélectionné dans Recalbox.
* **Installateur** en une commande, **mise à jour** en une commande, sans perdre
  les badges.
* **Mode simulation** pour tester tout le fonctionnement sur un PC, sans
  Raspberry Pi.

---

## 1. Ce dont vous avez besoin

| Matériel | Détail |
| --- | --- |
| Recalbox | **version 9 ou plus récente** (le lancement de jeu par script a été ajouté dans Recalbox 9) |
| Raspberry Pi 3 (ou 4 / Zero 2) | le Pi doit démarrer sur Recalbox |
| Lecteur RFID **MFRC522** | module « RC522 », par exemple le **nf-SL001** (3,3 V !) |
| Badges / porte-clés | 13,56 MHz ISO 14443-A (MIFARE Classic, Ultralight…), UID 4 ou 7 octets |
| Un bouton poussoir | n'importe quel bouton à contact momentané |
| 6 fils Dupont | pour le lecteur (7 avec le bouton) |

> ⚠️ Le RC522 **fonctionne en 3,3 V uniquement**. Ne le branchez jamais sur le
> 5 V du Raspberry Pi : vous le détruiriez.

## 2. Câblage (5 minutes)

Voir le schéma détaillé : [`docs/CABLAGE.md`](docs/CABLAGE.md).

| RC522 | Broche RC522 | Raspberry Pi (GPIO BCM) | Broche physique |
| --- | --- | --- | --- |
| SDA / SS | SDA | GPIO8 (CE0) | 24 |
| SCK | SCK | GPIO11 (SCLK) | 23 |
| MOSI | MOSI | GPIO10 (MOSI) | 19 |
| MISO | MISO | GPIO9 (MISO) | 21 |
| RST | RST | GPIO25 | 22 |
| GND | GND | GND | 6 |
| 3.3V | 3.3V | 3V3 | 1 |

| Bouton | Branchement |
| --- | --- |
| Borne 1 | GPIO17 (broche physique 11) |
| Borne 2 | GND (broche physique 9) |

Aucune résistance n'est nécessaire : le pull-up interne du Pi est activé par le
programme.

## 3. Installation (3 étapes)

1. **Activez le SSH** dans Recalbox : menu `RÉSEAU` → `SERVEUR SSH` → `ON`.
   Notez l'adresse IP affichée (ou utilisez `recalbox.local`).
2. **Copiez le dossier du projet** sur le partage Recalbox : ouvrez
   `\\RECALBOX\share` dans l'Explorateur Windows et copiez-y le dossier
   `recalbox-rfid`.
3. **Lancez l'installateur** depuis le PC (PowerShell) :

   ```powershell
   ssh root@recalbox.local "sh /recalbox/share/recalbox-rfid/install.sh --start"
   ```

   Mot de passe par défaut de Recalbox : `recalboxroot`.
   (Ou, depuis la console SSH : `sh /recalbox/share/recalbox-rfid/install.sh --start`.)

L'installateur :

* installe le programme dans `/recalbox/share/system/rfid` ;
* active le bus SPI (`dtparam=spi=on` dans `/boot/recalbox-user-config.txt`,
  avec sauvegarde) ;
* installe le démarrage automatique avec Recalbox ;
* vérifie que le lancement de jeu par script est disponible ;
* conserve toujours `config.ini` et `tags.json` lors d'une mise à jour.

**Redémarrez Recalbox** si l'installateur vous le demande (activation du SPI),
puis vérifiez le matériel :

```sh
/recalbox/share/system/rfid/rfidctl test
```

Le diagnostic affiche la version du MFRC522, détecte un badge posé sur le
lecteur et teste le bouton.

> Un assistant Windows est aussi fourni : `windows\INSTALLER.cmd` (double-clic)
> fait la copie et l'installation à votre place. Détails :
> [`docs/INSTALLATION.md`](docs/INSTALLATION.md).

## 4. Utilisation

### Associer un badge au jeu sélectionné

1. Dans Recalbox, naviguez jusqu'au jeu voulu (il doit être **sélectionné** dans
   la liste, pas lancé).
2. **Appui court** sur le bouton → un bip aigu confirme le mode association
   (30 secondes pour scanner).
3. **Scannez le badge** → deux bips : le badge est enregistré et le jeu se lance
   immédiatement pour confirmer.

### Lancer un jeu

Scannez le badge : le jeu associé se lance. Le frontend affiche son écran de
chargement habituel (nom + jaquette) — c'est le retour visuel.

### Effacer un badge

1. **Appui long** (2 secondes) sur le bouton → deux bips graves.
2. Scannez le badge à effacer → bips de confirmation.

### Retour sonore

| Son | Signification |
| --- | --- |
| 1 bip aigu | mode association armé |
| 2 bips graves | mode suppression armé |
| 2 bips aigus montants | badge reconnu / association réussie |
| 2 bips graves descendus | badge inconnu ou action refusée |
| 3 bips descendants | délai dépassé |

> **Pourquoi pas une notification à l'écran ?** Le frontend Recalbox 9 n'expose
> aucune API permettant à un script d'afficher un message : il *publie* ses
> événements en MQTT mais n'écoute rien (voir `NotificationManager` et
> `RequestHandler` du projet Recalbox). Le retour visuel est donc assuré par le
> lancement du jeu lui-même, et le retour immédiat par le son. Détails et pistes :
> [`docs/DEPANNAGE.md`](docs/DEPANNAGE.md).

### Gérer les badges sans le bouton

```sh
RFID=/recalbox/share/system/rfid/rfidctl

$RFID list                              # liste des associations
$RFID add A1B2C3D4 --current            # associe au jeu sélectionné dans Recalbox
$RFID add A1B2C3D4 snes "Super Mario World.smc"
$RFID remove A1B2C3D4                   # supprime
$RFID export /recalbox/share/badges.csv # export CSV (tableur)
$RFID import /recalbox/share/badges.csv # import CSV
$RFID status                            # état du service
$RFID logs                              # dernières lignes du journal
$RFID restart                           # après modification de config.ini
```

Le format CSV utilise des points-virgules : il s'ouvre directement dans Excel ou
LibreOffice Calc. La colonne `game` contient le chemin du jeu **relatif au
dossier du système**, extension comprise (par exemple `Super Mario World.smc`,
ou `Classiques/jeu.smc` pour un jeu dans un sous-dossier).

## 5. Mise à jour

Deux méthodes, aucune ne touche aux badges :

1. **Depuis un nouveau dossier** (recommandé pour tester) : copiez la nouvelle
   version sur le partage puis relancez
   `sh /recalbox/share/<nouveau-dossier>/install.sh --upgrade`.
2. **Depuis une URL** (ZIP hébergé où vous voulez) :

   ```sh
   /recalbox/share/system/rfid/rfidctl self-update https://exemple.fr/recalbox-rfid.zip
   ```

La mise à jour remplace le programme, conserve `config.ini` + `tags.json`,
redémarre le service et affiche la nouvelle version. Détails :
[`docs/MISE-A-JOUR.md`](docs/MISE-A-JOUR.md).

## 6. Tester sur un PC (sans Raspberry Pi)

Le mode simulation utilise de faux lecteur/bouton et affiche les commandes qui
seraient envoyées à Recalbox :

```sh
python app/main.py --home ./data config-init
python app/main.py --home ./data simulate

rfid> select snes "Super Mario World.smc"
rfid> press
rfid> scan A1B2C3D4
rfid> scan A1B2C3D4
rfid> quit
```

Tests unitaires (73 tests, aucun matériel requis) :

```sh
python tests/run_tests.py
```

## 7. Comment ça marche (technique)

* **Lecture du badge** : pilote MFRC522 écrit en Python pur au-dessus de
  `/dev/spidev0.0` (ioctl `SPI_IOC_MESSAGE` via `ctypes`, sans le module
  `spidev`). Séquence ISO 14443-3A : `REQA` → anticollision → `SELECT` →
  `HALT`, avec vérification du BCC et gestion des UID 4 et 7 octets.
* **Bouton** : `RPi.GPIO` (fourni par Recalbox via `rpi-lgpio`), repli sur
  `lgpio`, puis sur `/sys/class/gpio`. Pull-up interne, anti-rebond logiciel.
* **Jeu sélectionné** : lecture de `/tmp/es_state.inf`, fichier que le frontend
  réécrit à chaque événement (`SystemId`, `GamePath`, `IsFolder`, `State`).
* **Lancement** : datagramme UDP `START|<systeme>|<jeu>` sur `127.0.0.1:1337`,
  l'interface de commande officielle du frontend Recalbox 9. Le jeu est lancé
  exactement comme depuis le menu (splash, sauvegardes, retroachievements).
* **Démarrage** : script permanent `recalbox-rfid(permanent).py3` dans
  `/recalbox/share/userscripts`, exécuté par Recalbox à chaque démarrage de
  l'interface. Un verrou (`flock`) empêche tout doublon.
* **Données** : `/recalbox/share/system/rfid/` (config, badges, journaux),
  donc dans le partage réseau et conservé lors des mises à jour de Recalbox.

## 8. Dépannage express

| Symptôme | Piste |
| --- | --- |
| `/dev/spidev0.0` absent | `dtparam=spi=on` manquant dans `/boot/recalbox-user-config.txt`, puis redémarrage |
| « Lecteur RFID indisponible » | câblage, 3,3 V, `rfidctl test`, journal `logs/rfid.log` |
| Badge non détecté | UID 13,56 MHz requis, badge collé au lecteur, RST non branché |
| Bouton sans effet | GPIO17 occupé (manettes GPIO : `controllers.gpio.enabled=0`), câblage vers GND |
| Le jeu ne se lance pas | Recalbox < 9, ou `rfidctl frontend` en échec |
| Rien ne se passe après un appui | le jeu doit être **sélectionné** dans la liste (pas dossier) |

Guide complet : [`docs/DEPANNAGE.md`](docs/DEPANNAGE.md).

## 9. Documentation

* [`docs/CABLAGE.md`](docs/CABLAGE.md) — câblage détaillé et choix des broches
* [`docs/INSTALLATION.md`](docs/INSTALLATION.md) — installation pas à pas (Windows, macOS, Linux)
* [`docs/UTILISATION.md`](docs/UTILISATION.md) — association, commandes, configuration
* [`docs/MISE-A-JOUR.md`](docs/MISE-A-JOUR.md) — mises à jour et retour arrière
* [`docs/DEPANNAGE.md`](docs/DEPANNAGE.md) — diagnostic et solutions
* [`CHANGELOG.md`](CHANGELOG.md) — historique des versions

## 10. Structure du projet

```
recalbox-rfid/
├── app/
│   ├── main.py                  # point d'entrée (CLI + service + simulation)
│   └── rfid/
│       ├── config.py            # configuration INI
│       ├── storage.py           # base de badges JSON + CSV
│       ├── esbridge.py          # dialogue avec le frontend Recalbox
│       ├── controller.py        # logique association / lancement
│       ├── daemon.py            # boucle du service
│       ├── feedback.py          # bips sonores
│       ├── hardware.py          # fabrication lecteur + bouton
│       └── drivers/             # SPI, RC522, GPIO, bouton, simulateur
├── userscript/recalbox-rfid(permanent).py3
├── tests/                       # 73 tests unitaires
├── docs/
├── install.sh                   # installation / mise à jour
├── uninstall.sh
└── windows/INSTALLER.cmd        # assistant Windows
```
