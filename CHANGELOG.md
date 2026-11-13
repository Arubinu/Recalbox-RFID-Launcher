# Historique des versions

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
versionnage sémantique. La version courante est aussi dans le fichier `VERSION`
et affichée par `rfidctl version`.

## [2.9.0]

### Ajouté — installation complète depuis la page, sans redémarrage (Recalbox 10)

* La page dépose aussi `userscripts/manual/Installer-lecteur-RFID.sh`. Recalbox 10
  liste ce dossier dans **START → réglages avancés → scripts utilisateur** et le
  relit à chaque ouverture du menu : on lance l'installation avec la manette,
  sans redémarrer. Le script démarre, détaché, le script permanent habituel
  (installation, service, agent) ; Recalbox ne redémarre qu'une fois, seule,
  pour activer le lecteur. Vérifié sur Recalbox 10.1.1.
* `install.sh` pose ce script (réparation sans SSH), `uninstall.sh` le retire.
* L'installateur `.cmd` le copie aussi et rouvre la page directement à l'étape
  « Lancer » (`#etape=3`).

### Modifié — nouvelle interface

* **Assistant d'installation en 4 étapes** (Brancher, Copier, Lancer,
  Autoriser) : la page attend la Recalbox toute seule, puis demande l'appui de
  3 s. Plus de choix techniques à faire.
* **Un seul écran « Autoriser cet ordinateur »** partout (installation,
  connexion, reconnexion après redémarrage), avec compte à rebours visuel.
* **Badges** : le jeu sélectionné sur la Recalbox en grand, un bouton
  « Associer un badge à ce jeu », le compte à rebours de pose, et un message
  clair à la fin (associé, ou délai dépassé). Liste lisible (nom du jeu, nom de
  la console, nombre de lancements), recherche dès 6 badges.
* **Matériel** : une liste de vérifications en langage courant, avec l'action
  à faire ; l'éventuel problème s'affiche aussi en haut du tableau de bord.
* **Mises à jour** : « Mettre à jour vers X » envoie le programme contenu dans
  la page elle-même ; plus besoin de fichier ZIP.
* Messages et confirmations intégrés à la page (plus de fenêtres `alert`).
* Toutes les chaînes affichées sont traduites (6 langues), mise en page
  mobile revue (en-tête, onglets).

### Corrigé

* `uninstall.sh --remove-spi` échouait sur `/boot` en lecture seule (et
  s'arrêtait avant de supprimer le programme) ; il ne retirait pas non plus la
  ligne ajoutée à `/boot/config.txt`. Il remonte maintenant `/boot` le temps
  de la modification et ne retire que les lignes ajoutées par l'installation.
* `uninstall.sh` n'arrêtait le service que si `rfidctl` était exécutable (jamais
  le cas sur le partage exFAT) et laissait l'agent tourner.
* Documentation : `rfidctl` s'appelle avec `sh` (le partage exFAT ne garde pas
  le droit d'exécution).

## [2.8.2]

### Corrigé

* **Le badge posé à la fin du réglage automatique ne lance plus le jeu.** La
  mesure interroge le lecteur lui-même : le badge resté en place n'avait donc
  jamais été « vu » par la boucle du service et, la mesure terminée, il passait
  pour un nouveau badge — d'où un jeu qui démarrait juste après la calibration.
  Le badge présent est maintenant **adopté sans agir** (il faut le retirer puis
  le reposer pour qu'il lance quelque chose).
* Même correction après le **test du lecteur** et après une **réinitialisation**
  des réglages, qui rouvrent aussi le lecteur.
* Un mode armé (association, effacement) reste prioritaire : le badge déjà posé
  peut toujours être présenté pour l'action demandée.

## [2.8.1]

### Corrigé

* **Le rond des interrupteurs de l'onglet Options est maintenant centre** dans
  sa piste. Il etait colle au bas du bouton (2 px en haut, 0 en bas) : il est
  desormais a 2 px des deux bords, allume comme eteint, sur ordinateur comme sur
  telephone.

## [2.8.0]

### Ajouté — « Régler le lecteur automatiquement »

Onglet **Matériel** : le service mesure le lecteur, puis règle trois valeurs
tout seul. Plus besoin de chercher un bon réglage à tâtons : c'est le matériel
qui donne les chiffres.

* `rfid.spi_speed_hz` — la vitesse de bus la plus rapide qui lit le registre de
  version **40 fois de suite sans une erreur** (8, 4, 2, 1 MHz, puis 500 kHz) ;
* `rfid.poll_interval_ms` — la cadence de lecture, calée sur la **durée réelle
  d'une lecture** (durée + 30 ms, bornée 60–500 ms) ;
* `rfid.rearm_absent_ms` — le délai d'absence, calé sur la **latence mesurée au
  retrait** (× 1,5, borné 1–4 s).

Séquence guidée (≈ 30 secondes) : *posez un badge* → *laissez-le* → *retirez-le*
→ *reposez-le*, avec barre de progression, numéro d'étape et bouton **Arrêter**.
La mesure tourne **dans le service** (seul propriétaire du bus SPI) : la page ne
fait qu'afficher, elle peut être fermée sans interrompre la mesure.

Rapport affiché en clair, sans jargon : vitesse du bus, intervalle de lecture,
délai d'absence, durée d'une lecture, **présence REQA / WUPA**, latence de
retrait, latence de repose et UID lu.

### Sécurité

* **Rien n'est écrit si une étape échoue** (aucun badge posé, badge illisible,
  retrait ou repose manquant, lecteur muet) : un message dit pourquoi et les
  réglages restent intacts.
