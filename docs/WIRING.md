# Câblage

![Branchement du lecteur RC522 et du bouton](wiring.svg)


## Le lecteur RC522 (nf-SL001)

Le module utilise le bus **SPI0** du Raspberry Pi et doit être alimenté en
**3,3 V**.

| RC522 | Raspberry Pi (nom) | GPIO (BCM) | Broche physique |
| --- | --- | --- | --- |
| SDA (SS) | CE0 | GPIO8 | 24 |
| SCK | SCLK | GPIO11 | 23 |
| MOSI | MOSI | GPIO10 | 19 |
| MISO | MISO | GPIO9 | 21 |
| RST | libre | GPIO25 | 22 |
| GND | GND | — | 6, 9, 14, 20, 25, 30, 34, 39 |
| 3.3V | 3V3 | — | 1 ou 17 |
| IRQ | non connecté | — | — |

Repère de la broche 1 : c'est la broche la plus proche du coin, côté « 3V3 »
(repérée par un carré sur beaucoup de cartes). Le connecteur GPIO 40 broches se
lit ainsi, vu de dessus, barrette vers le haut :

```
             3V3 (1)  (2) 5V
  bouton <-> GPIO2 (3)  (4) 5V
            GPIO3 (5)  (6) GND
            GPIO4 (7)  (8) GPIO14
              GND (9)  (10) GPIO15
   bouton -> GPIO17 (11) (12) GPIO18
           GPIO27 (13) (14) GND  <- bouton
           GPIO22 (15) (16) GPIO23
             3V3 (17) (18) GPIO24
           GPIO10 (19) (20) GND
           GPIO9  (21) (22) GPIO25 <- RST du RC522
           GPIO11 (23) (24) GPIO8  <- SDA du RC522   (CE0)
              GND (25) (26) GPIO7
                     ...
```

> Si votre lecteur est soudé sur un autre CS (CE1 = GPIO7, broche 26), il suffit
> de changer `spi_device = /dev/spidev0.1` dans `config.ini`.

## Le bouton poussoir

Le bouton se branche **entre GPIO17 (broche 11) et GND (broche 9)**.

* Aucune résistance : le programme active le **pull-up interne** du processeur
  (`PUD_UP`), la broche lit 1 au repos et 0 quand on appuie.
* Un bouton à 4 pattes se câble par paire : les deux pattes du même côté sont
  reliées entre elles. Vérifiez au multimètre en mode continuité.
* Un côté du bouton sur GPIO17, l'autre sur GND. Peu importe le sens.

Si vous préférez une autre broche, modifiez `pin = 17` dans la section
`[button]` de `config.ini`, puis `rfidctl restart`.

## Points à vérifier

1. **3,3 V**, jamais 5 V (le RC522 n'est pas tolérant au 5 V).
2. Les fils MISO/MOSI ne sont pas croisés : MISO→MISO, MOSI→MOSI.
3. Les masses (GND) sont bien communes entre le lecteur, le bouton et le Pi.
4. La nappe Dupont est bien enfoncée : un faux contact sur SCK donne exactement
   le symptôme « aucun badge détecté ».
5. Attention aux **manettes GPIO** de Recalbox : si `controllers.gpio.enabled=1`
   dans `recalbox.conf`, des broches sont réservées. Laissez cette option à `0`.

## Vérification

Une fois Recalbox redémarré (SPI activé) :

```sh
sh /recalbox/share/system/rfid/rfidctl test
```

Résultat attendu :

```
--- Lecteur RC522 (/dev/spidev0.0) ---
  Version du MFRC522 : 0x92
  Posez un badge sur le lecteur (attente 8 secondes)...
  Badge detecte : A1:B2:C3:D4
```

* `0x91`, `0x92`, `0x88`, `0x12`… : le lecteur répond, le SPI est bon.
* `0x00` ou `0xFF` : le SPI est actif mais le lecteur ne répond pas → câblage,
  alimentation, ou soudure du module.
* `/dev/spidev0.0` absent : le SPI n'est pas activé (voir `docs/TROUBLESHOOTING.md`).

Un badge 13,56 MHz (MIFARE Classic / Ultralight) est reconnu en 4 ou 7 octets.
Un badge de 125 kHz (contrôle d'accès ancien) ne fonctionnera **pas**.
