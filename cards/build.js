#!/usr/bin/env node
// Générateur des gabarits de cartes (format ID-1 / carte bancaire, 85.60 × 53.98 mm).
// Unité : 1 = 0.1 mm  →  856 × 540 (horizontal) ou 540 × 856 (vertical), coins r = 31.8 (3.18 mm).
//
// Trois variantes par plateforme :
//   <id>-h-right.svg : [ jaquette ][ console ][ languette ]   fente sur le côté, languette à droite
//   <id>-h-left.svg  : [ languette ][ console ][ jaquette ]   fente sur le côté, languette à gauche
//   <id>-v.svg       : jaquette, console, puis languette en bas   fente en façade
// La languette est la partie qui DÉPASSE du lecteur : nom du jeu, joueurs, mini-logo.
// La jaquette est une fenêtre TRANSPARENTE : on pose l'image dessous, la carte par-dessus.
// <id>-zones.json décrit les zones de chaque variante (une zone avec "rotate" s'écrit tournée)
// ainsi que les couleurs de texte conseillées.
//
// Les motifs sont dans lib/heroes.js (motif principal) et lib/details.js (détails),
// les réglages de chaque plateforme dans themes.js.
//
// Usage : node build.js [id ...]
// Le dessin lui-même est dans lib/card.js ; après une modification, relancer aussi
// node bundle.js (embarque le générateur dans l'éditeur de cartes, installer.html).


const fs = require('fs');
const path = require('path');
const { card, VARIANTS, R } = require('./lib/card');
const THEMES = require('./themes');

/* ------------------------------------------------------------------ */
const only = process.argv.slice(2);
const out = __dirname;
const all = {};
for (const [id, T] of Object.entries(THEMES)) {
  if (only.length && !only.includes(id)) continue;
  const dir = path.join(out, id);
  fs.mkdirSync(dir, { recursive: true });
  const variants = {};
  for (const [suffix, side] of Object.entries(VARIANTS)) {
    const { svg, zones } = card(T, side);
    fs.writeFileSync(path.join(dir, `${id}-${suffix}.svg`), svg);
    variants[suffix] = zones;
  }
  fs.writeFileSync(path.join(dir, `${id}-zones.json`), JSON.stringify({ unit: '0.1mm', radius: R, name: T.name, short: T.short, variants }, null, 2));
  all[id] = { name: T.name, short: T.short, variants };
}
// pour preview.html / gallery.html (lisibles en file://, sans serveur)
if (!only.length) fs.writeFileSync(path.join(out, 'zones.js'), 'window.ZONES = ' + JSON.stringify(all) + ';\n');
console.log(Object.keys(all).length, 'plateformes générées');
