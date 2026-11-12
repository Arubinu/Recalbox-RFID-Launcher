# Historique des versions

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
versionnage sémantique. La version courante est aussi dans le fichier `VERSION`
et affichée par `rfidctl version`.

## [2.0.0]

### Ajouté

* **Appairage confirmé physiquement au bouton.** Plus besoin de relancer le `.cmd`
  pour autoriser un navigateur :
  1. la page dépose une **demande d'appairage** — une seule à la fois, valable
     **30 secondes** ;
  2. la Recalbox attend un **appui continu de 3 secondes** sur le bouton du
     boîtier (preuve de présence) ;
  3. le service enregistre un accord qui porte l'identifiant exact de la demande,
     et la page échange cet accord contre le jeton, **une seule fois**.
* **Protection contre la course entre demandes** : un accord donné pour la
  demande A ne peut jamais valider la demande B, même si celle-ci arrive juste
  après l'expiration de A (l'identifiant et l'échéance de la demande sont
  recopiés dans l'accord). Un appui commencé **avant** la demande est également
  refusé (marge de 250 ms) : impossible de valider une demande qui n'était pas
  la vôtre en gardant le doigt posé.
* Nouveaux gestes du bouton : appui court = associer, appui long (2 s) =
  effacer, **appui très long (3 s) = confirmer l'appairage**. Pendant une
  demande d'appairage, l'appui long n'arme pas l'effacement.
* Réglage `hold_press_s` dans `config.ini` (`[button]`) pour ajuster la durée de
  confirmation.
* Commandes d'agent `pair.request` / `pair.check` / `pair.cancel`, réservées au
  réseau local et refusées si le service du lecteur est arrêté.

### Modifié

* L'écran « Se connecter » explique l'appui de 3 secondes et affiche un compte à
  rebours pendant l'attente (« Gardez le bouton appuyé 3 s… il reste 24 s ») ; le
  bouton est désactivé pendant la demande.
* Les messages d'erreur distinguent : service arrêté, demande déjà en attente,
  appui trop court, agent injoignable.
* Le fichier `pair-request` et `rfidctl pair` restent disponibles comme solution
  de secours quand le service ne tourne pas.

## [1.9.2]

### Modifié

* Écran **Se connecter** : le bouton « Se connecter » est **aligné à droite** de
  la carte, comme une action de formulaire.
* Le bouton « J'ai le fichier token.txt » disparaît : il devient une **icône
  d'import placée dans le champ « Jeton »** (au survol : « Importer le fichier
  token.txt »). Le champ réserve la place de l'icône, et le message d'état
  s'affiche sur sa propre ligne.