* Les valeurs d'avant la mesure sont conservées dans `calibration-backup.json`,
  et le bouton **Réinitialiser** remet les trois valeurs d'origine (1 MHz,
  150 ms, 1,2 s).
* Si la vitesse mesurée ne tient pas à la réouverture du lecteur, le service
  **revient seul à 1 MHz** et le note dans le journal.
* L'agent refuse la mesure si le service n'est pas démarré ou s'il tourne encore
  dans une version plus ancienne que la page.

## [2.7.6]

### Corrigé — un badge posé n'est plus jamais pris pour un badge retiré

Deux symptômes, une seule cause : **la presence d'un badge etait testee par un
appel qui echouait a tous les coups**. Le service croyait donc le badge retire
une seconde apres chaque lecture, ce qui relancait le jeu tout seul et faisait
declarer « badge retire » juste apres un lancement (donc sans rien arreter).

* `tag_present()` est maintenant expose par le lecteur et fonctionne :
  * **REQA, puis WUPA.** Un badge qui vient d'etre selectionne ne repond plus a
    REQA : interroger REQA seul faisait passer un badge parfaitement pose pour
    retire. C'est la cause du jeu relance tout seul.
  * **cycle de champ en dernier recours** pour les clones bloques ;
  * **`None` quand le lecteur ne repond pas** : un bus muet ne prouve pas qu'un
    badge a ete retire, donc on ne conclut rien (avant, une erreur valait
    « absent »).
* Le service ne deduit plus l'absence d'une lecture ratee ou filtree par
  l'anti-rebond : seule une **absence confirmee par le lecteur** (REQA et WUPA
  sans reponse, trois constats, au moins 2 secondes d'affilee) libere le verrou.
* **3 secondes de grace** apres une action : un incident au demarrage de
  l'emulateur ne peut plus defaire le lancement.

### Corrigé — « quitter le jeu quand le badge est retire »

