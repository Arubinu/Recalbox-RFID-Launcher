# Installation

L'installation consiste à copier le programme sur le partage Recalbox puis à
lancer un script. Comptez 5 minutes.

## Pré-requis

* Recalbox **9 ou plus** (menus > `SYSTÈME` > `INFORMATIONS` : la version est
  affichée). Le lancement de jeu par script n'existe pas avant Recalbox 9.
* Le **serveur SSH** activé : `RÉSEAU` > `SERVEUR SSH` > `ON`.
* Le **partage réseau** activé : `RÉSEAU` > `PARTAGE SMB` > `ON` (activé par
  défaut). Le partage apparaît dans l'Explorateur sous `\\RECALBOX\share`.
* Le montage du Raspberry Pi et le câblage du lecteur : voir
  [`CABLAGE.md`](CABLAGE.md).

Mot de passe par défaut du compte `root` : `recalboxroot`.

---

## Méthode 0 — l'installateur `.cmd` (le plus simple)

Le sélecteur de dossier de Windows ne sait pas atteindre un partage UNC : on
l'évite complètement. La page génère un **fichier unique** qui fait tout.

1. **Ouvrez `dist\recalbox-rfid-installer-<version>.html`** (ou régénérez-le :
   `python tools/build_installer.py`) et indiquez l'adresse de la Recalbox.