* Documentation alignée (l'icône remplace le bouton).

## [1.9.1]

### Modifié

* **Boutons neutres, hiérarchie par la taille et non par la couleur** : plus de
  bleu saturé ni de rouge vif. Tous les boutons partagent la même surface
  discrète ; seuls les boutons structurants sont plus grands, et les actions
  destructrices (« Redémarrer la Recalbox », « Effacer un badge ») utilisent un
  liseré rouge sourd.
* **Barres d'actions** dans les onglets : les boutons ne flottent plus à gauche
  (ce qui imitait l'agencement des onglets). Chaque groupe est posé dans un
  encadré avec un intitulé à gauche (`MISE À JOUR`, `SERVICE`, `ASSOCIATION`) et
  les boutons alignés à droite.
* Sur l'écran de connexion, « Se connecter » et « J'ai le fichier token.txt » ont
  désormais **exactement le même style**.

### Corrigé

* Le message « aucun badge » du tableau s'affiche enfin centré sur toute la
  largeur (l'attribut `colspan` n'était pas posé par le générateur d'éléments).

## [1.9.0]

### Modifié

* **Refonte de l'interface : un choix, puis des écrans, sans défilement.**
  * l'accueil propose **deux tuiles visuelles** — *Installer sur la Recalbox* ou
    *Gérer mes badges* — au lieu d'enchaîner des blocs les uns sous les autres ;
  * chaque parcours occupe **un seul écran** (installation ou connexion), avec un
    bouton retour, et les explications longues sont repliées ;
  * une fois connecté, place à un **tableau de bord à onglets** (Badges,
    Matériel, Maintenance) qui tient dans la fenêtre : seule la liste des badges
    et les journaux défilent, jamais la page (hauteur fixe `100dvh`, grille
    `minmax(0, 1fr)`) ;
  * l'onglet **Matériel** affiche un **verdict en une phrase avec l'action à
    faire** (« Le bus du lecteur n'est pas encore activé → redémarrez la
    Recalbox »), calculé à partir de l'état réel ;
  * en-tête permanent : marque, version, état de connexion, `Déconnecter`, aide
    dans une boîte de dialogue (`<dialog>`).

### Corrigé

* Cascade CSS : les tuiles de l'accueil (des `<button>`) héritaient de la hauteur
  et du `nowrap` des boutons standards.
* Défilement horizontal résiduel sur mobile (colonne de grille élastique et
  `min-width: auto` des éléments flex) — la largeur est désormais bornée.
* Documentation alignée sur les nouveaux libellés (`J'ai le fichier token.txt`,
  onglet Maintenance, « Se connecter »).

## [1.8.3]

### Corrigé (Recalbox 10 : installation en échec et service arrêté)

* **`/boot` est monté en lecture seule sur Recalbox 9/10** : `install.sh`
  échouait en écrivant `dtparam=spi=on` (`cp: can't create … : Read-only file
  system`), `set -e` interrompait tout, le script renvoyait 1 et **le service
  n'était jamais démarré** (d'où un agent présent mais aucun lecteur de badges).
  * `install.sh` remonte désormais `/boot` en écriture (`mount -o remount,rw`),
    écrit la ligne, puis le remet en lecture seule ;
  * en cas d'échec d'écriture, il **avertit et continue** au lieu de tout
    interrompre, avec les instructions manuelles (`mount` en SSH ou partition
    `boot` de la carte SD).
* **Le script de démarrage lance le service même si l'installation retourne une
  erreur** : un échec partiel ne laisse plus la Recalbox sans lecteur.

### Ajouté

* L'agent honore la **demande d'appairage (`pair-request`) au moment où la page
  demande le jeton**, plus seulement au démarrage : relancer le `.cmd` suffit à
  réouvrir l'appairage, sans redémarrage.

## [1.8.2]

### Corrigé (cause racine de l'installation incomplète)

* **`robocopy` échouait silencieusement sur le partage Recalbox.** Le serveur
  Samba refuse la modification des **attributs du dossier** de destination
  (`ERREUR 50 : Cette demande n'est pas prise en charge`) ; `robocopy` abandonne
  alors la copie… **en renvoyant le code 0**, que l'installateur interprétait
  comme un succès. Résultat : le dossier `recalbox-rfid` était créé et **vide**,
  le démarrage ne trouvait aucun programme (`auto-install.log` :
  « dossier du projet introuvable ») et l'agent ne démarrait donc jamais.
  * les copies utilisent désormais `/DCOPY:D /COPY:D` (données seules, aucune
    écriture d'attribut) — vérifié sur une Recalbox réelle : 31 fichiers copiés,
    code 1 ;
  * **la réussite est vérifiée autrement que par le code** :
    `recalbox-rfid\install.sh` et `recalbox-rfid\app\main.py` doivent exister ;
  * si ce n'est pas le cas, un second essai passe par `xcopy` (qui n'écrit pas
    d'attributs de dossier), puis l'échec est annoncé clairement avec la cause ;
  * le même traitement est appliqué aux copies du script de démarrage.

## [1.8.1]

### Corrigé

* **Le message d'échec distingue enfin les deux causes**, qui n'ont rien à voir :
  * *« La Recalbox ne répond pas sur ws://… »* → l'agent n'est pas lancé
    (script de démarrage absent ou Recalbox non redémarrée), avec la marche à
    suivre : relancer le `.cmd`, redémarrer, recliquer ;
  * *« La Recalbox répond mais l'appairage automatique est fermé »* → l'agent
    tourne, la fenêtre a expiré : relancer le `.cmd` (il redemande un appairage)
    ou `rfidctl pair`.

### Ajouté

* **Demande d'appairage par fichier** : le `.cmd` dépose
  `system\rfid\pair-request` sur le partage ; au démarrage suivant, l'agent
  ouvre la fenêtre d'appairage. Plus besoin de SSH pour appairer un nouveau PC,
  même si un poste est déjà appairé.
* Le `.cmd` **attend l'agent jusqu'à 30 s** quand le jeton existe déjà (cas du
  « redémarrez puis relancez ») : il affiche `Agent pret.` et ouvre la page, ou
  prévient que l'agent ne répond pas encore et qu'il faut redémarrer.
* Le **diagnostic** lit désormais les journaux de la Recalbox depuis le partage :
  `logs\auto-install.log` (ce que le démarrage a fait) et `logs\rfid.log`, et
  indique si un poste est déjà appairé ou si une demande d'appairage est en
  attente. C'est le rapport qui dit pourquoi l'agent ne tourne pas.

## [1.8.0]

### Ajouté

* **Appairage automatique : plus aucun jeton à recopier, plus aucun fichier à
  chercher.** Au premier démarrage après l'installation, l'agent ouvre une
  **fenêtre d'appairage de 15 minutes** ; la page récupère alors le jeton toute
  seule quand on clique sur « Se connecter », sans partage réseau, sans
  Explorateur Windows et sans copier-coller.
  * transmission **une seule fois** (le fichier `pairing.json` est supprimé
    dès qu'un client l'a obtenu, et à la première authentification réussie) ;
  * la fenêtre se rouvre à chaque démarrage **tant qu'aucun poste ne s'est
    connecté** (marqueur `paired.ok`) : après une mise à jour ou une
    réinstallation, l'appairage fonctionne donc encore, sans SSH ;
  * **réseau local uniquement** (10/8, 172.16/12, 192.168/16, lien-local, `::1`) ;
    toute autre adresse est refusée avec un message explicite ;
  * `rfidctl pair` (en SSH) réouvre la fenêtre quand on veut appairer un autre
    PC plus tard.
* Le `.cmd` **ouvre la page même quand le jeton n'existe pas encore** : après le
  redémarrage, il n'y a plus qu'à cliquer sur « Se connecter ».
* Le statut de l'agent expose `agent.pairing` (fenêtre ouverte ou non).

### Modifié

* Étape 2 de la page : le champ « Jeton de sécurité » devient **facultatif**, le
  texte explique que la page le récupère seule, et l'aide « La récupération
  automatique ne marche pas ? » donne les solutions dans l'ordre (redémarrer,
  `rfidctl pair`, puis copie manuelle en dernier recours).
* Le diagnostic et la documentation ne renvoient plus à l'Explorateur en
  première intention.

## [1.7.3]

### Ajouté

* **Le jeton est vérifié avant la connexion** : un jeton Recalbox fait
  exactement 16 caractères hexadécimaux (`70C2633536122BAA`). S'il n'a pas cette
  forme, la page le dit et indique combien de caractères ont été reçus — un
  presse-papiers contenant autre chose (texte copié ailleurs) est ainsi repéré
  immédiatement, la connexion étant tout de même tentée.
* **Trois tentatives automatiques** espacées de 1,5 s quand l'agent ne répond
  pas : le temps que le service finisse de démarrer après un redémarrage.
* Message d'échec actionnable, qui distingue les deux cas :
  * agent muet → « Impossible de joindre la Recalbox après 3 tentatives » avec
    les trois causes (pas redémarrée depuis l'installation, mauvaise adresse,
    agent non installé) et le renvoi vers « Faire un diagnostic » ;
  * jeton refusé → « La Recalbox répond mais refuse le jeton » avec la marche à
    suivre.

### Modifié

* Le message de fin du `.cmd` (quand le jeton n'existe pas encore) dit
  explicitement que **le redémarrage est obligatoire** et pourquoi, puis invite à
  relancer le fichier après une minute.
* L'aide « Où trouver le jeton ? » montre la forme attendue du jeton.

### Corrigé

* Les scripts de test n'utilisent plus `clip` : ils n'écrasent plus le
  presse-papiers du poste (c'est ce qui y avait laissé un faux jeton de test à la
  place du vrai).

## [1.7.2]

### Corrigé

* **L'étape 1 du `.cmd` ne peut plus rester bloquée.** Le blocage venait de
  `net use`, qui attendait la fin des tentatives TCP vers une adresse morte
  (nom résolu vers une ancienne IP, ou IPv6 essayé d'abord) : 20 à 60 s par
  essai, sans rien afficher. L'étape 1 fait maintenant, dans un **seul appel
  PowerShell**, la résolution IPv4 puis un **test du port 445 limité à 1,5 s**.
  Port injoignable → message `ECHEC RAPIDE` immédiat (≈ 3 s) et arrêt, sans
  aucune tentative `net use` ; port joignable → les essais d'identifiants, qui
  répondent en ~2 s chacun.
* Les tentatives se font désormais **sur l'adresse IP** (jamais sur le nom), ce
  qui supprime l'attente IPv6/NetBIOS ; l'adresse trouvée est aussi utilisée
  pour ouvrir la page (`#host=`), donc l'interface se connecte du premier coup.
* Trois essais au lieu de cinq (chacun coûte ~2 s de négociation SMB) : `root`,
  `root` sans mot de passe, invité. La méthode retenue est affichée
  (`OK (methode : root sans mot de passe)`).
* La suppression d'une éventuelle connexion existante n'est faite que si elle
  existe vraiment (test local, sans réseau) : encore ~2 s gagnées.

Mesures sur un PC réel, port joignable mais partage absent (pire cas) :
**15,7 s → 7,4 s** ; adresse injoignable : **≈ 3 s** au lieu du blocage.

## [1.7.1]

### Ajouté

* **« Faire un diagnostic »** dans l'aide « Où trouver le jeton ? » : la page
  génère `diagnostic-recalbox.cmd`, un rapport lisible en six points — nom et
  adresse IP résolus, ports 445 (partage) et 8765 (agent) testés en TCP,
  connexion au partage avec les trois jeux d'identifiants, présence des
  `install.sh`, des deux userscripts et du `token.txt`, contenu de
  `system\rfid`, puis les codes d'erreur expliqués. Il ne modifie rien.
* Bouton **« Copier l'adresse du dossier »** : copie
  `\\<adresse>\share\system\rfid` (l'adresse du champ, donc l'IP si vous l'avez
  saisie) pour la coller dans la barre de l'Explorateur, sans risque de faute de
  frappe.

### Modifié

* L'aide du jeton explique désormais en premier qu'il suffit de **relancer le
  `.cmd`** (il copie le jeton dans le presse-papiers et rouvre la page déjà
  connectée), et rappelle explicitement que `\\RECALBOX` **tout seul** ne
  s'ouvre pas sous Windows : il faut `\\RECALBOX\share`.

### Corrigé

* Diagnostic : les chemins contenant des parenthèses
  (`recalbox-rfid-agent(permanent).py3`) cassaient l'analyse de la ligne `if`
  (erreur « .py3) était inattendu ») — corrigé.
* Diagnostic : le test de réponse utilisait `ping`, qui n'affiche pas l'adresse
  entre crochets quand on lui donne déjà une IP (faux négatif) ; il passe
  maintenant par la résolution DNS en PowerShell, insensible à la langue de
  Windows, et les tests de ports n'émettent plus d'avertissement parasite.

## [1.7.0]

### Modifié

* **Refonte complète de `installer.html`** pour un public qui ne connaît pas
  grand-chose à l'informatique :
  * une page unique, centrée, en trois étapes numérotées (« Installer »,
    « Relier », « Associer ») avec un seul bouton important par étape ;
  * un bandeau d'accroche (« Posez un badge, le jeu démarre. ») et trois
    promesses courtes à la place du jargon de tableau de bord ;
  * **tout le vocabulaire technique est reformulé** : « Bus SPI » devient
    « Bus du lecteur (SPI) », « PID » « Numéro de processus », « Dossier
    » « Emplacement », « Charger token.txt… » « J'ai le fichier token.txt »,
    les messages d'erreur et d'attente sont en français simple et disent quoi
    faire ;
  * les actions rares (ajout manuel, CSV, journaux, simulation de scan,
    mise à jour par ZIP ou URL) sont repliées dans des blocs « … » pour ne pas
    encombrer ;
  * une fois connecté, l'étape 1 se réduit à une seule ligne discrète et la page
    met en avant l'étape en cours.
* Nouveau style visuel : palette sombre chaude, accents corail et indigo,
  cartes à grand rayon, typographie système lisible, tuiles d'état colorées
  (vert / ambre / rouge), boutons de 44 px minimum, focus clavier visible,
  respect de `prefers-reduced-motion` et mise en page mobile sans débordement
  horizontal.
* Libellés de la documentation alignés sur les nouveaux boutons.

### Corrigé

* Le tableau des badges ne provoque plus de défilement horizontal quand il est
  vide (cellules qui reviennent à la ligne ; seuls les en-têtes restent sur une
  ligne).

## [1.6.3]

### Corrigé

* **Copie du script de démarrage : quatre méthodes en cascade**, au lieu d'une
  seule source. Le `.cmd` essaie (1) `robocopy` depuis
  `recalbox-rfid\bootstrap` du partage, (2) `copy` depuis ce même dossier,
  (3) `robocopy` depuis les fichiers temporaires, puis (4) une recherche du
  fichier `recalbox-rfid-agent*.py3` dans toute l'arborescence temporaire
  (`for /r`) — et vérifie la présence du fichier après chaque tentative. Chez
  certains utilisateurs l'extraction temporaire ne contenait pas `bootstrap\`,
  ce qui donnait un `robocopy` en code 0 (« rien à copier ») puis un échec
  alors que les fichiers étaient bien sur la carte.
* Le message d'échec indique désormais **quelle source est présente ou absente**
  (locale / partage) et rappelle la copie manuelle du userscript dans
  `userscripts\`.

## [1.6.2]

### Corrigé

* **La copie du script de démarrage ne peut plus échouer avec le code 1** :
  elle se fait maintenant avec `robocopy` (comme le programme), qui crée le
  dossier `userscripts` au besoin et renvoie des codes explicites ; la présence
  du fichier est vérifiée ensuite. L'ancien `copy /y` échouait silencieusement
  (« ECHEC : copie vers le partage impossible (code 1) ») alors que le programme
  venait d'être copié.
* Les codes `robocopy` sont affichés en cas d'échec (8 = fichiers non copiés,
  16 = erreur grave) avec les pistes correspondantes.

### Modifié

* L'essai « `root` sans mot de passe » passe en **2ᵉ** position : c'est la
  configuration réelle d'une Recalbox dont `system.default_password` est
  renseigné (le compte Samba `root` a alors un mot de passe vide). Les essais
  deviennent : 1 `root` / `recalboxroot`, 2 `root` sans mot de passe,
  3 `RECALBOX\root`, 4 adresse IP, 5 invité.
* Le message d'échec de connexion rappelle que le code **86** signifie
  « mot de passe réseau incorrect » côté Samba.

## [1.6.1]

### Corrigé

* **Le `.cmd` ne reste plus bloqué à « 1/4 Connexion au partage »** : les
  commandes `net use` sont désormais lancées avec l'entrée standard redirigée
  (`<nul`), si bien qu'une question de Windows (« des fichiers sont ouverts,
  continuer ? », demande de mot de passe) échoue au lieu d'attendre une réponse
  invisible pendant que la sortie était redirigée vers `nul`.
* La connexion essaie maintenant **cinq méthodes** et affiche chaque essai :
  `root`, `RECALBOX\root`, l'adresse IP résolue par ping, `root` **sans mot de
  passe** (cas où Recalbox n'a pas créé le mot de passe Samba), puis l'accès
  invité. Le ping préalable indique tout de suite si la Recalbox répond au nom
  donné.
* Après connexion, le partage est réutilisé via l'**adresse IP** si c'est elle
  qui a fonctionné (robuste aux noms NetBIOS/mDNS capricieux).
* Le `.cmd` n'ouvre plus la page avec un chemin de fichier suivi d'un fragment
  (`…\installer.html#host=…`, que Windows refuse d'ouvrir) mais avec une vraie
  URL `file:///…` (les espaces du chemin sont encodés en `%20`).
* `acces-recalbox.cmd` (diagnostic) affiche aussi le résultat du ping et n'attend
  plus de réponse invisible.

## [1.6.0]

### Ajouté

* **Installateur `.cmd` autonome, sans aucune boîte de dialogue** : le bouton
  « Télécharger l'installateur Windows (.cmd) » produit un fichier unique qui
  se connecte au partage (`net use`, avec repli invité), décompresse les fichiers
  (ZIP embarqué, `certutil` + `tar`/PowerShell), les copie dans
  `\\RECALBOX\share\recalbox-rfid\` et installe le script de démarrage dans
  `userscripts\`. Fini le sélecteur de dossier Windows, qui ne sait pas atteindre
  un partage UNC.
* **Installation automatique rétablie** : le script permanent installe/actualise
  au démarrage, active le SPI, redémarre Recalbox si nécessaire (jamais pendant
  un jeu) puis démarre le service et l'agent.
* **Mise à jour automatique** : copier un dossier de version plus récente sur le
  partage puis redémarrer suffit (comparaison de versions, pas de rétrogradation).
* Le `.cmd` relancé après redémarrage **ouvre la page avec le jeton déjà rempli**
  (fragment d'URL `#host=…&port=…&token=…`) et le copie dans le presse-papiers.
* La page accepte `#host=`, `#port=`, `#token=` et se connecte automatiquement.
* L'installateur embarque désormais `installer.html` (page « dossier » copiée sur
  la Recalbox).

### Modifié

* La copie par sélecteur de dossier (Edge/Chrome) passe en méthode alternative,
  repliée dans un menu.

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