* L'arret du jeu attend que **l'emulateur tourne vraiment** (jusqu'a 6 s) : au
  moment du retrait, le jeu peut encore etre en train de demarrer. Plus de
  message trompeur « jeu arrete » alors que rien n'avait ete arrete.
* L'arret ne bloque jamais la lecture des badges ni le bouton : la demande est
  mémorisée et traitée par la boucle du service.
* `EmulationStation` n'est toujours jamais vise : seul l'emulateur recoit
  `SIGTERM`, puis `SIGKILL` s'il resiste.

## [2.7.5]

### Ajouté

* **Un onglet « Options »**, pour tout régler depuis la page, sans fichier à
  ouvrir : action au scan d'un badge associé, lancement pendant une partie,
  arrêt du jeu au retrait du badge, délai de pose du badge, appui qui autorise un
  navigateur, intervalle de lecture, anti-rebond du même badge, absence avant de
  pouvoir rescanner, vitesse du bus SPI, bips sonores et niveau de journal.
  * la page ne contient **aucune liste de réglages en dur** : c'est l'agent qui
    les décrit (`config.get`) et les enregistre (`config.set`) ; ajouter une
    option côté service la fait apparaître dans l'interface ;
  * l'enregistrement **conserve les commentaires** du `config.ini` et le service
    **relit sa configuration immédiatement** (SIGHUP) : ni redémarrage ni
    coupure de la lecture des badges ;
  * les modifications non enregistrées sont annoncées et **survivent au
    changement d'onglet** ; « Annuler » revient aux valeurs de la Recalbox ;
  * chaque valeur est **validée côté service** (bornes, choix, oui/non) : une
    valeur refusée n'écrit rien dans le fichier.

### Ajouté — lancer avec un badge, quitter en le retirant

* Nouvelle option `[launch] stop_on_remove` (désactivée par défaut) : quand le
  badge qui a lancé le jeu quitte le lecteur, le jeu est arrêté et Recalbox
  revient au menu. L'émulateur reçoit d'abord un arrêt propre (`SIGTERM`), puis
  un arrêt forcé s'il résiste (`SIGKILL`) ; **EmulationStation n'est jamais
  visé**, ce qui donne exactement le retour au menu d'une sortie de jeu normale.
* La détection des émulateurs se fait sur le **nom du programme** et non plus sur
  la ligne de commande entière : aucun processus système sans rapport ne peut
  être arrêté (le mot « service » contient « vice », par exemple).

### Corrigé

* **Le jeu ne se relance plus quand le badge reste sur le lecteur.** Un badge
  posé ne peut plus être pris pour un badge retiré : l'absence doit être vue
  **trois fois de suite** et durer plus longtemps que le délai de réarmement,
  toute lecture positive remettant le compteur à zéro.
* `hold_press_s` (durée d'appui qui autorise un navigateur) apparaît enfin dans
  le `config.ini` livré : il était réglable mais absent du fichier, donc
  invisible.

## [2.7.4]

### Ajouté

* **Reconnexion silencieuse au chargement.** Si une autorisation a déjà été
  donnée (secret de session mémorisé par le navigateur), la page **teste la
  connexion en arrière-plan** dès l'ouverture, sans attendre de clic :
  * succès (cas normal, y compris après une mise à jour ou un redémarrage du
    service, puisque le secret survit) → on arrive **directement sur le tableau
    de bord**, en ~0,2 s sur le réseau local ;
  * échec (Recalbox complètement redémarrée, autorisation perdue) → **rien ne
    s'affiche** : la page reste sur son écran, sans bandeau collant ; un message
    discret n'apparaît sous le formulaire que s'il est déjà à l'écran.
* La tentative est abandonnée au bout de 2,5 s et ne bloque jamais l'affichage :
  l'écran d'accueil est utilisable immédiatement.

## [2.7.3]

### Modifié

* **Sans choix explicite, c'est la langue du système qui décide.** La page lit la
  liste de préférences du navigateur (`navigator.languages`, qui suit la langue
  de l'OS) et retient la **première langue disponible** : un Windows en allemand
  ouvre la page en allemand, un Windows en français en français. Si aucune
  langue de la liste n'est disponible (OS en néerlandais, par exemple),
  l'anglais est utilisé ; en dernier recours, le français (langue source).
* La page suit aussi un **changement de langue du système** en direct
  (`languagechange`) tant qu'aucun choix n'a été fait.
* **Appui long sur le bouton de langue** : oublie le choix et revient à la
  langue du système (comme l'appui long du bouton de thème). Une infobulle
  rappelle les deux gestes.

## [2.7.2]

### Modifié

* **Plus de bip au lancement d'un jeu.** Le jeu se lance à l'écran, c'est la
  confirmation : le bip ne servait à rien et s'ajoutait au son du frontend. Les
  bips restent pour ce qui ne se voit pas — association d'un badge, badge
  inconnu, délai dépassé, effacement.

## [2.7.1]

### Ajouté

* **Les six langues de Recalbox que nous pouvons traduire proprement** :
  français, anglais, **allemand, espagnol, italien et portugais** — un fichier
  par langue (`i18n/de.json`, `es.json`, `it.json`, `pt.json`, 175 entrées
  chacun). Le bouton de l'en-tête fait défiler les six ; son infobulle donne le
  nom de la langue (`Deutsch`, `Español`…).
  * les libellés du tableau de bord construits par la page (« Jeu sélectionné »,
    « Version en service », « Bus du lecteur (SPI) »…) passent désormais par la
    table de traduction, ainsi que les messages les plus visibles (« Aucun badge
    pour l'instant », « ancien nombre de badges », « C'est prêt : posez le badge
    sur le lecteur (N s) », « Connexion perdue depuis N s »).
* Le basque, le turc et le chinois de Recalbox ne sont **pas** livrés : une
  traduction approximative serait pire que le français. Le mécanisme est prêt :
  déposer `i18n/eu.json` (ou `tr`, `zh`) suffit, la page le propose
  automatiquement.

### Note

* Les messages longs construits à la volée (détail des bandeaux d'erreur,
  verdicts du test du lecteur, textes du `.cmd` de diagnostic) restent en
  français pour l'instant : la fonction `t()` est en place, il ne manque que
  leurs traductions.

## [2.7.0]

### Ajouté

* **Interface multilingue.** Un bouton dans l'en-tête affiche la langue courante
  en deux lettres (`FR`, `EN`) et passe à la langue suivante d'un simple clic.
  La langue suit d'abord celle du navigateur, puis le choix est mémorisé.
  * chaque langue est un fichier `i18n/<code>.json` (fr, en, de, es, it, pt) — clé = texte français,
    valeur = traduction), compilé dans la page par `tools/build_installer.py`
    comme le reste du contenu — la page reste un fichier unique, sans réseau ;
  * un texte sans traduction reste en français : on peut donc ajouter une
    langue progressivement ;
  * la langue de référence est le français (`i18n/fr.json`, vide par
    construction) ; l'anglais est livré complet (`i18n/en.json`, 148 entrées,
    y compris le schéma de câblage) ;
  * les messages construits par la page (bandeaux, attentes, verdicts du test
    lecteur) passent par la même table ;
  * ajouter une langue = déposer `i18n/de.json` puis relancer
    `python tools/build_installer.py`.

### Modifié

* **Le fichier livré ne porte plus le numéro de version** :
  `dist/recalbox-rfid-installer.html` (au lieu de
  `dist/recalbox-rfid-installer-<version>.html`). La version reste affichée
  dans l'en-tête de la page et dans `VERSION`.
* Le bandeau d'écart de version renvoie au nouveau nom de fichier.

## [2.6.9]

### Corrigé

* **Associer un badge ne lance plus le jeu.** L'association déclenchait aussitôt
  le lancement (`[launch] launch_after_bind = 1`), ce qui surprend quand on
  vient seulement d'attribuer un jeu : on se retrouve dans le jeu sans l'avoir
  demandé. L'enregistrement ne fait plus que ça — deux bips et le badge est
  associé ; le jeu démarre au **scan suivant**.
* Le réglage `launch_after_bind` est supprimé : une valeur laissée à `1` par une
  version précédente dans `config.ini` est simplement ignorée (rien à éditer).
  Le fichier de configuration livré ne contient plus la ligne.

## [2.6.8]

### Modifié

* **L'appui de 3 secondes valide dès la 3ᵉ seconde**, sans avoir à relâcher le
  bouton. Avant, le geste n'était lu qu'au relâchement : il fallait tenir 3 s
  *puis* lâcher. Maintenant le geste part à l'instant où la durée est atteinte
  (bip de confirmation), et le relâchement qui suit ne déclenche rien d'autre.
* L'appui court reste lu au relâchement (pour ne jamais déclencher les deux
  gestes), et le journal note la durée : « Bouton maintenu 3.01 s : validation ».

## [2.6.7]

### Modifié

* **Deux gestes seulement, et l'action au relâchement.** Agir au contact était
  une erreur : un appui maintenu déclenchait à la fois l'appui court et l'appui
  long. Les gestes sont de nouveau lus **au relâchement** :
  * **appui court** → associer le jeu sélectionné (fenêtre de 10 s) ;
  * **appui de 3 secondes** → autoriser un navigateur.
* **Le geste « long » (2 s) qui armait l'effacement est supprimé** : réassocier
  un badge existant écrase l'ancienne correspondance, et l'effacement reste
  disponible dans l'interface (onglet Badges → « Effacer un badge »). Le réglage
  `[button] long_press_s` disparaît de `config.ini`.
* **L'interface suit l'événement en une seconde** (rafraîchissement de 2 s à 1 s)
  et affiche « C'est prêt : posez le badge sur le lecteur (N s) » pendant la
  fenêtre : on voit immédiatement que l'appui a été pris en compte.
* Les bips sont documentés (README, UTILISATION) : un bip aigu à l'armement,
  deux bips montants après l'association, deux graves si le badge est refusé,
  trois descendants si le délai expire. Le service journalise
  `Retour sonore actif (paplay)` au démarrage.

## [2.6.6]

### Corrigé

* **Un badge resté posé sur le lecteur devenait invisible.** Le pilote terminait
  chaque lecture par un `HALT` ; certains badges clones ne se réveillent pas
  après un `HALT` (ils ignorent `WUPA`) et restent muets tant qu'ils n'ont pas
  quitté le champ — d'où l'impression que le badge n'était plus vu. Le pilote
  **coupe puis rétablit le champ** (4 ms) : toutes les cartes repartent en état
  `IDLE`, et un cycle de champ automatique débloque même une carte restée
  coincée par une version précédente. La détection de présence (`tag_present`)
  n'utilise plus qu'un `REQA`, sans effet de bord.

### Modifié

* **L'appui sur le bouton agit immédiatement.** L'association est armée dès que
  le contact est confirmé (anti-rebond de 40 ms), sans attendre le relâchement :
  plus besoin de maintenir une seconde. Un appui maintenu bascule ensuite sur
  l'effacement (2 s) ou la confirmation d'appairage (3 s), qui restent au
  relâchement.
* **Armer un mode oublie le badge déjà posé** : après une suppression, on peut
  réassocier le même badge sans avoir à l'éloigner du lecteur.
* **Le jeu affiché est toujours montré dans l'interface.** Après avoir quitté
  une partie, le frontend conserve `State=playing` sur la fiche du jeu : la page
  affichait « aucun ». L'affichage tolère désormais cet état (le lancement par
  badge, lui, ne lance toujours rien pendant une partie).

