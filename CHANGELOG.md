# Historique des versions

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
versionnage sémantique. La version courante est aussi dans le fichier `VERSION`
et affichée par `rfidctl version`.

## [1.5.1]

### Ajouté

* `acces-recalbox.cmd` (généré par la page) devient **diagnostic** : il affiche
  le code d'erreur `net use` et la cause probable (1326 mot de passe, 53 nom
  introuvable, 67 partage absent, 1272 stratégie Windows), et rappelle les
  commandes de nettoyage (`net use /delete`, `cmdkey /delete`).

### Documenté

* **« Mot de passe incorrect » avec `root` / `recalboxroot`** : le script Recalbox
  `S35securepasswd` crée le compte Samba avec `recalboxroot` **uniquement si**
  `system.default_password` est vide ; sinon la variable `MASTERPASSWD` n'est pas
  définie et le mot de passe Samba devient **vide** (Windows le refuse).
  Procédure : `grep default_password recalbox.conf`, puis `smbpasswd -a root`
  (et `pdbedit -L` pour vérifier). Table des codes `net use` ajoutée dans
  `docs/DEPANNAGE.md`.

## [1.5.0]

### Ajouté

* **Le bouton « Connecter » récupère le jeton tout seul** : si le champ est vide,
  la page demande une seule fois le dossier du partage, lit
  `system/rfid/token.txt` et se connecte. L'autorisation est mémorisée
  (`IndexedDB`) pour les fois suivantes ; plus de copier-coller.
* Bouton **« Autoriser Windows à accéder au partage »** : génère un
  `acces-recalbox.cmd` prêt à l'emploi (`net use \\RECALBOX\share /user:root
  recalboxroot`, puis ouverture de l'Explorateur). Le navigateur ne peut pas
  saisir les identifiants SMB à notre place : ce fichier fait le lien en un
  double-clic (l'adresse saisie dans la page est reprise).
* La section « Copier les fichiers » reste visible dans la version « dossier »
  (le bouton de copie est masqué) pour profiter de l'assistant d'accès et du
  jeton automatique.
* Vérifié dans un navigateur réel : jeton lu sur le partage puis connexion à
  l'agent sans saisie manuelle.

## [1.4.1]

### Corrigé / documenté

* **`\\RECALBOX\share` demande un identifiant** : explication ajoutée dans la
  page de copie, le README, `docs/INSTALLATION.md` et `docs/DEPANNAGE.md`.
  Windows 11 (24H2+) refuse par défaut les sessions invitées : utiliser le compte
  Recalbox **`root` / `recalboxroot`**, ou autoriser les ouvertures de session
  invité non sécurisées
  (`Set-SmbClientConfiguration -EnableInsecureGuestLogons $true`).
  Rappel : `\\RECALBOX` sans `\share` n'est pas parcourable (normal), et
  `net use Z: \\RECALBOX\share /user:root recalboxroot` évite les dialogues dans
  le sélecteur de dossier.
* Précisé que le compte Samba `root` est (re)créé à chaque démarrage par le
  script Recalbox `S35securepasswd`.

## [1.4.0]

### Ajouté

* **Installateur unique et autonome** : `dist/recalbox-rfid-installer-<version>.html`
  contient la page de gestion **et le contenu de tous les fichiers à copier**.
  Plus besoin de copier le dossier à la main.
* **Copie directe vers `\\RECALBOX\share`** depuis la page (API File System
  Access) : la page crée `recalbox-rfid\` et le script de démarrage dans
  `userscripts\`. Fonctionne avec Edge et Chrome (Firefox/Safari ne permettent
  pas l'écriture locale : la méthode « copier le dossier » reste disponible).
* Générateur `tools/build_installer.py` : relancez-le après toute modification
  d'un fichier pour régénérer le fichier unique (celui livré est vérifié par un
  test de fraîcheur).
* 11 tests dédiés au générateur (contenu identique aux sources, payload
  analysable, génération déterministe, aucune balise parasite, fins de ligne LF) :
  118 tests au total.

### Modifié

* `installer.html` affiche une section « Copier les fichiers » lorsqu'il est
  utilisé sous sa forme générée, et rappelle la méthode manuelle sinon.

## [1.3.0]

### Modifié

* **Plus aucune interface hébergée sur la Recalbox** : le serveur HTTP et la page
  servie par la Recalbox sont supprimés.
* La gestion passe par un **agent WebSocket** (RFC 6455, bibliothèque standard)
  protégé par un **jeton** (`token.txt`), et par un fichier **`installer.html`**
  autonome ouvert sur le PC (`file://` → `ws://`), sans serveur local.
* Le script permanent d'amorçage devient
  `recalbox-rfid-agent(permanent).py3` : il démarre l'agent, depuis
  l'installation ou depuis le dossier copié sur le partage (avant installation).
* `install.sh` installe les deux scripts permanents et copie `installer.html`
  dans le dossier d'installation ; il affiche l'URL de l'agent et le chemin du
  jeton.
