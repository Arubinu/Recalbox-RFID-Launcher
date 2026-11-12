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

**Recalbox 10 (Raspberry Pi 3, vérifié) :** la ligne doit être dans
`/boot/config.txt` — le fichier `/boot/recalbox-user-config.txt` **n'est pas
appliqué** par cette version, même s'il est présent et bien rempli.

```sh
grep -n "dtparam=spi" /boot/config.txt
mount -o remount,rw /boot
# ajoutez la ligne dans la section globale (avant les sections [pi3], [pi4]…)
grep -q '^dtparam=spi=on' /boot/config.txt || \
  sed -i 's/^dtparam=audio=on$/dtparam=audio=on\ndtparam=spi=on/' /boot/config.txt
mount -o remount,ro /boot
reboot
```

L'installateur fait cela tout seul depuis la version 2.3.0 (avec sauvegarde
`/boot/config.txt.bak-rfid-launcher`). Pour les versions antérieures de
Recalbox, `dtparam=spi=on` dans `/boot/recalbox-user-config.txt` suffit.

Ou relancez l'installateur (il écrit dans les deux fichiers) :

```sh
sh /recalbox/share/system/rfid/install.sh
```

Puis vérifiez après redémarrage : `ls -l /dev/spidev0.0`
(`spidev0.0` **et** `spidev0.1` apparaissent).

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

**Commencez par « Tester avec un badge »** (onglet **Matériel** de
`installer.html`) : le test lit le lecteur pendant 5 secondes et distingue les
trois seules causes possibles.

| Ce que dit le test | Ce que ça veut dire | Quoi faire |
| --- | --- | --- |
| UID affiché | le badge est lu, il n'était simplement pas associé | l'associer (onglet Badges) |
| « le badge répond mais la lecture complète échoue » (code ATQA) | le badge est bien 13,56 MHz mais exotique | noter le code ATQA ; l'UID partiel est dans le journal |
| « aucune carte 13,56 MHz vue » avec un badge | soit le badge n'est pas 13,56 MHz, soit le lecteur ne voit rien | refaire le test **avec une carte bancaire sans contact** |
| « aucune carte » aussi avec une carte bancaire | le lecteur ne voit aucune carte | antenne ou câblage : voir la section 3 |

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
7. **Recalbox 10 / noyau 6.12 :** si le journal montre
   « export de la broche 17 impossible : Invalid argument » et un backend
   `/sys/class/gpio`, c'est que l'ancienne interface sysfs est refusée. Depuis la
   version 2.3.0, le backend `RPi.GPIO` est utilisé (le service change
   temporairement de répertoire de travail, car lgpio crée ses tubes de
   notification dans le dossier courant et le système est en lecture seule).
   Après mise à jour, redémarrez le service (`rfidctl restart`) : le journal doit
   afficher `GPIO : backend RPi.GPIO`.

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

   La commande affiche `ws://…:8765` et rappelle que l'autorisation se donne au
   bouton. `Ctrl+C` pour arrêter.
7. Si l'interface d'EmulationStation ne démarre pas (écran noir), aucun script
   utilisateur ne tourne : utilisez SSH avec `install.sh --start`.

## 13. `installer.html` ne se connecte pas

| Symptôme | Cause probable |
| --- | --- |
| « Impossible de joindre la Recalbox après 3 tentatives » | l'agent ne tourne pas : Recalbox **pas redémarrée** depuis l'installation, mauvaise adresse, ou userscript de l'agent absent |
| « Le service du lecteur est arrêté » | sans le service, personne ne surveille le bouton : Maintenance → **Démarrer** |
| « Une autre demande d'autorisation est déjà en attente » | une seule demande à la fois (30 s) : attendez la fin du compte à rebours et recommencez |
| « Le bouton n'a pas été maintenu assez longtemps » | il faut **3 secondes** d'appui continu pendant le compte à rebours |
| « La Recalbox répond mais n'autorise plus ce poste » | la Recalbox a redémarré, le service a été relancé ou le programme a été mis à jour : cliquez sur « Se connecter » et gardez le bouton appuyé 3 s |
| « Le délai de 30 s est écoulé sans appui sur le bouton » | une seule demande à la fois : recommencez « Se connecter », puis 3 s d'appui continu pendant le compte à rebours |
| « délai dépassé » | adresse injoignable : testez `ping recalbox.local`, préférez l'IP |
| rien ne se passe | la page doit être ouverte **depuis le disque** (`file://`) : ouverte depuis un site `https://`, le navigateur bloque `ws://` (mixed content) |

À vérifier :

