#!/bin/sh
# =============================================================================
#  Recalbox RFID Launcher - installation depuis le menu de Recalbox (10 et +)
#
#  Recalbox 10 liste les scripts de /recalbox/share/userscripts/manual dans
#  START > REGLAGES AVANCES > SCRIPTS UTILISATEUR, et relit ce dossier a chaque
#  ouverture du menu : la page installer.html y depose ce fichier, l'utilisateur
#  le lance avec la manette, et l'installation demarre SANS redemarrage.
#
#  Le script ne fait que lancer, detache, le script permanent habituel
#  (installation + service + agent). Il peut etre relance sans risque : un
#  second agent ne peut pas ouvrir le port deja pris, et l'installation ne
#  refait rien si la version est deja la bonne. Si le lecteur vient d'etre
#  active, Recalbox redemarre une fois toute seule : c'est normal.
# =============================================================================

SHARE="/recalbox/share"
NAME="recalbox-rfid-agent(permanent).py3"
BOOT="$SHARE/userscripts/$NAME"
[ -f "$BOOT" ] || BOOT="$SHARE/recalbox-rfid/bootstrap/$NAME"

if [ ! -f "$BOOT" ]; then
    echo "Fichiers RFID introuvables sur la Recalbox."
    echo "Recommencez la copie depuis la page de votre ordinateur."
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)

# Detache du menu : le script rend la main tout de suite, l'agent continue.
if command -v setsid >/dev/null 2>&1; then
    setsid "$PYTHON" "$BOOT" </dev/null >/dev/null 2>&1 &
else
    nohup "$PYTHON" "$BOOT" </dev/null >/dev/null 2>&1 &
fi

echo "Installation du lecteur RFID lancee."
echo "Revenez sur la page de votre ordinateur : elle continue toute seule."
exit 0