2. Cliquez sur **« Télécharger l'installateur Windows (.cmd) »**.
3. **Double-cliquez** sur le fichier téléchargé. Windows peut afficher
   « Windows a protégé votre PC » : *Informations complémentaires* →
   *Exécuter quand même*.
   Le script (`recalbox-rfid-installation.cmd`) :
   * se connecte au partage (`net use` : `root`/`recalboxroot`, puis invité) ;
   * décompresse les fichiers embarqués (`certutil` + `tar`) ;
   * copie `\\RECALBOX\share\recalbox-rfid\` et
     `\\RECALBOX\share\userscripts\recalbox-rfid-agent(permanent).py3`.
4. **Redémarrez Recalbox.** Le script d'amorçage installe tout seul (programme,
   SPI, service) et redémarre une fois de plus si le SPI vient d'être activé.
   Le déroulé est dans `\\RECALBOX\share\system\rfid\logs\auto-install.log`.
5. **Relancez le même `.cmd`** : il lit le jeton sur le partage, le copie dans
   le presse-papiers et ouvre l'interface de gestion avec le jeton déjà rempli.

Si le message est `ECHEC : acces au partage impossible`, le script affiche le
code d'erreur et les pistes (adresse IP, mot de passe, accès invité).

## Méthode 1 — copie depuis la page (sélecteur de dossier, Edge/Chrome)

Le sélecteur de dossier de Windows ne sait pas toujours atteindre un partage
UNC : c'est une méthode de repli, à utiliser si elle fonctionne chez vous.

1. **Ouvrez le fichier** (double-clic) dans **Edge ou Chrome** — Firefox et
   Safari ne permettent pas l'écriture locale.
2. Cliquez sur **« Choisir `\\RECALBOX\share` et copier… »**, puis sélectionnez le
   partage Recalbox (le dossier qui contient `roms`, `system`…).
   La page crée :
   * `\\RECALBOX\share\recalbox-rfid\` (programme complet) ;
   * `\\RECALBOX\share\userscripts\recalbox-rfid-agent(permanent).py3`
     (démarrage automatique de l'agent).
3. **Redémarrez Recalbox.**
4. Dans la même page, connectez-vous (étape 2) : adresse, port `8765`, et
   cliquez sur **« Connecter »** — le jeton est lu automatiquement dans
   `\\RECALBOX\share\system\rfid\token.txt` (une autorisation de dossier la
   première fois, mémorisée ensuite).
5. Cliquez sur **« Installer / mettre à jour maintenant »**, puis sur
   **« Redémarrer Recalbox »** si le journal signale l'activation du SPI.

En cas de navigateur non compatible (ou d'API d'écriture refusée), utilisez la
méthode 2 : le résultat est identique, seules les copies sont manuelles.

### Si `\\RECALBOX\share` demande un identifiant

C'est normal sur les Windows récents : le partage Recalbox est un partage
« invité » et **Windows 11 (24H2 et plus) bloque les accès invités par défaut**.
Deux solutions :

1. **Se connecter avec le compte Recalbox** (le plus simple) :

   * utilisateur : `root`
   * mot de passe : `recalboxroot` (mot de passe par défaut)

   Cochez « Se souvenir de mes informations d'identification ». Recalbox crée ce
   compte Samba à chaque démarrage (script `S35securepasswd`).

2. **Autoriser les accès invités dans Windows** (plus aucune demande de mot de
   passe). Dans une console **PowerShell en administrateur** :

   ```powershell
   Set-SmbClientConfiguration -EnableInsecureGuestLogons $true
   ```

   (équivalent graphique : `gpedit.msc` → Configuration ordinateur → Modèles
   d'administration → Réseau → Station de travail Lanman → « Activer les
   ouvertures de session invité non sécurisées »).

Astuce : si Windows a mémorisé de mauvais identifiants, supprimez-les avant de
réessayer :

```cmd
net use \\RECALBOX\share /delete
cmdkey /delete:RECALBOX
```

Puis, pour éviter les dialogues dans la sélecteur de dossier, montez le partage
en lecteur (le sélecteur de la page pourra choisir `Z:\`) :

```cmd
net use Z: \\RECALBOX\share /user:root recalboxroot /persistent:yes
```

> `\\RECALBOX` seul (sans `\share`) n'est pas parcourable : c'est normal, seul le
> partage nommé est exposé. Utilisez `\\RECALBOX\share` ou
> `\\<adresse-ip>\share`.

Si `root` / `recalboxroot` est refusé, c'est que le mot de passe racine a été
personnalisé : réinitialisez le mot de passe Samba en SSH
(`smbpasswd -a root`), ou utilisez la méthode A (copie manuelle) / la méthode C
(SSH).

## Méthode 2 — copie manuelle du dossier

Aucune ligne de commande : une page locale (`installer.html`) parle à un agent
WebSocket protégé qui tourne sur la Recalbox.

1. **Copiez le dossier du projet** sur le partage Recalbox : ouvrez
   `\\RECALBOX\share` dans l'Explorateur et déposez-y le dossier
   `recalbox-rfid` (celui qui contient `install.sh`).
2. **Copiez le script de l'agent** :

   ```
   recalbox-rfid\bootstrap\recalbox-rfid-agent(permanent).py3
   ```

   dans le dossier `userscripts` du partage, c'est-à-dire
   `\\RECALBOX\share\userscripts\`.
3. **Redémarrez Recalbox** (`QUITTER` > `REDÉMARRER`) : l'agent démarre avec
   l'interface.
4. **Double-cliquez sur `installer.html`** (le fichier est à la racine du
   projet, sur votre PC). Renseignez :
   * l'adresse : `recalbox.local` (ou l'IP affichée dans `RÉSEAU` > `INFORMATIONS`) ;
   * le port : `8765` ;
   * le jeton : **laissez le champ vide**. La page le récupère toute seule grâce
     à l'appairage automatique (fenêtre de 15 minutes ouverte après le
     redémarrage de la Recalbox). Il n'y a aucun fichier à chercher.
5. Cliquez sur **« Se connecter »**, puis sur **« Installer / mettre à jour »**
   (carte « Installation et service ») : le journal défile en direct.
6. Si l'installation active le bus SPI, cliquez sur **« Redémarrer la Recalbox »**
   (indispensable pour que le lecteur soit reconnu).

Tout est journalisé dans `/recalbox/share/system/rfid/logs/install.log` et
`logs/agent.log`.

> `installer.html` ne nécessite ni serveur local ni installation : un
> navigateur récent (Edge, Chrome, Firefox, Safari) suffit. Il mémorise
> l'adresse et le jeton pour les fois suivantes.

## Méthode 3 — assistant Windows

1. Téléchargez / décompressez le projet `recalbox-rfid` sur le PC.
2. Double-cliquez sur **`windows\INSTALLER.cmd`**.
3. L'assistant demande l'adresse de la Recalbox (par défaut `recalbox.local`),
   copie les fichiers sur le partage et y place automatiquement le script de
   l'agent.
4. Il propose ensuite d'installer tout de suite par SSH (mot de passe
   `recalboxroot`) ; sinon il ouvre `installer.html` pour finir dans le
   navigateur après redémarrage.

## Méthode 4 — Windows, macOS ou Linux, en ligne de commande (SSH)

**Étape 1 — copier le dossier sur la Recalbox**

* Windows : ouvrez `\\RECALBOX\share` dans l'Explorateur et copiez-y le dossier
  `recalbox-rfid` (celui qui contient `install.sh`).
* macOS / Linux : depuis un terminal, dans le dossier du projet :

  ```sh
  scp -r recalbox-rfid root@recalbox.local:/recalbox/share/
  ```

**Étape 2 — lancer l'installateur**

Windows (PowerShell), macOS ou Linux :

```sh
ssh root@recalbox.local "sh /recalbox/share/recalbox-rfid/install.sh --start"
```

**Étape 3 — redémarrer et vérifier**

Si l'installateur indique qu'un redémarrage est nécessaire (activation du SPI),
redémarrez Recalbox (`QUITTER` > `REDÉMARRER`), puis connectez `installer.html`
(agent sur le port 8765) ou lancez :

```sh
ssh root@recalbox.local "/recalbox/share/system/rfid/rfidctl test"
```

## Méthode 5 — directement sur la Recalbox

Avec un clavier branché, quittez le frontend (`QUITTER` > `QUITTER
EMULATIONSTATION`) pour obtenir une console, connectez-vous en `root`
(`recalboxroot`), puis :

```sh
sh /recalbox/share/recalbox-rfid/install.sh --start
reboot
```

---

## Ce que fait l'installateur

| Action | Détail |
| --- | --- |
| Programme | copié dans `/recalbox/share/system/rfid/app` |
| Configuration | `/recalbox/share/system/rfid/config.ini` (créée si absente, **jamais écrasée**) |
| Badges | `/recalbox/share/system/rfid/tags.json` (**jamais écrasé**) |
| Journaux | `/recalbox/share/system/rfid/logs/rfid.log` |
| Commande | `/recalbox/share/system/rfid/rfidctl` |
| Démarrage auto | `/recalbox/share/userscripts/recalbox-rfid(permanent).py3` (service RFID) |
| Agent de gestion | `/recalbox/share/userscripts/recalbox-rfid-agent(permanent).py3` (WebSocket) |
| Jeton d'accès | `/recalbox/share/system/rfid/token.txt` (créé au premier démarrage de l'agent) |
| Journaux | `/recalbox/share/system/rfid/logs/rfid.log`, `agent.log`, `install.log` |
| Bus SPI | ajoute `dtparam=spi=on` dans `/boot/recalbox-user-config.txt` (sauvegarde `.bak-rfid-launcher`) |

Tout est dans le partage : **rien n'est écrit dans le système Recalbox**, une
mise à jour de Recalbox ne supprime donc pas l'installation (mais vérifiez que
`dtparam=spi=on` est toujours présent dans le fichier de configuration du boot
après une montée de version majeure).

L'installateur est **idempotent** : le relancer réinstalle proprement, en
conservant configuration, badges et jeton. C'est aussi la procédure de mise à
jour.

## Options de l'installateur

```sh
sh install.sh                 # installer / mettre a jour
sh install.sh --start         # ... et demarrer le service tout de suite
sh install.sh --upgrade       # mise a jour (conserve tout)
sh install.sh --no-restart    # ne pas redemarrer le service (utilise par l'agent)
sh install.sh --no-spi        # ne pas toucher a la configuration du SPI
sh install.sh --from-url URL  # installer un ZIP heberge en ligne
sh install.sh --uninstall     # desinstaller
```

## Si l'installation affiche des erreurs bizarres (`: not found`, `illegal option`)

Le fichier a des **fins de ligne Windows (CRLF)** : Recalbox exécute les scripts
avec `/bin/sh`, qui n'accepte que les fins de ligne Unix (LF).

* le plus simple : utilisez l'assistant `windows\INSTALLER.cmd`, il convertit
  automatiquement les fichiers ;
* ou convertissez le fichier avant de le copier :

  ```powershell
  (Get-Content install.sh -Raw) -replace "`r`n", "`n" | Set-Content -NoNewline install.sh
  ```

* en ligne de commande sur Recalbox (si `dos2unix` est absent) :

  ```sh
  sed -i 's/\r$//' /recalbox/share/recalbox-rfid/install.sh
  ```

Le fichier `.gitattributes` du projet force déjà les fichiers `*.sh`, `*.py` et
`*.py3` en LF : un `git clone` sur Windows est donc sûr.

## Activation manuelle du SPI

Si l'installation n'a pas pu écrire dans `/boot` (droits), éditez
`/boot/recalbox-user-config.txt` et ajoutez à la fin :

```
dtparam=spi=on
```

Puis redémarrez. Vérification :

```sh
ls -l /dev/spidev0.0
```

Le fichier doit exister.

## Premier test complet

1. Posez un badge : `rfidctl test` doit afficher son UID.
2. Dans Recalbox, sélectionnez un jeu.
3. Appui court sur le bouton (1 bip aigu).
4. Scannez le badge : le jeu se lance.
5. Quittez le jeu, scannez à nouveau le badge : le jeu se relance.

## Désinstallation

```sh
ssh root@recalbox.local "sh /recalbox/share/system/rfid/uninstall.sh"
```

Options :

* `--keep-data` : conserve `config.ini` et `tags.json` ;
* `--remove-spi` : retire aussi `dtparam=spi=on` de la configuration du boot.