1. **La page est-elle bien `installer.html` du projet ?** (pas une ancienne
   copie ni l'ancienne interface web).
2. **La Recalbox a-t-elle redémarré depuis l'installation ?** C'est au démarrage
   que le programme est installé et que l'agent démarre, avec son secret de
   session. Sans ce redémarrage, la page ne peut rien joindre.
3. **L'autorisation** : « Se connecter », puis **bouton du boîtier maintenu
   3 secondes** pendant le compte à rebours (30 s). Une seule demande à la fois,
   et elle est refusée si le service du lecteur est arrêté. Rien à recopier :
   aucun fichier ne contient de secret. Un seul repli, `rfidctl pair` en SSH :
   il réouvre la fenêtre de 30 s et n'affiche aucun jeton.
4. **L'adresse** : `recalbox.local` ou l'IP affichée dans
   `RÉSEAU` > `INFORMATIONS` ; le port `8765`. En cas de doute :
   « Faire un diagnostic » (bouton dans l'aide de l'écran de connexion) teste le
   port.
5. **Un bloqueur / proxy d'entreprise** peut interdire les WebSocket : essayez
   un autre navigateur (Edge, Chrome, Firefox) ou un autre poste.

### L'appui long sur le bouton ne confirme pas

Vérifiez, dans cet ordre :

1. **Le service tourne** (onglet Maintenance) : c'est lui qui lit le bouton ;
   l'agent seul ne suffit pas.
2. **Le bouton est reconnu** (onglet Matériel) : sinon, câblage GPIO17 → masse.
3. **L'appui est continu** : 3 secondes, sans relâcher, *après* avoir cliqué sur
   « Se connecter » (la demande n'est valable que 30 s). Un appui commencé avant
   la demande est ignoré, par sécurité.
4. Pendant une demande d'autorisation, l'appui long **ne déclenche pas**
   l'effacement d'un badge : c'est volontaire.

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

### L'autorisation est perdue

Il n'y a plus rien à lire ni à recopier : le secret de session n'existe qu'en
mémoire et il est renouvelé à chaque démarrage de l'agent. Les anciens fichiers
`system/rfid/token.txt` et `system/rfid/paired.ok` sont supprimés tout seuls au
démarrage de l'agent.

* la page indique que la Recalbox demande une nouvelle autorisation : cliquez sur
  « Se connecter » et gardez le bouton appuyé **3 secondes** ;
* c'est le cas après un redémarrage de la Recalbox, un redémarrage du service ou
  une mise à jour du programme ;
* pour retirer l'autorisation d'un poste (ordinateur prêté, revendu…) : redémarrez
  l'agent ou la Recalbox, un nouvel appui sera exigé.

### « Se connecter » n'autorise pas ce poste

Les messages de la page sont listés au §13. Les causes les plus fréquentes :

* **le service du lecteur est arrêté** : personne ne surveille le bouton —
  Maintenance → **Démarrer** ;
* **l'appui est trop court, ou commencé trop tôt** : 3 secondes d'appui continu,
  *après* avoir cliqué sur « Se connecter » ;
* **une autre demande est déjà en attente** : une seule à la fois, 30 s ;
* **la page n'est pas ouverte depuis le disque** (`file://`) : le navigateur
  bloque `ws://` depuis un site `https://`.

La page garde l'autorisation dans le navigateur (localStorage) : une actualisation
ne redemande rien, mais un redémarrage de l'agent l'annule.

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
| Reste bloqué à « 1/4 Connexion au partage » | Windows attendait une réponse à une question invisible (connexion déjà ouverte / mot de passe) : utilisez la page 1.6.1 ou plus, voir « Le `.cmd` reste bloqué » plus bas |
| `ECHEC : decompression impossible` | `certutil`/`tar` absents : Windows 10 1803+ requis, sinon la page bascule sur PowerShell |
| `ECHEC : copie vers le partage` | partage en lecture seule ou session expirée : relancer le `.cmd` (le code `robocopy` affiché aide : 8 = fichiers non copiés, 16 = erreur grave) |
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

### Le bouton « Faire un diagnostic »

Dans `installer.html`, allez sur l'écran **« Gérer mes badges »** (connexion),
ouvrez **« La connexion ne marche pas ? »** puis cliquez sur
**« Faire un diagnostic »** : la page télécharge `diagnostic-recalbox.cmd`, à
double-cliquer. Il n'installe rien et n'écrit rien, il affiche :

1. le nom et l'adresse IP résolus (ou l'échec de résolution) ;
2. l'état des ports **445** (partage) et **8765** (agent), testés en TCP ;
3. la connexion au partage avec les trois jeux d'identifiants (root, root sans
   mot de passe, invité) et le code d'erreur éventuel ;