## [2.6.5]

### Corrigé (le jeu ne se lançait pas : « Couldn't find game »)

* **Le lancement envoie maintenant le chemin complet du jeu**, et non plus son
  nom de fichier. Vérifié sur la machine : le frontend Recalbox 10 répond
  `[Command] Couldn't find game Flower (Europe).uae for system amiga600` au nom
  seul, et `[Command] Starting game /recalbox/share_init/roms/amiga600/Flower
  (Europe).uae for system amiga600` au chemin complet — celui-là même que le
  frontend publie dans `/tmp/es_state.inf`. La trame devient
  `START|<systeme>|<chemin complet>`.
  * les badges déjà associés fonctionnent : leur `path` a été enregistré au
    moment de l'association ;
  * une entrée ancienne sans chemin retombe sur le nom de fichier ;
  * l'ajout manuel et l'import CSV reconstruisent le chemin
    (`/recalbox/share/roms/...` puis `/recalbox/share_init/roms/...`).
* **Les jeux de la base en lecture seule ne déclenchent plus d'avertissement** :
  un chemin sous `/recalbox/share_init/roms/` est parfaitement normal (les jeux
  fournis avec Recalbox y sont), seul un chemin vraiment inattendu est signalé.
* Documentation alignée (README, UTILISATION, DEPANNAGE) sur le format de trame.

## [2.6.4]

### Corrigé (le jeu affiché n'était pas reconnu au moment d'associer)

* **Association possible quand le frontend affiche une fiche de jeu.** Le
  frontend laisse parfois `State=playing` alors qu'aucune partie n'est en
  cours ; le filtre « jeu en cours » s'appliquait aussi à l'association, d'où le
  message « Aucun jeu sélectionné » alors que le jeu était bien à l'écran. Le
  filtre ne s'applique plus qu'au **lancement par badge** (pas d'interruption de
  partie), plus à l'association.
