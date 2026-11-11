# Mise à jour

## Principe

Le programme est installé dans un dossier **avec** ses données :

```
/recalbox/share/system/rfid/
├── app/         <- programme (remplacé à chaque mise à jour)
├── config.ini   <- VOTRE configuration (conservée)
├── tags.json    <- VOS badges (conservés)
├── logs/
├── rfidctl
├── install.sh   <- copie de l'installateur (pour la mise à jour en ligne)
├── uninstall.sh
└── VERSION      <- version installée
```

La mise à jour **remplace uniquement `app/`** (et les fichiers de programme),
puis redémarre le service. Configuration et badges ne sont jamais touchés.

## Méthode 1 — nouvelle version copiée sur le partage (recommandée pour tester)

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

## Méthode 2 — depuis une URL (mise à jour à distance)

Hébergez un ZIP du projet (contenu du dossier `recalbox-rfid`, avec `install.sh`
à la racine), par exemple sur GitHub Releases, sur un serveur web personnel ou
sur un NAS.

```sh
/recalbox/share/system/rfid/rfidctl self-update https://exemple.fr/recalbox-rfid-1.1.0.zip
```

Ou :

```sh
sh /recalbox/share/system/rfid/install.sh --from-url https://exemple.fr/recalbox-rfid-1.1.0.zip
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

## Méthode 3 — depuis la console Recalbox

```sh
sh /recalbox/share/system/rfid/install.sh --upgrade
```

La copie de `install.sh` présente dans le dossier d'installation réinstalle la
version… déjà installée. Pour une nouvelle version, utilisez la méthode 1 ou 2.

## Fabriquer le ZIP de distribution

Depuis le dossier du projet (Windows, PowerShell) :

```powershell
Compress-Archive -Path app, userscript, docs, tests, install.sh, uninstall.sh, VERSION, README.md, CHANGELOG.md `
                 -DestinationPath recalbox-rfid-1.1.0.zip
```

Depuis un système Unix :

```sh
zip -r recalbox-rfid-1.1.0.zip app userscript docs tests install.sh uninstall.sh VERSION README.md CHANGELOG.md
```

Le ZIP doit contenir `install.sh` **à sa racine** (ou dans un unique
sous-dossier : l'installateur le retrouve).

## Retour arrière

Réinstallez l'ancienne version avec la méthode 1 (`install.sh --upgrade`).
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
