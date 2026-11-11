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
| Sortie de `rfidctl start` | `/recalbox/share/system/rfid/logs/service.out` |
| Frontend Recalbox | `/recalbox/share/system/logs/emulationstation.log` |
| Lancement d'un jeu | `/recalbox/share/system/logs/es_launch_stdout.log` |
| Démarrage système | commande `recallog` / `dmesg` pour le SPI |