* **Clés du frontend tolérées** : `SystemId` / `System` / `SystemName` et
  `GamePath` / `Path` / `File` / `RomPath`, et les dossiers sont aussi reconnus
  par `Type=folder` (toutes les versions de Recalbox n'écrivent pas `IsFolder`).
* **Le journal dit pourquoi** : « Aucun jeu sélectionné dans Recalbox
  (State='playing', SystemId='snes', GamePath='…') » — plus besoin de deviner.
* `status.json` contient désormais un instantané de `/tmp/es_state.inf`
  (valeurs tronquées) : l'état réel du frontend est lisible depuis le partage,
  sans rien lancer.

## [2.6.3]

### Ajouté (badges qui ne répondent jamais à la sélection)

* **Repli « anticollision stable »** : certains badges clones répondent au
  `REQA` et à l'anticollision mais restent muets à la sélection, quel que soit le
  BCC ou le CRC employé. Comme nous n'avons besoin **que de l'UID** (jamais de la
  mémoire du badge), le pilote accepte désormais la trame d'anticollision comme
  identifiant **après trois lectures identiques** : une lecture perturbée ne
  peut donc pas devenir un badge par accident, alors qu'un badge stable est
  reconnu en une fraction de seconde.
* Le test du lecteur annonce ce cas : « le badge est lu, mais il ne répond pas à
  la phase de sélection : badge non standard, il peut quand même être associé ».

## [2.6.2]

### Corrigé

* **La troisième stratégie de sélection était mal câblée** : `TxCRCEn` est le
  bit **7** (0x80) de `TxModeReg`, pas le bit 4. La trame était donc envoyée
  sans CRC (7 octets), ce qui ne pouvait pas aboutir. Corrigé, et le simulateur
  ajoute désormais lui-même le CRC quand ce bit est armé, pour que le test
  couvre réellement cette variante.
* Sans effet sur les deux premières stratégies (BCC reçu, BCC recalculé), qui
  restent celles que la carte a le plus de chances d'accepter.

## [2.6.1]

### Corrigé (badges qui répondent mais dont la sélection reste muette)

* La trace de 2.5.6 a montré que le **CRC était juste** (`crc_sw = crc_hw =
  6062`) : ma correction précédente ne visait pas la bonne cause. Les faits
  mesurés sont précis : `ATQA 0400`, anticollision reçue `36 00 00 00` avec un
  **BCC renvoyé à `00`** (au lieu de `36`), puis silence total sur la trame de
  sélection, quelle que soit la variante.
* Le pilote essaie désormais **plusieurs stratégies de sélection** au lieu d'une
  seule :
  1. BCC **renvoyé par la carte** (les clones comparent souvent celui-là) ;
  2. BCC **recalculé** à partir de l'UID (les vraies cartes recalculent) ;
  3. idem avec le **CRC ajouté par le coprocesseur** (`TxCRCEn`) au lieu d'être
     calculé en logiciel — certaines trames ne sont acceptées que sous cette
     forme.
  Chaque tentative est rejouée après un `REQA` puis un `WUPA`.
* La trace du test nomme chaque étape (`select-bcc-recu-reqa`,
  `select-bcc-recalcule-wupa`…) et indique la **stratégie gagnante** : si un
  badge finit par être lu, on saura exactement pourquoi.
* Simulateur : il vérifie désormais le BCC de la sélection comme une vraie carte
  (et sait simuler un clone qui exige son propre BCC erroné). Deux tests de plus.

## [2.6.0]

### Ajouté

* **Thème clair et thème sombre.** La page suit le thème du système
  (`prefers-color-scheme`) tant que l'on n'a rien choisi, et un bouton
  **soleil / lune** dans l'en-tête fige le choix (mémorisé dans le navigateur).
  La bascule est animée par un **cercle qui part du bouton** (API View
  Transitions, repli immédiat si elle n'existe pas ou si les animations sont
  réduites). **Appui long** sur le bouton : retour au thème du système.
* La palette claire est une vraie palette (fond chaud, encres foncées, mêmes
  accents) : les surfaces, bordures, textes teintés et la lueur de fond passent
  tous par des variables, aucune couleur n'est codée en dur dans les composants.

### Modifié

* **Le schéma de câblage suit le thème** : ses couleurs sont des variables CSS
  (`--c-…`), donc il est sombre sur page sombre et clair sur page claire. Le
  fichier `docs/cablage.svg` embarque sa propre feuille de style et suit
  `prefers-color-scheme`, y compris dans le README.
* La section **« Comment brancher le lecteur et le bouton »** est de nouveau
  **repliée au départ** et occupe **toute la largeur** de l'onglet Matériel.

## [2.5.6]

### Corrigé (cause réelle des badges illisibles)

* La trace de 2.5.5 a montré que l'**anticollision réussit** (`envoi 9320 →
  reçu 7700000000`) : le lecteur lit bien l'UID des badges, et le BCC était
  juste. C'est la **sélection** qui échouait, sans aucune réponse de la carte —
  signature d'un CRC_A invalide.
* **Le CRC_A de la trame de sélection est désormais calculé en logiciel**
  (`crc_a_software`, polynôme 0x8408, initialisation 0x6363, vérifié sur le
  vecteur de référence HALT `50 00 → 57 CD`) au lieu de dépendre du
  coprocesseur du MFRC522. La carte validait
  le CRC et ignorait silencieusement la trame.
* La trace indique maintenant `crc_sw` **et** `crc_hw` pour chaque sélection :
  si les deux diffèrent, c'est le coprocesseur qui est en cause.
* La trace enregistre aussi les trames **sans réponse** (avant, elles étaient
  perdues) : un échec de sélection est enfin visible.

### Modifié

* **Le schéma de câblage n'est plus replié** dans l'onglet Matériel : il est
  visible dès l'ouverture, sous le verdict matériel.
* **Bandeau d'avertissement quand la page et la Recalbox n'ont pas la même
  version** : « cette page est en 2.5.6 alors que la Recalbox est en 2.5.2 :
  ouvrez le fichier le plus récent ». C'est ce décalage qui faisait chercher un
  schéma absent d'un écran ancien.

## [2.5.5]

### Corrigé (badges lus par le lecteur mais sans UID)

* Diagnostic mesuré sur la machine : `Réponses : 36`, `ATQA : 0400`, `UID lu :
  aucun`. Le lecteur **voit** donc les badges (MIFARE Classic 4 octets), mais
  l'identification échouait dans le pilote. Trois corrections :
  * **BCC recalculé pour la sélection.** Le pilote recopiait le BCC renvoyé par
    la carte dans la trame de sélection ; certains badges clones le calculent
    faux, et la sélection était alors ignorée. Le BCC est maintenant recalculé
    (ou exclusif des octets transmis) et le BCC reçu n'est plus un critère de
    rejet.
  * **WUPA en secours de REQA** : un badge en veille qui répond à WUPA est
    désormais lu (deuxième tentative automatique).
  * **Une réponse non vide n'est plus jetée** à cause d'un drapeau d'erreur
    (parité, collision) : la trame est exploitée et c'est la sélection qui
    valide l'UID.
* **Le test du lecteur montre maintenant les trames échangées** (`envoi 9320 →
  reçu 88A1B2C34F (erreur 0x00)`) et les journalise : si un badge reste
  illisible, le rapport dit exactement à quelle étape.
* Trois nouveaux tests sur simulateur (BCC faux, badge endormi, trace).

## [2.5.4]

### Corrigé

* **Après « Installer / mettre à jour », le service continuait de tourner avec
  l'ancien code.** L'installation se fait avec `--no-restart` et seul l'agent se
  rechargeait : la Recalbox affichait donc « installé 2.5.2 » avec un service
  encore en 2.5.0, jusqu'au redémarrage suivant. Conséquence visible : le
  **test du lecteur échouait** (« le lecteur n'a pas répondu au test »), puisque
  c'est le service qui possède le bus SPI et qu'il ne connaissait pas la
  commande. Le service est maintenant relancé juste après l'installation, avec
  trois tests unitaires dédiés.

### Note

* Si votre Recalbox affiche deux versions différentes (onglet Maintenance), un
  clic sur « Installer / mettre à jour » suffit désormais à tout aligner, sans
  redémarrage de la machine.

## [2.5.3]

### Ajouté

* **Schéma de câblage, en image.** Une figure générée par
  `python tools/build_cablage.py` montre les neuf broches du connecteur à
  utiliser, les huit broches du module RC522 en face, et le bouton poussoir.
  Elle est visible :
  * dans l'onglet **Matériel** de `installer.html` (replié sous
    « Le branchement, en image »), sans aucune ressource externe ;
  * dans le `README.md` et `docs/CABLAGE.md` (`docs/cablage.svg`).

### Corrigé

* **Le numéro de version affiché était celui de la Recalbox, pas celui de la
  page.** L'en-tête affiche maintenant deux informations distinctes — « page
  2.5.3 » et « Recalbox 2.5.x » — et la seconde passe en rouge quand les deux
  diffèrent, avec l'explication en infobulle.
* **Le bandeau « connexion perdue » proposait « Réessayer maintenant », qui ne
  pouvait pas réussir** quand le secret de session était perdu (redémarrage
  complet). Il propose désormais **« Autoriser cet ordinateur »** : l'appui de
  3 secondes se fait depuis le tableau de bord, sans repasser par l'écran de
  connexion. Le bouton « Réessayer » reste pour les coupures réseau ordinaires.
* **« Le lecteur n'a pas répondu au test (service bloqué ?) » est remplacé par
  la vraie cause** : quand le service tourne encore une version plus ancienne
  que l'agent (il ne connaît pas la commande), le message le dit et renvoie vers
  « Installer / mettre à jour ».

## [2.5.2]

### Corrigé

* **Plus d'installation inutile.** « Installer / mettre à jour » lançait tout le
  script, recopiait les fichiers et redémarrait l'agent même quand la Recalbox
  était déjà à la version du dossier du partage — ce qui coûtait au passage un
  nouvel appui sur le bouton. L'agent compare maintenant les trois versions
  (disque, dossier du partage, service en cours) :
  * versions identiques → il répond « déjà à jour » et **ne touche à rien** ;
  * le service tourne encore une version plus ancienne → il réinstalle ;
  * bouton **« Réinstaller quand même »** pour forcer (cas d'un fichier abîmé).
* L'onglet Maintenance affiche désormais : version **sur la Recalbox**, version
  **en service**, version **à installer**, et l'état « déjà à jour ».

### Modifié

* **Un redémarrage du service ou une mise à jour ne redemande plus l'appui de
  3 secondes.** Le secret de session est conservé dans le dossier privé
  (`0600`, hors partage, remis à zéro avec `/tmp` au démarrage) : la page se
  reconnecte seule. Seul un **redémarrage complet de la Recalbox** renouvelle le
  secret et donc demande un nouvel appui — c'est aussi ce qui garantit qu'aucun
  secret ne survit à une coupure de courant.

## [2.5.1]

### Ajouté

* **« Tester avec un badge » dans l'onglet Matériel.** Un clic lance 5 secondes de
  lecture et donne une réponse claire, la seule qui manquait quand « il ne se
  passe rien » :
  * **le badge est lu** → son UID s'affiche, il peut être associé ;
  * **le badge répond mais la lecture échoue** → le code ATQA est affiché (badge
    exotique à signaler) ;
  * **aucune carte vue** → la page propose de recommencer avec une carte bancaire
    sans contact : si elle est vue, les badges ne sont pas en 13,56 MHz (les
    badges 125 kHz sont illisibles par ce lecteur) ; si elle n'est pas vue non
    plus, le problème est le lecteur (antenne ou câblage).
* Commande d'agent **`reader.test`** : le bus SPI appartient au service, l'agent
  lui dépose la demande et lit le résultat (`reader-test.json`). Le rapport
  contient le nombre d'essais, les réponses REQA/WUPA, les ATQA vus, les UID lus
  et les erreurs. Testé par six tests unitaires.

## [2.5.0]

### Sécurité

* **Suppression complète du jeton sur disque.** Plus aucun fichier du partage ne
  contient de secret : l'agent tire un **secret de session en mémoire**, neuf à
  chaque démarrage, et rien n'est écrit dans `system/rfid/`. Les fichiers
  `token.txt` et `paired.ok` laissés par une version précédente sont supprimés
  automatiquement au démarrage de l'agent.
* **Autorisation par appui physique de 3 secondes uniquement.** On ouvre
  `installer.html`, on clique sur « Se connecter », puis on garde le bouton du
  boîtier appuyé pendant le compte à rebours (30 s, une seule demande à la fois,
  refusée si le service du lecteur est arrêté). Ni mot de passe, ni jeton, ni
  copier-coller, ni fichier à chercher.
* **Suppression de la commande `pair` de l'agent et du fichier `pair-request`** :
  une demande déposée sur le partage ne donne plus aucun accès. `rfidctl pair`
  subsiste en SSH, mais ne fait que réouvrir la fenêtre de 30 s et n'affiche
  jamais de jeton.

### Modifié

* Le navigateur mémorise l'autorisation (localStorage) : une actualisation de la
  page reconnecte sans rien faire. En revanche, un redémarrage de la Recalbox, du
  service ou une mise à jour efface le secret de session : la page annonce qu'une
  nouvelle autorisation est demandée, affiche un bandeau « hors ligne » et
  réessaie automatiquement en attendant le nouvel appui de 3 s.
* L'agent n'écoute que le réseau local (port 8765) et refuse les origines web
  autres qu'une page locale ouverte en `file://`.

## [2.4.0]

### Modifié

* **Fenêtre d'association ramenée à 10 secondes** (`[button] arm_timeout_s`,
  au lieu de 30) : appui court, puis scan dans les 10 s. La réassociation d'un
  badge déjà connu reste le même geste : elle écrase l'ancienne correspondance.
