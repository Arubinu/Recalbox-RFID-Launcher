# Historique des versions

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
versionnage sémantique. La version courante est aussi dans le fichier `VERSION`
et affichée par `rfidctl version`.

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
