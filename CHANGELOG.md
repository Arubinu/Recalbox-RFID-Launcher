# Historique des versions

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
versionnage sémantique. La version courante est aussi dans le fichier `VERSION`
et affichée par `rfidctl version`.

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