* **Appui de 3 secondes** : il ne sert plus qu'à confirmer une demande
  d'appairage de l'interface (aucun autre effet sinon).
* **Bips enrichis** : un signal distinct pour un badge reconnu sans action
  (mode cartouche) et pour un effacement.

### Ajouté

* **Mode « cartouche »** : un badge laissé sur le lecteur ne déclenche l'action
  **qu'une seule fois**. Il faut l'éloigner `[rfid] rearm_absent_ms`
  (1,2 s par défaut) pour pouvoir le rescanner et refaire l'action ; un autre
  badge posé à la place agit immédiatement. Le service sonde la présence réelle
  du badge (`tag_present`) pour ne pas confondre anti-rebond et absence.
* **`[launch] action`** : `launch` (défaut, lance le jeu) ou `none` (bip de
  confirmation seulement, rien n'est lancé).

### Note

* Le frontend Recalbox n'accepte **qu'une seule commande réseau, `START`**
  (vérifié dans `CommandThread.cpp`) : il n'existe pas de commande officielle
  pour « ouvrir la fiche d'un jeu » sans le lancer. L'option `action` couvre
  donc les deux comportements réellement possibles.

## [2.3.1]

### Corrigé

* **Fini les messages de coupure fantômes.** Un bandeau « Connexion perdue »
  pouvait rester affiché après une simple actualisation de la page ou après une
  connexion réussie :
  * une **connexion réussie efface** désormais le bandeau d'état et le message
    d'erreur (`setConnected` nettoie les deux) ;
  * l'**auto-connexion au chargement** (jeton passé dans l'URL par le `.cmd`)
    n'affiche plus d'alerte collante quand elle échoue : elle se contente du
    message discret sous le formulaire, et l'utilisateur reste maître de cliquer ;
  * la déconnexion volontaire efface aussi les messages ;
  * une reconnexion automatique encore programmée est annulée dès qu'une
    connexion manuelle réussit (plus de double connexion).

