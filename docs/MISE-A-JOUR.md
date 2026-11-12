# Mise à jour

## Méthode automatique — copier un dossier plus récent puis redémarrer

1. Copiez le dossier de la nouvelle version (par exemple
   `recalbox-rfid-1.7.0`) sur `\\RECALBOX\share` (ou laissez l'installateur
   `.cmd` le faire).
2. Redémarrez Recalbox.

Au démarrage, le script permanent compare la version du dossier présent sur le
partage à celle qui est installée : si elle est **plus récente**, il l'installe
tout seul, puis redémarre le service. Les versions identiques ou plus anciennes
sont ignorées (pas de rétrogradation). Détail :
`/recalbox/share/system/rfid/logs/auto-install.log`.

## Régénérer l'installateur unique

Après chaque modification d'un fichier du projet :

```sh
python tools/build_installer.py
```

Le fichier `dist/recalbox-rfid-installer.html` est reconstruit avec le
contenu à jour. Un test échoue si le fichier livré n'est pas régénéré.

## Principe

Le programme est installé dans un dossier **avec** ses données :

```
/recalbox/share/system/rfid/
├── app/         <- programme (remplacé à chaque mise à jour)
├── config.ini   <- VOTRE configuration (conservée)
├── tags.json    <- VOS badges (conservés)
├── logs/
├── rfidctl
├── installer.html
├── install.sh   <- copie de l'installateur
├── uninstall.sh
└── VERSION      <- version installée
```

La mise à jour **remplace uniquement `app/`** (et les fichiers de programme),
puis l'agent se recharge et redémarre le service. Configuration et badges ne sont
jamais touchés. Aucun secret n'est stocké dans ce dossier : l'agent tire un
nouveau secret de session à chaque démarrage, donc l'autorisation est à redonner
après chaque mise à jour (appui de 3 s sur le bouton).

## Méthode 1 — depuis `installer.html` (aucune ligne de commande)

1. Double-cliquez sur `installer.html`, renseignez l'adresse et le port `8765`,
   puis cliquez sur « Se connecter » et gardez le bouton du boîtier appuyé
   3 secondes (compte à rebours de 30 s).
2. Ouvrez **« Mettre à jour depuis un fichier ZIP ou une adresse »** (dernière
   carte, tout en bas) puis **« Choisir un fichier ZIP »** : l'archive est
   envoyée par WebSocket depuis le PC, installée sur la Recalbox, et le journal
   s'affiche ;
3. ou collez une URL puis cliquez sur « Installer depuis cette adresse ».

L'agent se recharge tout seul avec la nouvelle version (la page se reconnecte et
demande une nouvelle autorisation : un appui de 3 s sur le bouton suffit), puis il
suffit de cliquer sur **« Redémarrer la Recalbox »** (carte « Installation et
service ») si le SPI vient d'être activé.

Le ZIP doit contenir `install.sh` à sa racine (ou dans un sous-dossier).

## Méthode 2 — nouvelle version copiée sur le partage

1. Copiez le nouveau dossier (par exemple `recalbox-rfid-1.1.0`) sur
   `\\RECALBOX\share`.
2. Lancez :

   ```powershell
   ssh root@recalbox.local "sh /recalbox/share/recalbox-rfid-1.1.0/install.sh --upgrade"
   ```

3. Vérifiez la version :

   ```sh
   /recalbox/share/system/rfid/rfidctl version
   ```

Le service redémarre automatiquement s'il tournait (aucun redémarrage de
Recalbox nécessaire, sauf si le SPI vient d'être activé).

## Méthode 3 — depuis une URL (mise à jour à distance)

Hébergez un ZIP du projet (contenu du dossier `recalbox-rfid`, avec `install.sh`
à la racine), par exemple sur GitHub Releases, sur un serveur web personnel ou
sur un NAS. Ensuite, soit dans `installer.html` (champ URL), soit en SSH :

```sh
/recalbox/share/system/rfid/rfidctl self-update https://exemple.fr/recalbox-rfid-1.3.0.zip
```

Ou :

```sh
sh /recalbox/share/system/rfid/install.sh --from-url https://exemple.fr/recalbox-rfid-1.3.0.zip
```

Le ZIP est téléchargé avec `curl` (présent dans Recalbox), décompressé avec
`python3 -m zipfile`, puis l'installateur de la nouvelle version est exécuté en
mode `--upgrade`.

Astuce : pour ne pas retaper l'URL, notez-la dans `config.ini` :

```ini
[update]
url = https://exemple.fr/recalbox-rfid.zip
```

`rfidctl self-update` sans argument utilisera alors cette URL. Sans URL
configurée, la commande réinstalle simplement la version locale (utile pour
réparer une installation).

## Méthode 4 — depuis la console Recalbox

```sh
sh /recalbox/share/system/rfid/install.sh --upgrade
```

La copie de `install.sh` présente dans le dossier d'installation réinstalle la
version… déjà installée. Pour une nouvelle version, utilisez la méthode 2 ou 3.

## Fabriquer le ZIP de distribution

Depuis le dossier du projet (Windows, PowerShell) :

```powershell
Compress-Archive -Path app, userscript, bootstrap, docs, tools, dist, installer.html, `
                  install.sh, uninstall.sh, VERSION, README.md, CHANGELOG.md `
                 -DestinationPath recalbox-rfid-1.4.0.zip
```

Depuis un système Unix :

```sh
zip -r recalbox-rfid-1.4.0.zip app userscript bootstrap docs tools dist installer.html \
                              install.sh uninstall.sh VERSION README.md CHANGELOG.md
```

Le ZIP doit contenir `install.sh` **à sa racine** (ou dans un unique
sous-dossier : l'installateur le retrouve).

## Retour arrière

Réinstallez l'ancienne version avec la méthode 2 (`install.sh --upgrade`).
Les données restent compatibles : le format de `tags.json` est versionné
(`"schema": 1`) et n'a pas changé.

Avant toute mise à jour importante, gardez une copie de :

```sh
cp /recalbox/share/system/rfid/tags.json /recalbox/share/tags-sauvegarde.json
```

## Vérifier ce qui est installé

```sh
/recalbox/share/system/rfid/rfidctl version   # version du programme
cat /recalbox/share/system/rfid/VERSION       # version du paquet installé
/recalbox/share/system/rfid/rfidctl status    # service + uptime
```

## En cas d'échec

* `rfidctl logs` ou `cat /recalbox/share/system/rfid/logs/rfid.log` ;
* si le service ne démarre pas, `logs/service.out` contient la sortie de la
  tentative de démarrage manuelle ;
* relancer l'installateur est sans danger (idempotent) ;
* pour repartir d'une base saine : `rfidctl restart`, puis au besoin
  `rfidctl self-update ...` à nouveau.