* L'agent diffuse le journal d'installation en direct (flux d'événements), accepte
  un ZIP envoyé par morceaux, et se recharge seul après une installation.
* `installer.html` : connexion adresse/port/jeton (mémorisée), journal en direct,
  badges, association, service, redémarrage, journaux.

### Supprimé

* `app/rfid/webui.py`, `app/web/index.html`, la commande `rfidctl web`, le
  redémarrage automatique après installation et les tests associés.

### Tests

* 104 tests, dont 20 sur l'agent WebSocket (poignée de main, trames, jeton,
  commandes, upload, flux d'installation).

## [1.2.0]

### Ajouté

* **Installation et mise à jour automatiques au démarrage** : il suffit de
  copier le dossier sur le partage et de redémarrer Recalbox. Le script
  d'amorçage installe, active le SPI, redémarre Recalbox une fois si nécessaire,
  puis démarre le service — sans SSH, sans serveur et sans clic.
* Mise à jour automatique : copier un dossier de version plus récente sur le
  partage et redémarrer ; la comparaison de version évite les rétrogradations.
* Le journal `logs/auto-install.log` conserve la sortie complète de
  l'installation automatique.
* Redémarrage différé si un jeu est en cours (jamais d'interruption de partie).
* 20 tests dédiés au script d'amorçage (120 tests au total).

### Modifié

* Le script permanent `recalbox-rfid-autoinstall(permanent).py3` remplace
  l'interface web d'amorçage : il installe tout seul et ne sert la page que si
  quelque chose échoue (diagnostic + relance manuelle).
* Le dossier `bootstrap/` remplace `web-bootstrap/`.
* L'interface web devient un outil de gestion et de secours : elle n'est plus
  nécessaire pour installer.

## [1.1.0]

### Ajouté

* **Interface web** (`http://recalbox.local:8080`, sans dépendance) : installer,
  mettre à jour (ZIP envoyé depuis le navigateur ou URL), redémarrer Recalbox,
  voir l'état du matériel, gérer les badges, armer l'association d'un badge,
  exporter/importer les CSV et consulter les journaux.
* **Installation sans SSH** : copier le dossier sur le partage, copier
  `web-bootstrap/recalbox-rfid-web(permanent).py3` dans les userscripts,
  redémarrer, puis tout faire dans le navigateur.
* Interface web de secours : un script permanent sert la page si le service ne
  démarre pas (configuration cassée, plantage).
* Mot de passe facultatif (HTTP Basic) et protection CSRF (vérification de
  l'origine + JSON obligatoire).
* Commandes `rfidctl web` et option `--source` (mode « avant installation »).
* Option `--no-restart` de l'installateur (utilisée par l'interface web).
* Tests de l'interface web : 100 tests unitaires au total.

### Modifié

* L'installateur affiche l'adresse de l'interface web et installe le script
  permanent de secours.
* Le service démarre l'interface web et consomme ses commandes (association,
  suppression, scan simulé).
* Le désinstalleur retire les deux scripts permanents.

## [1.0.0]

Première version publiable.

### Ajouté

* Lecture des badges RFID MFRC522 (RC522 / nf-SL001) sur le bus SPI du
  Raspberry Pi, en Python pur (aucun paquet à installer).
* Lancement du jeu associé via la commande UDP officielle du frontend Recalbox
  (`START|systeme|jeu`, port 1337), sans modification de l'OS.
* Base de correspondances badge ↔ jeu dans `tags.json` (écriture atomique,
  sauvegarde automatique, import/export CSV).
* Bouton poussoir avec pull-up interne (aucune résistance) : appui court pour
  associer le jeu sélectionné, appui long pour effacer un badge.
* Retours sonores (bips générés localement, joués par `paplay` ou `aplay`).
* Service lancé par Recalbox au démarrage (script utilisateur permanent), avec
  verrou anti-doublon et rechargement de la configuration (SIGHUP).
* Installateur idempotent : activation du SPI, installation du démarrage auto,
  conservation de la configuration et des badges.
* Mise à jour par dossier recopié ou par ZIP en ligne (`rfidctl self-update`),
  avec redémarrage automatique du service.
* Désinstallation avec conservation facultative des données.
* Diagnostic `rfidctl test` (SPI, version du MFRC522, lecture d'un badge,
  état du bouton, support du frontend).
* Mode simulation sur PC (`rfidctl simulate`) et 73 tests unitaires, dont un
  simulateur de MFRC522 au niveau SPI.
* Assistant d'installation Windows (`windows/INSTALLER.cmd`).
* Documentation : câblage, installation, utilisation, mise à jour, dépannage.

### Notes

* Recalbox **9** minimum pour le lancement des jeux (le fil « UDPCommand » du
  frontend n'existe pas avant).
* Pas de notification à l'écran : Recalbox n'expose aucune API de message pour
  les scripts (voir `docs/DEPANNAGE.md`, section 8).