## [2.3.0]

### Corrigé (Recalbox 10.1.1 sur Raspberry Pi 3, vérifié sur la machine)

* **Le bus SPI n'était jamais activé.** L'installateur écrivait
  `dtparam=spi=on` dans `/boot/recalbox-user-config.txt`, que Recalbox 10
  n'applique pas (l'`include` de ce fichier est sans effet). La ligne est
  désormais écrite **directement dans `/boot/config.txt`**, dans la section
  globale (juste après `dtparam=audio=on`), avec sauvegarde
  `.bak-rfid-launcher` et remontage temporaire de `/boot` en écriture.
  Résultat constaté après redémarrage : `/dev/spidev0.0` et `/dev/spidev0.1`
  apparaissent et le lecteur est détecté (`version 0x92`).
* **Le bouton poussoir n'était pas reconnu** (« export de la broche 17
  impossible : Invalid argument »). Le service démarre avec `PWD=/` (système en
  lecture seule) ; lgpio crée ses tubes de notification dans le répertoire
  courant, son import échouait donc et le programme retombait sur
  `/sys/class/gpio`, refusé par le noyau 6.12. Le backend GPIO change
  maintenant de répertoire de travail (et de `HOME` si nécessaire) vers un
  dossier inscriptible (`RFID_GPIO_DIR`, `/tmp`, `TMPDIR`, `/run`) le temps de
  l'initialisation. `RPi.GPIO` fonctionne alors et le pull-up interne est
  disponible.

