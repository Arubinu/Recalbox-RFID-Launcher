# 🎮 Recalbox RFID Launcher

[English](README.md) · **Français** · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português](README.pt.md)

**Un badge, un jeu.** Posez un badge RFID sur un lecteur branché à votre Recalbox : le jeu associé démarre, comme
une cartouche. Tout se règle depuis une seule page web ouverte sur votre ordinateur, sans rien y installer et sans
ligne de commande.
La même page s'ouvre aussi sur un téléphone, servie par la Recalbox elle-même.

## 💡 L'idée

Le projet est né d'une image simple : une **fente découpée dans le boîtier de la console**, avec le lecteur caché
juste derrière, dans laquelle on **insère des cartes comme des cartouches de jeu**. On glisse une carte, son jeu
démarre ; avec le réglage **« Quitter le jeu quand on retire le badge »**, retirer la carte ramène au menu de
Recalbox, exactement comme on retire une cartouche. Chaque carte peut porter l'illustration de son jeu : une
étagère de « cartouches » que tout le monde peut utiliser, enfants compris, sans jamais passer par les menus.

## ✨ Fonctionnalités

- 🏷️ **Un badge = un jeu** : le jeu démarre exactement comme depuis le menu de Recalbox (écran de chargement,
  sauvegardes, succès)
- 🔘 **Association en deux secondes** : placez-vous sur un jeu dans la Recalbox, appuyez sur le bouton du boîtier
  (ou cliquez dans la page), posez le badge
- 🧭 **Installation guidée** : schéma de branchement, copie sur la Recalbox, installation depuis le menu de
  Recalbox 10 **sans redémarrage**, puis autorisation avec le bouton du boîtier
- 🔐 **Aucun mot de passe** : un ordinateur s'autorise en gardant le bouton du boîtier appuyé 3 secondes
- 🩺 **Vérification du matériel** en langage courant, test du lecteur et **réglage automatique du lecteur**
- 🔄 **Mises à jour en un clic** depuis la page ; badges et réglages sont toujours conservés
- 🌍 **6 langues** (anglais, français, allemand, espagnol, italien, portugais), thèmes clair et sombre
- 🧩 **Zéro dépendance** : uniquement le Python 3 déjà présent dans Recalbox, aucun paquet, aucune modification du
  système
- 🖨️ **Cartes à imprimer** : l'image du jeu, le logo et les couleurs de sa console, sept modèles, chaque élément se
  déplace et se tourne ; dix cartes par feuille A4
- 📱 **Aussi sur téléphone** : la Recalbox sert la page elle-même (QR code) ; cherchez un jeu et associez un badge sans
  la télé
- 🎲 **Cartes spéciales** : jeu au hasard, temps bonus, quitter le jeu, éteindre
- ⏱️ **Temps de jeu** : une limite par badge ou pour tous, avertissements avant la fin, cartes bonus avec quota
- 💡 **Voyant et messages à l'écran** : une LED RGB ou des LED programmables, des messages sur l'écran du jeu

## 🧰 Ce qu'il vous faut

| Matériel | Détail |
| --- | --- |
| Recalbox | **version 9 ou plus récente** (Recalbox 10 conseillée : installation sans redémarrage) |
| Raspberry Pi | 3, 4 ou Zero 2, qui démarre sur Recalbox |
| Lecteur RFID **MFRC522** | module « RC522 », par exemple le nf-SL001 (**3,3 V uniquement**) |
| Badges / porte-clés | 13,56 MHz ISO 14443-A (MIFARE Classic, Ultralight…). Les badges 125 kHz ne marchent pas |
| Un bouton poussoir | n'importe quel bouton à contact momentané, sans résistance |
| Fils Dupont | 7 (6 pour le lecteur, 1 de plus pour le bouton) |
| Voyant (facultatif) | un module LED RGB, ou des LED programmables WS2812 : voir [docs/WIRING.md](docs/WIRING.md) |

> ⚠️ Le RC522 fonctionne **en 3,3 V uniquement**. Ne le branchez jamais sur le 5 V du Raspberry Pi : il serait détruit.

## 🔌 Branchement

![Branchement du lecteur RC522 et du bouton](docs/wiring.svg)

| RC522 | Raspberry Pi (GPIO BCM) | Broche physique |
| --- | --- | --- |
| SDA | GPIO8 (CE0) | 24 |
| SCK | GPIO11 (SCLK) | 23 |
| MOSI | GPIO10 (MOSI) | 19 |
| MISO | GPIO9 (MISO) | 21 |
| RST | GPIO25 | 22 |
| GND | GND | 6 |
| 3.3V | 3V3 | 1 |
| **Bouton** | GPIO17 et GND | 11 et 9 |

Le pull-up interne du Raspberry Pi est activé par le programme : aucune résistance. Détails :
[docs/WIRING.md](docs/WIRING.md).

## 🚀 Installation

### Le plus simple : la page

