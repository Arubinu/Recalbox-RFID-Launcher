# Dépannage

Toujours commencer par :

```sh
RFID=/recalbox/share/system/rfid/rfidctl
$RFID status
$RFID logs
$RFID test
```

Et vérifier le journal en direct pendant un scan :

```sh
tail -f /recalbox/share/system/rfid/logs/rfid.log
```

---

## 1. Le service ne démarre pas

| Vérification | Commande / fichier |
| --- | --- |
| Le script de démarrage est-il installé ? | `ls -l /recalbox/share/userscripts/` |
| Python répond ? | `python3 -c "print('ok')"` |
| Le service tourne-t-il déjà ? | `ps aux \| grep rfid` |
| Erreur au démarrage ? | `cat /recalbox/share/system/rfid/logs/service.out` |
| Recalbox a-t-il lancé le script ? | `grep -i userscript /recalbox/share/system/logs/emulationstation.log` |

Le service est lancé par Recalbox **au démarrage de l'interface** (script
permanent `recalbox-rfid(permanent).py3`). Après une installation, redémarrez
Recalbox ou lancez `rfidctl start`.

---

## 2. `/dev/spidev0.0` est absent

Le bus SPI n'est pas activé.

```sh
grep -n "dtparam=spi=on" /boot/recalbox-user-config.txt
ls /boot/
```

Si la ligne est absente :

```sh
echo "dtparam=spi=on" >> /boot/recalbox-user-config.txt
reboot
```

Ou relancez l'installateur :

```sh
sh /recalbox/share/system/rfid/install.sh
```

Puis vérifiez après redémarrage : `ls -l /dev/spidev0.0`.

---

## 3. Le lecteur n'est pas détecté

Symptômes dans `rfidctl test` ou dans le journal :

* `Version du MFRC522 : 0x00` ou `0xFF` → le Pi ne dialogue pas avec le module.
* « Lecteur RFID indisponible » → idem.
* `Lecture RFID en echec (3)` répété → idem.

À vérifier, dans cet ordre :

1. **Alimentation en 3,3 V** (broche 1 ou 17), **jamais 5 V**.
2. **GND commun** entre le module et le Pi.
3. **MISO / MOSI** non croisés (MISO broche 21, MOSI broche 19).
4. **SCK** broche 23, **SDA/SS** broche 24 (CE0).
5. **RST** broche 22 (GPIO25). Si vous ne le branchez pas, mettez
   `reset_pin = -1` dans `config.ini` puis `rfidctl restart`.
6. Les connecteurs Dupont : un faux contact est la cause la plus fréquente.
7. Essayez une vitesse SPI plus basse :

   ```ini
   [rfid]
   spi_speed_hz = 500000
   ```

8. Le module est peut-être défectueux : testez-le sur un Raspberry Pi OS avec
   un exemple MFRC522 connu.

---

## 4. Un badge n'est pas détecté