4. la présence de `recalbox-rfid\install.sh`, des deux userscripts et d'une
   éventuelle demande d'autorisation en attente (`system\rfid\pair-pending.json`) ;
5. le contenu de `system\rfid` ;
6. le rappel des codes `net use` et la bonne façon d'écrire le chemin.

C'est le rapport à transmettre en cas de problème : il dit en une capture si
l'installation est incomplète, si le partage est refusé ou si l'agent ne tourne
pas.

Si `root` / `recalboxroot` est refusé, le mot de passe racine a probablement été
personnalisé : en SSH, `smbpasswd -a root` permet de définir le mot de passe
Samba (le compte doit correspondre à un utilisateur existant). Sinon, utilisez la
copie manuelle (méthode B) ou l'installation par SSH (méthode C).

Un test réseau utile (invite de commandes) :

```cmd
net view \\RECALBOX
dir \\RECALBOX\share
```

### Le `.cmd` reste bloqué à « 1/4 Connexion au partage »

Deux causes possibles, corrigées dans cet ordre.

**1) Une question invisible (1.6.0 et antérieures).** Les sorties de `net use`
étaient redirigées vers `nul`, donc une question de Windows restait cachée et le
script attendait indéfiniment :

* `net use \\RECALBOX\share /delete` demande « Des fichiers sont ouverts sur cette
  connexion, voulez-vous continuer ? » quand le partage est ouvert dans
  l'Explorateur ;
* `net use` demande un mot de passe quand Windows exige des identifiants.

Depuis 1.6.1, toutes les commandes sont lancées avec `<nul` : une question
échoue au lieu d'attendre.

**2) Une attente TCP de 20 à 60 s par essai (1.7.1 et antérieures).** Si le nom
résout vers une **ancienne adresse IP** (bail DHCP changé) ou si Windows essaie
**IPv6 en premier**, `net use` attend la fin des tentatives TCP avant d'échouer :
la fenêtre semble figée sur « essai 1 » pendant une minute.

Depuis **1.7.2**, l'étape 1 est bornée :

1. un seul appel PowerShell résout l'adresse IPv4 et **teste le port 445 avec un
   délai maximum de 1,5 s** ;
2. port injoignable → message **`ECHEC RAPIDE`** (≈ 3 s au total) qui rappelle
   les vérifications (Recalbox allumée, même réseau, adresse IP changée) et
   s'arrête sans tenter `net use` ;
3. port joignable → trois essais seulement (chacun ≈ 2 s de négociation SMB) :
   `root`, `root` sans mot de passe, invité. Les essais se font **sur l'adresse
   IP**, jamais sur le nom ;
4. la méthode retenue est affichée : `OK  (methode : root sans mot de passe)`.

> L'essai 2 (« `root` sans mot de passe ») couvre le cas où Recalbox n'a pas créé
> le mot de passe Samba par défaut (voir « Mot de passe incorrect » plus bas).
> Sur cette configuration, les codes `86` / `1326` (« Le mot de passe réseau
> spécifié est incorrect ») sont attendus pour l'essai 1 — c'est l'essai 2 qui
> passe.

Si l'étape 1 reste silencieuse plus de quelques secondes : `Ctrl+C`, puis
lancez le **diagnostic** (« Faire un diagnostic » dans la page) qui dit si le
partage répond.

Il n'y a pas de blocage possible non plus au moment de la copie : le script de
démarrage est copié par **quatre méthodes successives** (robocopy depuis le
partage, `copy` depuis le partage, robocopy depuis les fichiers temporaires,
puis recherche du fichier `recalbox-rfid-agent*.py3` dans toute l'arborescence
temporaire), chacune suivie d'une vérification de présence. Si les quatre
échouent, le `.cmd` indique si les sources sont présentes et rappelle la copie
manuelle : `recalbox-rfid\bootstrap\recalbox-rfid-agent(permanent).py3` → dossier
`userscripts\` du partage.

En cas d'échec, testez à la main dans une invite de commandes (les messages
seront visibles) :

```cmd
ping RECALBOX
powershell Test-NetConnection RECALBOX -Port 445
net use \\RECALBOX\share /delete /y
net use \\RECALBOX\share /user:root recalboxroot
```

* `Test-NetConnection` en échec → réseau/pare-feu (port 445), Recalbox éteinte
  ou sur un autre réseau.
* code 1326 → mot de passe (voir la section suivante).
* code 1219 → une session existe déjà avec d'autres identifiants :
  `net use /delete` puis `cmdkey /delete:RECALBOX`.

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