1. **Téléchargez** `recalbox-rfid-installer.html` dans la [dernière version](../../releases/latest) (ou prenez
   `dist/recalbox-rfid-installer.html` dans ce dépôt) et ouvrez-le avec **Edge ou Chrome**.
2. Choisissez **« Installer pour la première fois »** et suivez les quatre étapes :
   1. **Brancher** : le schéma s'affiche à l'écran.
   2. **Copier** : cliquez sur « Choisir le dossier de la Recalbox » ; la page copie l'adresse, collez-la dans la
      fenêtre (Ctrl+V, Entrée) et validez. La page écrit tout sur le partage de la Recalbox.
   3. **Lancer** : sur **Recalbox 10**, avec la manette, `START` › Réglages avancés › Scripts utilisateur ›
      **Install-RFID-reader**. Sur **Recalbox 9**, redémarrez la Recalbox. La page attend et passe seule à la suite ;
      la Recalbox peut redémarrer une fois toute seule pour activer le lecteur.
   4. **Autoriser** : gardez le bouton du boîtier appuyé 3 secondes. La gestion des badges s'ouvre.

> **Version en ligne** : <https://arubinu.github.io/recalbox-games-rf-launcher/> permet de faire les étapes 1 et 2.
> Les navigateurs interdisent à une page `https://` de parler à un appareil de votre réseau : la page en ligne propose
> donc de se télécharger pour la suite, et la page enregistrée sur votre ordinateur fait tout.

### Si Windows n'ouvre pas `\\RECALBOX\share`

- **Windows propose de « Diagnostiquer »** : votre connexion est en réseau *Public*, qui cache les appareils de votre
  réseau. Paramètres › Réseau et Internet › Wi-Fi ou Ethernet › votre réseau › Type de profil réseau › **Privé**.
  Vous pouvez aussi taper l'adresse IP de la Recalbox (`\\192.168.1.20\share`, affichée dans START › Réglages réseau).
- **Windows demande un mot de passe, ou rien ne marche** : à l'étape 2, utilisez **« Télécharger l'installateur
  Windows »**. Ce petit fichier `.cmd` trouve la Recalbox, se connecte au partage, copie tout, puis rouvre la page à
  l'étape 3.

### Autres méthodes

- **À la main** : copiez le dossier `recalbox-rfid` dans `\\RECALBOX\share`, copiez
  `recalbox-rfid\bootstrap\recalbox-rfid-agent(permanent).py3` dans `userscripts\` et, sur Recalbox 10, le contenu de
  `recalbox-rfid\bootstrap\manual` dans `userscripts\manual\`. Redémarrez ensuite (ou lancez *Install-RFID-reader*).
- **En SSH** : `ssh root@recalbox.local "sh /recalbox/share/recalbox-rfid/install.sh --start"` (mot de passe par
  défaut `recalboxroot`).

Guide pas à pas : [docs/INSTALLATION.md](docs/INSTALLATION.md).

## 🎯 Au quotidien

- **Associer un badge** : sur la Recalbox, placez-vous sur un jeu dans la liste (sans le lancer). Dans la page,
  cliquez sur **« Associer un badge à ce jeu »** (ou appuyez brièvement sur le bouton du boîtier), puis posez le badge
  dans les 10 secondes. Deux bips confirment.
- **Lancer un jeu** : posez le badge. L'écran de chargement du jeu sert de retour visuel.
- **Effacer un badge** : dans la page, l'icône corbeille à côté de lui, ou **« Effacer en posant le badge »**.
- **Sauvegarder vos badges** : « Sauvegarder la liste » enregistre un fichier CSV (il s'ouvre dans Excel ou
  LibreOffice) ; « Restaurer une liste » le recharge.

| Son | Signification |
| --- | --- |
| 1 bip aigu | mode association armé |
| 2 bips montants | badge associé |
| 1 bip médium | badge reconnu sans action (`action = none`) |
| aucun son | un jeu démarre : son écran de chargement suffit |
| 2 bips graves | mode effacement armé |
| 2 bips graves descendants | badge inconnu ou action refusée |
| 3 bips descendants | délai dépassé (10 s pour poser le badge) |

## 🖨️ Cartes, cartes spéciales et temps de jeu

- **Chercher un jeu** (onglet Badges) : tapez quelques lettres, puis associez un badge au jeu, sans la télé. Pratique
  sur un téléphone : ouvrez `http://recalbox.local:8765/` (ou scannez le QR code du bouton téléphone de l'en-tête).
- **Imprimer les cartes** (onglet Cartes) : choisissez un jeu et un modèle, horizontal ou vertical ; touchez un élément
  de la carte pour le déplacer, l'agrandir ou le tourner ; une bande jaune montre la partie qui dépasse de la fente.
  Enregistrez votre mise en page comme modèle, ajoutez les cartes à la planche, puis imprimez à 100 % (dix cartes par
  feuille A4).