### Ajouté

* Commande d'agent **`diag`** (authentifiée, lecture seule) : version de
  Recalbox, modèle, `/boot/config.txt`, `/dev/spidev*`, GPIO disponibles,
  `dmesg`, points de montage, script d'overlays. C'est ce diagnostic qui a
  permis d'identifier les deux causes ci-dessus **sans SSH**.

### Modifié

* L'installateur ne considère plus le SPI comme configuré sur la seule foi du
  fichier utilisateur : il vérifie aussi `config.txt`, et n'échoue jamais sur
  cette étape (avertissement + suite de l'installation).

## [2.2.0]

### Corrigé

* **« Installer / mettre à jour » ne mettait rien à jour** : l'agent lançait
  toujours le `install.sh` **déjà installé**, dont le dossier source est le
  dossier d'installation lui-même — d'où « Sources déjà en place, copie inutile »
  et une version qui ne bougeait jamais. Il choisit maintenant le dossier du
  projet **sur le partage** quand sa version est supérieure ou égale, et ne
  rétrograde jamais le programme.
* Le bus SPI n'était pas activé alors que l'installation affirmait le contraire :
  Recalbox 10 recharge `/boot` au démarrage (`S99overlaysync`), la ligne
  `dtparam=spi=on` écrite par l'installateur ne survit donc pas. Un diagnostic
  embarqué permet de vérifier le mécanisme (voir ci-dessous) et la documentation
  indique la marche à suivre propre à Recalbox 10.

### Ajouté

* Commande d'agent **`diag`** (authentifiée) : renvoie, en lecture seule, la
  version de Recalbox, le contenu utile de `/boot` (`config.txt`,
  `recalbox-user-config.txt`), la présence de `/dev/spidev*`, les points de
  montage et le début du script `S99overlaysync`. Objectif : diagnostiquer le
  matériel **sans SSH**.

## [2.1.0]

### Ajouté

* **Pertes et retours de connexion gérés**, en particulier lors d'un redémarrage
  de la Recalbox :
  * la page **reste sur le tableau de bord** (plus de retour brutal au
    formulaire) ; les actions sont grisées, un **bandeau d'état** apparaît :
    « Connexion perdue depuis N s · tentative n. La Recalbox a peut-être
    redémarré. » ;
  * la pastille d'en-tête passe à **« hors ligne »**, puis à **« connecté »** au
    retour ;
  * **reconnexion automatique** avec jeton mémorisé, temporisation croissante
    (1 s → 6 s), sans limite de durée : dès que l'agent revient, les commandes
    sont réactivées et l'état est rafraîchi ;
  * le retour est **annoncé** : bandeau vert « Connexion rétablie (coupure de
    N s) », effacé après 5 s ;
  * bouton **« Réessayer maintenant »** pour ne pas attendre la temporisation ;
  * la reconnexion est aussi tentée dès que l'onglet redevient visible.
* Cas particuliers traités : déconnexion **volontaire** (bouton) et fermeture
  d'onglet ne déclenchent aucune reconnexion ; un **jeton refusé** arrête les
  tentatives avec un message dédié (il faut ré-appairer).

## [2.0.2]

### Modifié

* Le bouton « Se connecter » occupe désormais **toute la largeur** de la carte :
  le vide à sa gauche disparaît, et l'écran suit le motif classique d'un
  formulaire à action unique. Léger relief (dégradé très discret) pour le
  distinguer des champs, sans revenir aux couleurs vives. Le rendu rejoint celui
  du mobile, où les boutons étaient déjà pleine largeur.

## [2.0.1]

### Modifié

* La ligne « Dernière connexion enregistrée » a disparu de l'écran de connexion :
  quand une connexion est déjà mémorisée, la carte va directement des champs au
  bouton « Se connecter ».
* Les messages d'état n'occupent plus de place quand ils sont vides
  (`.hint:empty`), ce qui supprime les blancs inutiles dans la carte.

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