* Le badge doit être **13,56 MHz ISO 14443-A** (MIFARE Classic, Ultralight,
  NTAG…). Les badges 125 kHz (anciens contrôles d'accès) ne fonctionnent pas.
* Approchez le badge **à moins de 3 cm**, à plat, centré sur l'antenne.
* Un badge métallique ou collé sur du métal perd beaucoup de portée.
* Les UID de 10 octets sont ignorés (extrêmement rare) — voir le journal.
* Un BCC invalide est rejeté : c'est le signe d'une lecture perturbée,
  généralement un problème d'alimentation ou de longueur de fils.

---

## 5. Le bouton ne réagit pas

1. Vérifiez le câblage : bouton entre **GPIO17 (broche 11)** et **GND
   (broche 9)**.
2. `rfidctl test` affiche l'état du bouton ; appuyez pendant le test.
3. Vérifiez que les manettes GPIO de Recalbox ne monopolisent pas les broches :

   ```sh
   grep "controllers.gpio.enabled" /recalbox/share/system/recalbox.conf
   ```

   La valeur doit être `0`. Sinon, passez-la à `0` (menu Recalbox :
   `MANETTES` > `MANETTES GPIO` > `OFF`) et redémarrez.
4. Le bouton doit être **momentané** (contacts qui se ferment quand on appuie).
5. Changez de broche si besoin : `pin = 27` dans `[button]`, rebranchez sur la
   broche 13, puis `rfidctl restart`.
6. Si `rfidctl test` indique « Bouton indisponible » avec un backend `aucun`,
   les modules GPIO ne sont pas accessibles : vérifiez que vous êtes en root.

---

## 6. Le jeu ne se lance pas

1. Vérifiez que Recalbox sait lancer un jeu par script :

   ```sh
   $RFID frontend
   ```

   * `disponible` : c'est bon.
   * `INDISPONIBLE` : votre Recalbox est trop ancienne (il faut **Recalbox 9+**).

2. Vérifiez que le jeu est bien associé et que le chemin est correct :

   ```sh
   $RFID list
   ```

   La colonne « Jeu » doit contenir un chemin **relatif au dossier du système**
   avec l'extension : `Super Mario World.smc`, pas `Super Mario World`.

3. Regardez le journal après un scan :

   ```sh
   $RFID logs
   ```

   `Commande envoyee : START|snes|...` signifie que la trame est partie. Si le
   jeu ne démarre pas malgré cela, le frontend n'a pas trouvé le jeu : le chemin
   relatif est probablement faux (sous-dossier, extension, casse).

4. Un jeu en cours bloque les scans (`ignore_when_game_running`). Quittez le jeu.

5. `Le frontend n'a pas pu etre contacte` : le service a été lancé avant
   l'interface, ou le port 1337 est occupé. `rfidctl restart` corrige le premier
   cas.

---

## 7. Pas de son

```sh
which paplay aplay
paplay /usr/share/sounds/...      # ou :
aplay /tmp/rfid-launcher/beep-*.wav
```

Si aucun lecteur ne fonctionne (pas de carte son, HDMI sans audio), mettez :

```ini
[feedback]
sound = 0
```

Le service fonctionne sans son ; le lancement du jeu reste le retour visuel.

---

## 8. Pourquoi pas de notification (toast) à l'écran ?

Techniquement, **Recalbox 9 n'offre aucun canal** permettant à un script
d'afficher un message dans l'interface :

* le frontend **écrit** ses événements dans MQTT
  (`Recalbox/EmulationStation/Event`) ; seul un module interne (l'API web) s'y
  abonne, pour ses propres besoins — aucun texte n'est affiché à l'écran ;
* l'API web du frontend (`/api/...`) est en lecture (systèmes, jeux, BIOS,
  médias, configuration) : aucune route pour afficher un message ;
* le seul point d'entrée externe est la commande UDP `START|systeme|jeu`
  utilisée par ce projet, qui ne transporte pas de texte.

Les seuls affichages possibles viennent donc de Recalbox lui-même : l'écran de
chargement du jeu (nom + jaquette), qui sert de confirmation visuelle.

Le retour immédiat (mode association, badge inconnu, erreur) est assuré par des
bips sonores. Ils sont générés localement, sans dépendance.

Si une future version de Recalbox expose une API de notification, le module
`feedback.py` est le seul à modifier (une méthode `toast(message)` suffirait).

---

## 9. Deux instances / comportement erratique

Le service prend un verrou (`flock`) : une deuxième instance s'arrête
immédiatement en écrivant « Une autre instance du service tourne deja ».

```sh
ps aux | grep rfid
cat /recalbox/share/system/rfid/rfid.pid
$RFID restart
```

---

## 10. Réinitialisation complète

```sh
$RFID stop
cp /recalbox/share/system/rfid/tags.json /recalbox/share/tags-sauvegarde.json
sh /recalbox/share/system/rfid/uninstall.sh --keep-data
sh /recalbox/share/recalbox-rfid/install.sh --start
```

En dernier recours, supprimez `/recalbox/share/system/rfid` et réinstallez.

---

## 11. Où trouver les journaux

| Journal | Chemin |
| --- | --- |
| Service RFID | `/recalbox/share/system/rfid/logs/rfid.log` |
| Agent WebSocket | `/recalbox/share/system/rfid/logs/agent.log` |
| Installations | `/recalbox/share/system/rfid/logs/install.log` |
| Sortie de `rfidctl start` | `/recalbox/share/system/rfid/logs/service.out` |
| Frontend Recalbox | `/recalbox/share/system/logs/emulationstation.log` |
| Lancement d'un jeu | `/recalbox/share/system/logs/es_launch_stdout.log` |
| Démarrage système | commande `recallog` / `dmesg` pour le SPI |

---

## 12. L'agent WebSocket ne démarre pas

L'agent est lancé par le script permanent
`recalbox-rfid-agent(permanent).py3`, au démarrage de l'interface Recalbox.

1. **Le script est-il en place ?**
   `ls -l /recalbox/share/userscripts/` doit lister
   `recalbox-rfid(permanent).py3` **et**
   `recalbox-rfid-agent(permanent).py3`.
2. **Que dit son journal ?**
   `cat /recalbox/share/system/rfid/logs/agent.log` : on doit y lire
   « Agent WebSocket pret sur ws://…:8765 ».
3. **Le port est-il occupé ?** `netstat -ltnp | grep 8765`. Si oui, changez
   `port` dans `[agent]` de `config.ini` (et le port saisi dans `installer.html`).
4. **L'agent est-il activé ?** `[agent] enabled = 1` dans `config.ini`.
5. **Recalbox a-t-il redémarré ?** Le script n'est lu qu'au démarrage de
   l'interface : après l'avoir copié, redémarrez (`QUITTER` > `REDÉMARRER`).
6. **Test manuel** (SSH) :

   ```sh
   python3 /recalbox/share/system/rfid/app/main.py agent --home /recalbox/share/system/rfid
   ```

   La commande affiche `ws://…:8765` et le chemin du jeton. `Ctrl+C` pour
   arrêter.
7. Si l'interface d'EmulationStation ne démarre pas (écran noir), aucun script
   utilisateur ne tourne : utilisez SSH avec `install.sh --start`.

## 13. `installer.html` ne se connecte pas

| Symptôme | Cause probable |
| --- | --- |
| « connexion impossible » | agent arrêté, mauvaise IP, port différent de 8765 |
| « jeton refusé » | jeton mal recopié (espaces, minuscules) ou `token.txt` supprimé puis recréé |
| « délai dépassé » | adresse injoignable : testez `ping recalbox.local`, préférez l'IP |
| rien ne se passe | la page doit être ouverte **depuis le disque** (`file://`) : ouverte depuis un site `https://`, le navigateur bloque `ws://` (mixed content) |

À vérifier :

1. **La page est-elle bien `installer.html` du projet ?** (pas une ancienne
   copie ni l'ancienne interface web).
2. **L'adresse** : `recalbox.local` ou l'IP affichée dans
   `RÉSEAU` > `INFORMATIONS` ; le port `8765`.
3. **Le jeton** : `\\RECALBOX\share\system\rfid\token.txt`. Utilisez le bouton
   « Charger token.txt… » plutôt qu'un copier-coller.
4. **Le jeton n'existe pas ?** Il est créé au premier démarrage de l'agent.
   Redémarrez Recalbox puis rechargez la page.
5. **Un bloqueur / proxy d'entreprise** peut interdire les WebSocket : essayez
   un autre navigateur (Edge, Chrome, Firefox) ou un autre poste.

### « Le lanceur n'est pas installé » alors qu'il l'est

La page indique l'état du dossier `/recalbox/share/system/rfid`. Si le programme
a été installé ailleurs (variable `RFID_HOME`), l'agent ne le voit pas :
réinstallez avec le chemin par défaut, ou lancez l'agent avec
`python3 <dossier>/app/main.py agent --home <dossier>`.

### L'installation échoue

La page affiche le journal complet ; on le retrouve dans `logs/install.log`.
Causes fréquentes :

| Message | Cause / solution |
| --- | --- |
| `install.sh introuvable` | le dossier du projet n'a pas été copié sur `\\RECALBOX\share` |
| `/bin/sh est necessaire` | l'agent tourne hors Recalbox (PC de test) |
| `Permission denied` | l'agent ne tourne pas en root : il doit être lancé par Recalbox (userscript) |
| installation OK mais lecteur absent | le SPI n'est pas encore actif : redémarrer Recalbox |

### Jeton perdu ou à changer

* Le lire sur le partage : `\\RECALBOX\share\system\rfid\token.txt` ;
* pour le régénérer : supprimez ce fichier puis redémarrez Recalbox (il est
  recréé au démarrage de l'agent) — pensez à ressaisir le nouveau jeton dans
  `installer.html`.

### « Connecter » ne trouve pas le jeton

| Message / symptôme | Cause / solution |
| --- | --- |
| demande le dossier puis « jeton introuvable » | l'agent n'a jamais démarré : redémarrez Recalbox (`token.txt` est créé au démarrage de l'agent) |
| « jeton vide » | même cause, ou fichier tronqué : supprimez `token.txt` et redémarrez |
| « ce navigateur ne permet pas la lecture du partage » | Firefox/Safari : utilisez « Charger token.txt… » ou Edge/Chrome |
| autorisation refusée | recliquez sur « Connecter » et acceptez l'accès au dossier ; sinon « Charger token.txt… » |
| accès au dossier impossible | Windows ne s'authentifie pas au partage : lancez `acces-recalbox.cmd` (bouton « Autoriser Windows… ») ou `net use Z: \\RECALBOX\share /user:root recalboxroot` |

Le jeton est mémorisé dans le navigateur par sécurité uniquement pour la
connexion ; il reste sur le partage (`system/rfid/token.txt`).

### Faut-il l'exposer sur Internet ?

**Non.** L'agent permet d'installer du code et de redémarrer la Recalbox : il
doit rester sur le réseau local. Pour un accès à distance, utilisez un VPN
(WireGuard, Tailscale…), jamais une redirection du port 8765.

---

## 14. La copie des fichiers depuis la page échoue

La copie utilise l'API **File System Access** (`showDirectoryPicker`), disponible
uniquement dans **Edge et Chrome**. Causes fréquentes :

| Symptôme | Cause / solution |
| --- | --- |
| « Windows a protégé votre PC » au double-clic | fichier téléchargé : *Informations complémentaires* → *Exécuter quand même* (ou clic droit → Propriétés → Débloquer) |
| `ECHEC : acces au partage impossible` | adresse/mot de passe : ouvrir le `.cmd` avec le Bloc-notes, corriger `set HOST=` et `set PASS=` ; ou autoriser les invités (voir plus bas) |
| `ECHEC : decompression impossible` | `certutil`/`tar` absents : Windows 10 1803+ requis, sinon la page bascule sur PowerShell |
| `ECHEC : copie vers le partage` | partage en lecture seule ou session expirée : relancer le `.cmd` |
| Le bouton ne fait rien | navigateur non compatible (Firefox, Safari) : copiez le dossier à la main (méthode 2) |
| « Sélection annulée » | boîte de dialogue fermée : recommencez et choisissez le partage |
| « pas de dossier roms ici » | mauvais dossier choisi : sélectionnez `\\RECALBOX\share` (celui qui contient `roms`, `system`, `bios`…) |
| « Erreur d'écriture » / permission | partage non monté ou en lecture seule : vérifiez `\\RECALBOX\share` dans l'Explorateur |
| Aucun fichier écrit | antivirus/proxy bloquant l'API ; essayez l'installateur `.cmd` ou la méthode manuelle |

Après une copie réussie, la page affiche
`\\RECALBOX\share\recalbox-rfid` : redémarrez Recalbox pour que l'agent démarre.

### `\\RECALBOX\share` demande un identifiant

C'est le comportement normal des **Windows 11 24H2 et plus** : le partage
Recalbox est un partage « invité », et Windows refuse par défaut les sessions
invitées (il demande donc des identifiants).

1. **Compte Recalbox** (créé à chaque démarrage par `S35securepasswd`) :

   * utilisateur : `root`
   * mot de passe : `recalboxroot` (valeur par défaut)

2. **Ou autoriser les invités** (plus de mot de passe) — PowerShell **en
   administrateur** :

   ```powershell
   Set-SmbClientConfiguration -EnableInsecureGuestLogons $true
   ```

   Équivalent graphique : `gpedit.msc` → Configuration ordinateur → Modèles
   d'administration → Réseau → Station de travail Lanman → « Activer les
   ouvertures de session invité non sécurisées ».

   ⚠️ Ce réglage assouplit la sécurité SMB de **tout** le poste : à réserver à un
   réseau domestique.

Nettoyage si Windows a mémorisé de mauvais identifiants :

```cmd
net use \\RECALBOX\share /delete
cmdkey /delete:RECALBOX
```

### « Mot de passe incorrect » avec `root` / `recalboxroot`

D'après le script de démarrage Recalbox (`S35securepasswd`), le compte Samba
`root` reçoit :

* `recalboxroot` **si** `system.default_password` est vide (cas par défaut) ;
* un mot de passe **vide** si `system.default_password` est renseigné (bug du
  script : la variable `MASTERPASSWD` n'est alors jamais définie) — Windows
  refuse les mots de passe vides, donc la connexion échoue.

Vérifier le réglage (SSH) :

```sh
grep default_password /recalbox/share/system/recalbox.conf
```

Puis, quelle que soit la valeur, définir un mot de passe Samba explicite :

```sh
smbpasswd -a root        # tape deux fois le mot de passe voulu
pdbedit -L               # doit afficher : root:<uid>:...
```

et utiliser ce mot de passe (dans le `.cmd`, modifiez la ligne `set PASS=...`).

Autres causes du même message :

| Code `net use` | Signification |
| --- | --- |
| 1326 | identifiants refusés (mot de passe personnalisé, cache Windows) |
| 53 | nom/adresse introuvable → essayez l'IP |
| 67 | partage introuvable → `system.samba.enabled=1` dans `recalbox.conf` |
| 1272 | bloqué par une stratégie (voir ci-dessus, accès invité) |

Pour tester sans cache Windows, utilisez l'adresse **IP** plutôt que le nom :

```cmd
net use \\192.168.1.50\share /user:root recalboxroot
```

Pour supprimer les dialogues dans le sélecteur de dossier, montez le partage en
lecteur avant de cliquer sur « Copier » :

```cmd
net use Z: \\RECALBOX\share /user:root recalboxroot /persistent:yes
```

> `\\RECALBOX` sans `\share` n'est pas parcourable — c'est normal, seul le
> partage nommé est exposé. Utilisez `\\RECALBOX\share` ou
> `\\<adresse-ip>\share`.

Si `root` / `recalboxroot` est refusé, le mot de passe racine a probablement été
personnalisé : en SSH, `smbpasswd -a root` permet de définir le mot de passe
Samba (le compte doit correspondre à un utilisateur existant). Sinon, utilisez la
copie manuelle (méthode B) ou l'installation par SSH (méthode C).

Un test réseau utile (invite de commandes) :

```cmd
net view \\RECALBOX
dir \\RECALBOX\share
```

## 15. Le fichier unique est périmé

`dist/recalbox-rfid-installer-<version>.html` est généré à partir des sources.
Si une version différente de `VERSION` est affichée dans la page, ou si les
fichiers copiés ne correspondent pas au code :

```sh
python tools/build_installer.py
```

Puis remplacez votre ancien fichier par le nouveau. La suite de tests
(`python tests/run_tests.py`) échoue volontairement si le fichier livré n'est
plus à jour.