- **Cartes portables** : crayon d'un badge › « Écrire le jeu dans le badge » enregistre le jeu dans le badge
  lui-même ; il marche alors sur toute Recalbox qui a ce jeu (badges MIFARE Classic, Ultralight, NTAG).
- **Cartes spéciales** (onglet Badges) : jeu au hasard, temps bonus, quitter le jeu, éteindre la Recalbox.
- **Temps de jeu** : Réglages › Temps de jeu par partie, ou par badge avec le crayon. La Recalbox prévient 5 minutes
  puis 1 minute avant la fin, puis quitte le jeu ; une carte bonus ajoute des minutes, un nombre de fois limité par
  jour, par semaine…

Détails : [docs/USAGE.md](docs/USAGE.md) (en anglais).

## 🔄 Mettre à jour

Dans la page, onglet **Mises à jour** › **« Mettre à jour vers X »** : la page envoie le programme qu'elle contient.
Badges et réglages sont conservés, et la page se reconnecte toute seule. Autres façons (fichier ZIP, adresse, SSH) :
[docs/UPDATING.md](docs/UPDATING.md).

## 🗑️ Désinstaller

- **Recalbox 10** : `START` › Réglages avancés › Scripts utilisateur › **Uninstall-RFID-reader**. Badges et réglages
  sont gardés, et *Install-RFID-reader* reste dans le menu pour réinstaller en un clic.
- **Tout, données comprises** (SSH) : `sh /recalbox/share/system/rfid/uninstall.sh --remove-spi`

## 🩺 Dépannage

| Symptôme | À faire |
| --- | --- |
| Windows propose de « Diagnostiquer » sur `\\RECALBOX` | profil réseau *Public* : passez-le en *Privé*, ou utilisez l'adresse IP |
| La page ne trouve pas la Recalbox | même réseau ? essayez son adresse IP à la place de `recalbox.local` |
| « Lecteur introuvable » | câblage, 3,3 V, puis onglet **Matériel** › « Tester avec un badge » |
| Le badge n'est pas lu | il doit être en 13,56 MHz ; une carte bancaire sans contact permet de tester le lecteur |
| Le bouton ne fait rien | GPIO17 pris par les manettes GPIO (`controllers.gpio.enabled=0`), câblage vers GND |
| Le jeu ne se lance pas | Recalbox 9 ou plus récente ; le jeu doit être *sélectionné*, pas un dossier |
| La page redemande l'autorisation | la Recalbox a redémarré : gardez le bouton du boîtier appuyé 3 secondes |

Guide complet : [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## 🛠️ Pour les développeurs

Tout se teste sur un PC, sans Raspberry Pi :

```sh
python app/main.py --home ./data config-init
python app/main.py --home ./data simulate      # faux lecteur et faux bouton
python tests/run_tests.py                      # tests unitaires, aucun matériel requis
python tools/build_installer.py                # régénère dist/recalbox-rfid-installer.html
```

Sur la Recalbox, l'outil en ligne de commande s'appelle toujours avec `sh` (le partage exFAT ne garde pas le droit
d'exécution) : `sh /recalbox/share/system/rfid/rfidctl help`.

Le fonctionnement, en bref :

- **Lecture des badges** : pilote MFRC522 en Python pur sur `/dev/spidev0.0` (`ioctl` via `ctypes`), séquence
  ISO 14443-3A, tolérant aux badges clones.
- **Jeu sélectionné** : lu dans `/tmp/es_state.inf`, que le frontend Recalbox réécrit à chaque événement.
- **Lancement** : datagramme UDP `START|<système>|<chemin complet>` sur `127.0.0.1:1337`, la commande officielle du
  frontend.
- **Page ↔ Recalbox** : un agent WebSocket écrit avec la bibliothèque standard ; la page est ouverte en local
  (`file://`) et un ordinateur s'autorise par un appui physique sur le bouton (secret de session en mémoire).
- **Démarrage** : deux scripts utilisateur permanents (service + agent) et, sur Recalbox 10, deux scripts du menu
  (installer / désinstaller).

Publication sur GitHub (Pages et versions) : [docs/PUBLISHING.md](docs/PUBLISHING.md). La documentation
détaillée du dossier `docs/` et l'[historique des versions](CHANGELOG.md) sont en anglais.

## 📚 Documentation

- [docs/WIRING.md](docs/WIRING.md) : câblage détaillé, choix des broches et voyant
- [docs/INSTALLATION.md](docs/INSTALLATION.md) : installation pas à pas (Windows, macOS, Linux)
- [docs/USAGE.md](docs/USAGE.md) : association, cartes à imprimer, cartes spéciales, temps de jeu, commandes, configuration
- [docs/UPDATING.md](docs/UPDATING.md) : mises à jour et retour arrière
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) : diagnostic et solutions
- [docs/PUBLISHING.md](docs/PUBLISHING.md) : GitHub Pages et versions (en anglais)
