// Motifs principaux ("héros") : dessinés en coordonnées locales centrées sur (0,0),
// taille nominale : cercle de rayon 162 ou rectangle ≤ 320 × 300.
// Chaque fonction renvoie { svg, carve } ; carve = forme qui creuse la fenêtre jaquette.
const { mix, lt, dk, luma, f } = require('./color');

const radial = (id, c, { cx = .36, cy = .3, r = .8, a = .22, b = .45 } = {}) =>
  `<radialGradient id="${id}" cx="${cx}" cy="${cy}" r="${r}"><stop offset="0" stop-color="${lt(c, a)}"/><stop offset=".5" stop-color="${c}"/><stop offset="1" stop-color="${dk(c, b)}"/></radialGradient>`;
const vgrad = (id, a, b, c) =>
  `<linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${a}"/>${c ? `<stop offset=".5" stop-color="${b}"/><stop offset="1" stop-color="${c}"/>` : `<stop offset="1" stop-color="${b}"/>`}</linearGradient>`;
const gloss = `<linearGradient id="hGloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".28"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>`;

const MARK_FILLS = {
  gold: ['#fff6cf', '#e9c35c', '#9c6d12', '#f3d27a', '#b8861f'],
  chrome: ['#ffffff', '#c9ccd4', '#5d6068', '#e4e6eb', '#9a9da6'],
  red: ['#ff9a8a', '#e3302a', '#8f0d08', '#ff5a44', '#b3150f'],
  blue: ['#bfe3ff', '#3f8fe0', '#123f8a', '#6fb4ff', '#1f5bb8'],
};
// marquage (texte métallique ou couleur unie) en coordonnées locales
function mark(m, id = 'hMark') {
  if (!m) return '';
  const fill = MARK_FILLS[m.style];
  const defs = fill ? `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">${fill.map((c, i) => `<stop offset="${i / 4}" stop-color="${c}"/>`).join('')}</linearGradient></defs>` : '';
  const font = m.font || "'Arial Black','Segoe UI Black',sans-serif";
  return `${defs}<text x="${m.x || 0}" y="${m.y}" text-anchor="middle" font-family="${font}" font-style="${m.italic === false ? 'normal' : 'italic'}" font-weight="900" font-size="${m.size || 40}" letter-spacing="${m.ls ?? 1}" fill="${fill ? `url(#${id})` : m.style}"${fill ? ` stroke="${dk(fill[2], .5)}" stroke-width=".8"` : ''} filter="url(#soft)">${m.text}</text>`;
}
function arcText(a) {
  if (!a) return '';
  const r = a.r || 154, t = a.angle || .75;
  const d = `M${f(-r * Math.cos(t))} ${f(r * Math.sin(t))} A${r} ${r} 0 0 0 ${f(r * Math.cos(t))} ${f(r * Math.sin(t))}`;
  return `<defs><path id="hArc" d="${d}"/></defs><text font-family="'Segoe UI',Arial,sans-serif" font-weight="700" font-size="${a.size || 10.5}" letter-spacing="2.6" fill="${a.color}"><textPath href="#hArc" startOffset="50%" text-anchor="middle">${a.text}</textPath></text>`;
}

/* ------------------------------------------------------------------ */
// Dôme de fente cartouche (Mega Drive & co)
function dome(o, T) {
  const c = o.color || '#18181b', R = 162;
  const grooves = [0, 1, 2].map(i => `<circle r="${R - 26 - i * 7}" fill="none" stroke="#000" stroke-opacity=".55" stroke-width="1.3"/><circle cy="1.3" r="${R - 26 - i * 7}" fill="none" stroke="#fff" stroke-opacity=".06"/>`).join('');
  const sw = 196, sh = 54, sx = -sw / 2, sy = -sh / 2 + 8;
  return {
    carve: { type: 'circle', r: R },
    svg: `<defs>${radial('hDome', lt(c, .06), { a: .35, b: .7 })}${radial('hDomeTop', c, { cx: .4, cy: .28, r: .75, a: .2, b: .4 })}
      <linearGradient id="hRim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8d8d95"/><stop offset=".35" stop-color="${dk(c, .1)}"/><stop offset=".7" stop-color="${dk(c, .6)}"/><stop offset="1" stop-color="#45454b"/></linearGradient>
      ${vgrad('hSlotIn', '#000', '#16161a', '#000')}${vgrad('hFlap', lt(c, .1), dk(c, .4))}${gloss}</defs>
      <circle r="${R}" fill="url(#hDome)" filter="url(#drop)"/>
      <circle r="${R - 1.5}" fill="none" stroke="url(#hRim)" stroke-width="3"/>
      <circle r="${R - 16}" fill="url(#hDomeTop)"/>
      <circle r="${R - 16}" fill="none" stroke="#000" stroke-width="2.5"/>
      <circle r="${R - 17.5}" fill="none" stroke="#5b5b62" stroke-opacity=".5"/>
      ${grooves}
      <path d="M${-R + 22} -10 A${R - 20} ${R - 20} 0 0 1 40 ${-R + 24}" fill="none" stroke="url(#hGloss)" stroke-width="16" stroke-linecap="round" opacity=".7"/>
      <rect x="${sx - 10}" y="${sy - 10}" width="${sw + 20}" height="${sh + 20}" rx="14" fill="#060607" stroke="#2f2f34" stroke-width="1.5"/>
      <rect x="${sx}" y="${sy}" width="${sw}" height="${sh}" rx="6" fill="url(#hSlotIn)"/>
      <rect x="${sx + 4}" y="${sy + 4}" width="${sw - 8}" height="${sh / 2 - 5}" rx="3" fill="url(#hFlap)"/>
      <rect x="${sx + 4}" y="${sy + sh / 2 + 1}" width="${sw - 8}" height="${sh / 2 - 5}" rx="3" fill="url(#hFlap)" transform="rotate(180 0 ${sy + sh * .75 - 1})"/>
      <path d="M${sx + 6} ${sy + sh / 2} H${sx + sw - 6}" stroke="#000" stroke-width="2"/>
      ${o.accent ? `<circle r="${R - 8}" fill="none" stroke="${o.accent}" stroke-width="3" stroke-dasharray="${o.accentDash || 'none'}" opacity=".9"/>` : ''}
      ${mark(o.mark)}${arcText(o.arc)}`,
  };
}

/* ------------------------------------------------------------------ */
// Couvercle de lecteur CD (rond ou carré)
function disc(o, T) {
  const base = o.base || dk(T.body[1], .08), lid = o.lid || T.body[0], hub = o.hub || dk(lid, .15), R = 162;
  const square = o.square;
  const L = o.lidR || 138;
  const lidShape = square
    ? (attrs) => `<rect x="${-L}" y="${-L}" width="${2 * L}" height="${2 * L}" rx="${o.rx || 34}" ${attrs}/>`
    : (attrs) => `<circle r="${L}" ${attrs}/>`;
  const btns = (o.buttons || []).map((b, i) => `<circle cx="${b.x}" cy="${b.y}" r="${b.r || 12}" fill="url(#hBtn${i})" stroke="${dk(b.color, .5)}" stroke-width="1" filter="url(#soft)"/>`).join('');
  const btnDefs = (o.buttons || []).map((b, i) => radial(`hBtn${i}`, b.color, { a: .35, b: .4 })).join('');
  const rings = o.rings === false ? '' : [L - 22, L - 46].map(r => `<circle r="${r}" fill="none" stroke="${dk(lid, .14)}" stroke-width="1.2" opacity=".7"/><circle cy="1.2" r="${r}" fill="none" stroke="${lt(lid, .3)}" stroke-width=".8" opacity=".35"/>`).join('');
  return {
    carve: square ? { type: 'rect', w: 2 * R, h: 2 * R, rx: 46 } : { type: 'circle', r: R },
    svg: `<defs>${radial('hBase', base, { a: .12, b: .35 })}${radial('hLid', lid, { cx: .35, cy: .28, r: .85, a: .3, b: .22 })}${radial('hHub', hub, { a: .3, b: .4 })}${gloss}
      <radialGradient id="hGlow"><stop offset=".8" stop-color="${o.glow || '#fff'}" stop-opacity="0"/><stop offset=".93" stop-color="${o.glow || '#fff'}" stop-opacity=".8"/><stop offset="1" stop-color="${o.glow || '#fff'}" stop-opacity="0"/></radialGradient>${btnDefs}</defs>
      ${square ? `<rect x="${-R}" y="${-R}" width="${2 * R}" height="${2 * R}" rx="46" fill="url(#hBase)" filter="url(#drop)"/>` : `<circle r="${R}" fill="url(#hBase)" filter="url(#drop)"/>`}
      ${o.glow ? `<circle r="${L + 14}" fill="url(#hGlow)"/>` : ''}
      ${lidShape(`fill="${dk(lid, .45)}" transform="translate(0 3)"`)}
      ${lidShape(`fill="url(#hLid)"`)}
      ${lidShape(`fill="none" stroke="${dk(lid, .3)}" stroke-width="2"`)}
      ${rings}
      ${o.hub === false ? '' : `<circle r="34" fill="url(#hHub)" stroke="${dk(hub, .3)}"/><circle r="13" fill="${dk(hub, .45)}"/>`}
      ${o.dot ? `<circle r="7" fill="${o.dot}"/>` : ''}
      ${o.swirl ? `<path d="M-22 -8 C-18 -30 18 -30 20 -6 C22 14 -4 22 -10 8 C-14 -2 0 -8 6 -2" fill="none" stroke="${o.swirl}" stroke-width="6" stroke-linecap="round"/>` : ''}
      ${o.jewel ? `<circle r="30" fill="${o.jewel}" opacity=".95"/><circle r="30" fill="url(#hGloss)"/><path d="M-14 -14 L14 14 M14 -14 L-14 14" stroke="${dk(o.jewel, .5)}" stroke-width="7" stroke-linecap="round"/>` : ''}
      <path d="M${-L + 18} -12 A${L - 16} ${L - 16} 0 0 1 30 ${-L + 20}" fill="none" stroke="url(#hGloss)" stroke-width="14" stroke-linecap="round" opacity=".75"/>
      ${btns}${mark(o.mark)}${arcText(o.arc)}`,
  };
}

/* ------------------------------------------------------------------ */
// Boutons de manette sur un plateau circulaire
function buttons(o, T) {
  const plate = o.plate || T.body[1], R = 162, P = [];
  const D = [];
  const btn = (x, y, r, c, label, id, shape) => {
    D.push(radial(id, c, { cx: .38, cy: .32, r: .75, a: .35, b: .45 }));
    const sh = shape || `<circle cx="${x}" cy="${y}" r="${r}" fill="url(#${id})" filter="url(#soft)"/>`;
    return `${sh}<ellipse cx="${x - r * .25}" cy="${y - r * .38}" rx="${r * .4}" ry="${r * .22}" fill="#fff" opacity=".3"/>${label ? `<text x="${x}" y="${y + r + 15}" text-anchor="middle" font-family="'Segoe UI',Arial" font-weight="700" font-size="12" fill="${o.labelInk || lt(plate, .55)}">${label}</text>` : ''}`;
  };
  const well = (x1, y1, x2, y2, r) => {
    const len = Math.hypot(x2 - x1, y2 - y1), ang = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI, w = len + 2 * r, h = 2 * r;
    return `<rect x="${f(-w / 2)}" y="${-h / 2}" width="${f(w)}" height="${h}" rx="${r}" transform="translate(${f((x1 + x2) / 2)} ${f((y1 + y2) / 2)}) rotate(${f(ang)})" fill="${o.well || dk(plate, .12)}" stroke="${dk(plate, .25)}"/>`;
  };
  const C = o.colors || [];
  switch (o.layout) {
    case 'diamond': { // haut, droite, bas, gauche
      const s = 50, r = 30;
      P.push(well(-s, 0, 0, s, r + 9), well(0, -s, s, 0, r + 9));
      [[0, -s], [s, 0], [0, s], [-s, 0]].forEach(([x, y], i) => P.push(btn(x, y, r, C[i], o.labels?.[i], 'hB' + i)));
      break;
    }
    case 'nes': {
      P.push('<g transform="translate(-10 0) scale(.88)">');
      P.push(`<rect x="-138" y="-52" width="276" height="104" rx="10" fill="${o.well || '#1d1d1f'}" stroke="#000"/>`);
      P.push(`<rect x="-120" y="-14" width="34" height="12" rx="6" fill="#3b3b3e" transform="rotate(-0 0 0)"/><rect x="-74" y="-14" width="34" height="12" rx="6" fill="#3b3b3e"/>`);
      P.push(`<rect x="-6" y="-40" width="62" height="62" rx="6" fill="#d6d6d4"/><rect x="66" y="-40" width="62" height="62" rx="6" fill="#d6d6d4"/>`);
      P.push(btn(25, -9, 22, C[0] || '#c4161c', '', 'hB0'), btn(97, -9, 22, C[0] || '#c4161c', '', 'hB1'));
      P.push(`<text x="25" y="42" text-anchor="middle" font-family="Arial" font-weight="700" font-size="14" fill="#c4161c">B</text><text x="97" y="42" text-anchor="middle" font-family="Arial" font-weight="700" font-size="14" fill="#c4161c">A</text>`);
      P.push(`<path d="M-118 -30 h40 M-118 -34 h40" stroke="#c4161c" stroke-width="2"/>`, '</g>');
      break;
    }
    case 'n64': {
      const s = 30, r = 15;
      [[0, -s], [s, 0], [0, s], [-s, 0]].forEach(([x, y], i) => P.push(btn(x + 52, y - 46, r, C[2] || '#f2c518', '', 'hC' + i)));
      P.push(btn(-18, 34, 27, C[0] || '#2b56c8', 'A', 'hA'), btn(-70, -6, 24, C[1] || '#1f9a4a', 'B', 'hB'));
      P.push(`<circle cx="70" cy="70" r="34" fill="${dk(plate, .3)}"/><circle cx="70" cy="70" r="22" fill="url(#hStick)" filter="url(#soft)"/>`);
      D.push(radial('hStick', '#8a8a90', { a: .4, b: .5 }));
      break;
    }
    case 'gc': {
      P.push(btn(10, 6, 40, C[0] || '#1fb36a', 'A', 'hA'), btn(-56, 52, 21, C[1] || '#e2312e', 'B', 'hB'));
      D.push(vgrad('hK', lt(C[2] || '#cfcfd6', .2), dk(C[2] || '#cfcfd6', .25)));
      P.push(`<path d="M68 -40 C88 -10 86 28 70 50 C62 58 52 52 56 42 C66 22 66 -4 54 -28 C48 -40 62 -50 68 -40 Z" fill="url(#hK)" filter="url(#soft)"/>`);
      P.push(`<path d="M-42 -58 C-12 -76 26 -74 52 -60 C62 -54 56 -42 46 -46 C24 -56 -6 -58 -32 -44 C-44 -38 -54 -52 -42 -58 Z" fill="url(#hK)" filter="url(#soft)"/>`);
      break;
    }
    case 'arc4': { // A B C D en arc (arcade)
      [[-84, 22], [-30, -12], [28, -26], [86, -18]].forEach(([x, y], i) => P.push(btn(x, y + 10, 25, C[i], o.labels?.[i], 'hB' + i)));
      break;
    }
    case 'six': { // 2 rangées de 3 (X Y Z / A B C)
      const pos = [[-62, 34], [0, 18], [62, 6], [-50, -28], [6, -42], [62, -54]];
      pos.forEach(([x, y], i) => P.push(btn(x, y, i < 3 ? 24 : 17, C[i] || C[0], o.labels?.[i], 'hB' + i)));
      break;
    }
    case 'two': {
      P.push(btn(-38, 14, 30, C[0], o.labels?.[0], 'hB0'), btn(38, -10, 30, C[1] || C[0], o.labels?.[1], 'hB1'));
      break;
    }
    case 'three': {
      [[-66, 20], [0, 0], [66, -20]].forEach(([x, y], i) => P.push(btn(x, y, 26, C[i] || C[0], o.labels?.[i], 'hB' + i)));
      break;
    }
    case 'ps': {
      const s = 52, r = 27, sym = [
        `<path d="M0 -11 L10 7 H-10 Z" fill="none" stroke="#3fbf8a" stroke-width="3.2" stroke-linejoin="round"/>`,
        `<circle r="9.5" fill="none" stroke="#f2516b" stroke-width="3.2"/>`,
        `<path d="M-8 -8 L8 8 M8 -8 L-8 8" stroke="#6f9cf2" stroke-width="3.2" stroke-linecap="round"/>`,
        `<rect x="-8.5" y="-8.5" width="17" height="17" fill="none" stroke="#e98ad8" stroke-width="3.2"/>`];
      [[0, -s], [s, 0], [0, s], [-s, 0]].forEach(([x, y], i) => P.push(btn(x, y, r, C[0] || '#2a2a2e', '', 'hB' + i), `<g transform="translate(${x} ${y})">${sym[i]}</g>`));
      break;
    }
  }
  return {
    carve: { type: 'circle', r: R },
    svg: `<defs>${radial('hPlate', plate, { a: .14, b: .3 })}${D.join('')}</defs>
      <circle r="${R}" fill="url(#hPlate)" filter="url(#drop)"/>
      <circle r="${R - 2}" fill="none" stroke="${lt(plate, .25)}" stroke-opacity=".6" stroke-width="2"/>
      <circle r="${R - 14}" fill="none" stroke="${dk(plate, .25)}" stroke-opacity=".5" stroke-width="1.2"/>
      ${P.join('\n      ')}${mark(o.mark)}${arcText(o.arc)}`,
  };
}

/* ------------------------------------------------------------------ */
// Contenus d'écran
function pixelScene(x, y, w, h, pal, seed = 1) {
  // pal : [fond, clair, moyen, foncé]
  const px = Math.max(5, Math.round(w / 36)), cols = Math.floor(w / px), rows = Math.floor(h / px);
  const ox = x + (w - cols * px) / 2, oy = y + (h - rows * px) / 2;
  const R = (c, r, cw, ch, fill) => `<rect x="${f(ox + c * px)}" y="${f(oy + r * px)}" width="${cw * px}" height="${ch * px}" fill="${fill}"/>`;
  let s = `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${pal[0]}"/>`;
  // soleil + nuages
  s += R(cols - 7, 2, 3, 3, pal[1]) + R(cols - 8, 3, 5, 1, pal[1]) + R(cols - 7, 1, 3, 1, pal[1]);
  s += R(3, 3, 5, 1, pal[1]) + R(4, 2, 3, 1, pal[1]);
  // collines
  for (let c = 0; c < cols; c++) {
    const hh = Math.round(rows * .32 + Math.sin(c * .33 + seed) * rows * .1 + Math.sin(c * .9 + seed * 2) * rows * .03);
    s += R(c, rows - hh, 1, hh, pal[2]);
  }
  // sol en briques
  const g = Math.max(2, Math.round(rows * .16));
  s += R(0, rows - g, cols, g, pal[3]);
  for (let c = 0; c < cols; c += 2) s += R(c + ((c / 2) % 2), rows - g, 1, 1, pal[2]);
  // personnage + plateforme + bloc "?"
  const pc = Math.round(cols * .3);
  s += R(pc, rows - g - 3, 2, 3, pal[3]) + R(pc, rows - g - 4, 2, 1, pal[1]);
  s += R(Math.round(cols * .55), rows - g - 7, 6, 1, pal[3]) + R(Math.round(cols * .62), rows - g - 10, 2, 2, pal[1]);
  return s;
}
function screenContent(kind, x, y, w, h, o) {
  switch (kind) {
    case 'dmg': return pixelScene(x, y, w, h, o.pal || ['#9bbc0f', '#8bac0f', '#306230', '#0f380f']);
    case 'mono': return pixelScene(x, y, w, h, o.pal || ['#b8c4a8', '#98a488', '#4a5444', '#1c241a']);
    case 'color': return pixelScene(x, y, w, h, o.pal || ['#7ec8ff', '#fff3a8', '#3fae4b', '#8a4b1f'], 2);
    case 'oled': return pixelScene(x, y, w, h, ['#000', '#fff', '#555', '#fff'], 3);
    case 'vb': return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="#000"/>` +
      [0, 1, 2, 3, 4].map(i => `<path d="M${x + 10} ${f(y + h * .62 + i * 9)} L${x + w / 2} ${f(y + h * .3 + i * 4)} L${x + w - 10} ${f(y + h * .62 + i * 9)}" fill="none" stroke="#e01010" stroke-opacity="${1 - i * .17}" stroke-width="2"/>`).join('') +
      `<rect x="${x + w / 2 - 18}" y="${f(y + h * .38)}" width="36" height="24" fill="none" stroke="#ff2a2a" stroke-width="3"/>`;
    case 'lcd': return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="#c4c8b0"/>` +
      `<g fill="#3a3c34" opacity=".85"><circle cx="${x + w * .3}" cy="${y + h * .32}" r="9"/><rect x="${x + w * .3 - 8}" y="${y + h * .32 + 10}" width="16" height="24" rx="4"/>` +
      `<rect x="${x + 10}" y="${y + h * .78}" width="${w - 20}" height="5"/><rect x="${x + w * .55}" y="${y + h * .5}" width="${w * .3}" height="5"/>` +
      `<path d="M${x + w * .7} ${y + h * .2} l10 -10 l10 10 l-10 10 z"/></g><g fill="#3a3c34" opacity=".12"><circle cx="${x + w * .5}" cy="${y + h * .32}" r="9"/><circle cx="${x + w * .7}" cy="${y + h * .32}" r="9"/></g>`;
    case 'dual': {
      const g = 10, hh = (h - g) / 2;
      return pixelScene(x, y, w, hh, ['#7ec8ff', '#fff3a8', '#3fae4b', '#8a4b1f'], 2) + `<rect x="${x}" y="${y + hh}" width="${w}" height="${g}" fill="${o.bezel}"/>` + pixelScene(x, y + hh + g, w, hh, ['#ffd6a0', '#fff', '#e0663a', '#5a2a14'], 4);
    }
    case 'text': case 'prompt': {
      const ink = o.ink || '#33ff66', lines = o.lines || ['READY.', '>RUN', '_'];
      const fs = o.fontSize || Math.round(h / 8);
      return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${o.screen || '#071a0c'}"/>` +
        lines.map((l, i) => `<text x="${x + 12}" y="${y + 14 + fs * (i + 1) * 1.15}" font-family="Consolas,'Courier New',monospace" font-weight="700" font-size="${fs}" fill="${ink}">${l}</text>`).join('') +
        `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="url(#scan)" opacity=".5"/>`;
    }
    case 'vector': return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="#05060a"/>` +
      `<g fill="none" stroke="#e8f4ff" stroke-width="2.2" filter="url(#glowW)"><path d="M${x + w * .5} ${y + h * .2} L${x + w * .62} ${y + h * .5} L${x + w * .5} ${y + h * .42} L${x + w * .38} ${y + h * .5} Z"/>` +
      `<path d="M${x + w * .15} ${y + h * .75} L${x + w * .3} ${y + h * .62} L${x + w * .45} ${y + h * .8} L${x + w * .65} ${y + h * .6} L${x + w * .85} ${y + h * .78}"/><circle cx="${x + w * .2}" cy="${y + h * .25}" r="10"/><path d="M${x + w * .78} ${y + h * .2} l14 8 l-14 8 l-14 -8 z"/></g>`;
    case 'mac': return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="#f4f4f0"/><rect x="${x}" y="${y}" width="${w}" height="${h}" fill="url(#dither)" opacity=".5"/>` +
      `<rect x="${x}" y="${y}" width="${w}" height="12" fill="#fff"/><path d="M${x} ${y + 12} h${w}" stroke="#000"/>` +
      `<rect x="${x + w * .18}" y="${y + h * .26}" width="${w * .62}" height="${h * .52}" fill="#fff" stroke="#000" stroke-width="1.5"/>` +
      [0, 1, 2, 3, 4].map(i => `<path d="M${x + w * .18} ${y + h * .26 + 3 + i * 2.2} h${w * .62}" stroke="#000" stroke-width=".7"/>`).join('') +
      `<rect x="${x + w * .27}" y="${y + h * .45}" width="16" height="13" fill="none" stroke="#000"/><rect x="${x + w * .5}" y="${y + h * .45}" width="16" height="13" fill="none" stroke="#000"/>`;
    case 'scumm': return pixelScene(x, y, w, h * .72, ['#2a1f5c', '#f7d26a', '#5b3f9e', '#1a1030'], 5) +
      `<rect x="${x}" y="${y + h * .72}" width="${w}" height="${h * .28}" fill="#000"/>` +
      ['WALK TO', 'PICK UP', 'OPEN', 'LOOK AT', 'USE', 'TALK TO'].map((t, i) => `<text x="${x + 8 + (i % 3) * w / 3}" y="${y + h * .72 + 14 + Math.floor(i / 3) * 14}" font-family="Consolas,monospace" font-size="10" font-weight="700" fill="${i === 1 ? '#7ef' : '#3a8'}">${t}</text>`).join('');
  }
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="#222"/>`;
}

// Console portable / écran avec cadre
function screen(o, T) {
  const w = o.w || 300, h = o.h || 236, bz = o.bezel || '#55556a', body = o.body || T.body[1];
  const pad = o.pad || 34, sx = -w / 2 + pad, sy = -h / 2 + (o.top || 30), sw = w - 2 * pad, sh = h - (o.top || 30) - (o.bottom || 22);
  const label = o.label ? `<text x="0" y="${-h / 2 + 19}" text-anchor="middle" font-family="'Segoe UI',Arial" font-style="italic" font-weight="700" font-size="10" letter-spacing="1.5" fill="${o.labelInk || lt(bz, .55)}">${o.label}</text>` : '';
  const stripes = o.stripes ? o.stripes.map((c, i) => `<rect x="${-w / 2 + 14}" y="${-h / 2 + 8 + i * 5}" width="${w - 28}" height="2.2" fill="${c}"/>`).join('') : '';
  const led = o.led ? `<circle cx="${-w / 2 + 16}" cy="${f(sy + sh * .4)}" r="5" fill="url(#hLed)"/><circle cx="${-w / 2 + 16}" cy="${f(sy + sh * .4)}" r="13" fill="${o.led}" opacity=".18"/>` : '';
  return {
    carve: { type: 'rect', w: w + 24, h: h + 24, rx: (o.rx || 22) + 12 },
    svg: `<defs>${vgrad('hBody', lt(body, .12), body, dk(body, .2))}${vgrad('hBezel', lt(bz, .08), dk(bz, .18))}${radial('hLed', o.led || '#f00', { a: .5, b: .4 })}${gloss}</defs>
      <rect x="${-w / 2 - 12}" y="${-h / 2 - 12}" width="${w + 24}" height="${h + 24}" rx="${(o.rx || 22) + 12}" fill="url(#hBody)" filter="url(#drop)"/>
      <rect x="${-w / 2 - 11}" y="${-h / 2 - 11}" width="${w + 22}" height="${h + 22}" rx="${(o.rx || 22) + 11}" fill="none" stroke="${lt(body, .3)}" stroke-opacity=".6" stroke-width="1.5"/>
      <rect x="${-w / 2}" y="${-h / 2}" width="${w}" height="${h}" rx="${o.rx || 22}" fill="url(#hBezel)" stroke="${dk(bz, .45)}" stroke-width="1.5"/>
      ${o.cornerCut ? `<path d="M${w / 2 - 70} ${h / 2} L${w / 2} ${h / 2 - 70} V${h / 2 - 22} Q${w / 2} ${h / 2} ${w / 2 - 22} ${h / 2} Z" fill="url(#hBody)"/>` : ''}
      ${stripes}${label}
      <rect x="${sx - 3}" y="${sy - 3}" width="${sw + 6}" height="${sh + 6}" rx="4" fill="#000" opacity=".55"/>
      <g>${screenContent(o.content || 'dmg', sx, sy, sw, sh, { ...o, bezel: bz })}</g>
      <rect x="${sx}" y="${sy}" width="${sw}" height="${sh}" fill="url(#glass)"/>
      ${led}${mark(o.mark)}`,
  };
}

// Moniteur cathodique
function crt(o, T) {
  const w = o.w || 300, h = o.h || 250, c = o.case || T.body[0];
  const sx = -w / 2 + 30, sy = -h / 2 + 26, sw = w - 60, sh = h - 62;
  return {
    carve: { type: 'rect', w: w + 20, h: h + 20, rx: 34 },
    svg: `<defs>${vgrad('hCase', lt(c, .12), c, dk(c, .22))}${gloss}</defs>
      <rect x="${-w / 2 - 10}" y="${-h / 2 - 10}" width="${w + 20}" height="${h + 20}" rx="34" fill="url(#hCase)" filter="url(#drop)"/>
      <rect x="${-w / 2 + 14}" y="${-h / 2 + 12}" width="${w - 28}" height="${h - 34}" rx="24" fill="${dk(c, .45)}"/>
      <rect x="${sx}" y="${sy}" width="${sw}" height="${sh}" rx="18" fill="#000"/>
      <clipPath id="hScr"><rect x="${sx}" y="${sy}" width="${sw}" height="${sh}" rx="18"/></clipPath>
      <g clip-path="url(#hScr)">${screenContent(o.content || 'prompt', sx, sy, sw, sh, o)}<rect x="${sx}" y="${sy}" width="${sw}" height="${sh}" fill="url(#crtVignette)"/></g>
      <rect x="${sx}" y="${sy}" width="${sw}" height="${sh}" rx="18" fill="url(#glass)"/>
      <circle cx="${w / 2 - 30}" cy="${h / 2 - 10}" r="4" fill="${o.led || '#3f6'}"/>
      ${o.slot ? `<rect x="${-w / 2 + 40}" y="${h / 2 - 15}" width="70" height="5" rx="2.5" fill="${dk(c, .6)}"/>` : ''}
      ${o.stripes ? o.stripes.map((s, i) => `<rect x="${-w / 2 + 30 + i * 7}" y="${h / 2 - 18}" width="5" height="12" fill="${s}"/>`).join('') : ''}
      ${mark(o.mark)}`,
  };
}

// Clavier d'ordinateur
function keyboard(o, T) {
  const w = o.w || 290, h = o.h || 190, c = o.case || T.body[0], k = o.key || dk(c, .55);
  const rows = o.rows || 5, cols = o.cols || 13, pad = 16;
  const topH = o.fkeys ? 30 : 0;
  const kw = (w - 2 * pad) / cols, kh = (h - 2 * pad - topH - (o.space === false ? 0 : 0)) / (rows);
  const keys = [];
  const cap = (x, y, ww, hh, col, special) => {
    if (o.flat) return `<rect x="${f(x + 1.5)}" y="${f(y + 1.5)}" width="${f(ww - 3)}" height="${f(hh - 3)}" rx="2" fill="${col}" stroke="${dk(col, .35)}" stroke-width=".8"/>`;
    return `<rect x="${f(x + 1.5)}" y="${f(y + 2)}" width="${f(ww - 3)}" height="${f(hh - 3)}" rx="${o.round ? 8 : 4}" fill="${dk(col, .4)}"/>` +
      `<rect x="${f(x + 1.5)}" y="${f(y + .5)}" width="${f(ww - 3)}" height="${f(hh - 4.5)}" rx="${o.round ? 8 : 4}" fill="${col}"/>` +
      `<rect x="${f(x + 4)}" y="${f(y + 2.5)}" width="${f(ww - 8)}" height="${f(hh - 10)}" rx="${o.round ? 6 : 3}" fill="${lt(col, .1)}"/>`;
  };
  if (o.fkeys) {
    const n = o.fkeys.n || 8, fw = (w - 2 * pad) / n;
    for (let i = 0; i < n; i++) keys.push(cap(-w / 2 + pad + i * fw + (o.fkeys.diag ? 0 : 0), -h / 2 + pad - 2, fw, 26, o.fkeys.color));
  }
  const y0 = -h / 2 + pad + topH;
  for (let r = 0; r < rows; r++) {
    const off = r === rows - 1 ? 0 : (r % 2) * kw * .4;
    for (let cI = 0; cI < cols; cI++) {
      const x = -w / 2 + pad + off + cI * kw;
      if (x + kw > w / 2 - pad + .1) break;
      if (r === rows - 1 && o.space !== false) {
        if (cI === 3) { keys.push(cap(x, y0 + r * kh, kw * 7, kh, o.spaceKey || k)); cI += 6; continue; }
      }
      const special = o.special && o.special.find(s => s.at.some(([rr, cc]) => rr === r && cc === cI));
      keys.push(cap(x, y0 + r * kh, kw, kh, special ? special.color : (o.alt && (cI + r) % 5 === 0 ? o.alt : k)));
    }
  }
  const stripe = o.stripe ? `<g transform="translate(${w / 2 - 70} ${h / 2 - 8}) skewX(-30)">${o.stripe.map((s, i) => `<rect x="${i * 9}" y="-26" width="9" height="34" fill="${s}"/>`).join('')}</g>` : '';
  return {
    carve: { type: 'rect', w: w + 20, h: h + 20, rx: 22 },
    svg: `<defs>${vgrad('hCase', lt(c, .12), c, dk(c, .22))}</defs>
      <rect x="${-w / 2 - 10}" y="${-h / 2 - 10}" width="${w + 20}" height="${h + 20}" rx="22" fill="url(#hCase)" filter="url(#drop)"/>
      <rect x="${-w / 2 + 6}" y="${-h / 2 + 6}" width="${w - 12}" height="${h - 12}" rx="10" fill="${o.deck || dk(c, .3)}"/>
      ${keys.join('')}${stripe}${o.led ? `<circle cx="${w / 2 - 14}" cy="${-h / 2 - 1}" r="3.5" fill="${o.led}"/>` : ''}${mark(o.mark)}`,
  };
}

// Stick d'arcade
function arcade(o, T) {
  const plate = o.plate || T.body[1], R = 162, C = o.colors || ['#e23', '#fc2', '#2b4', '#26e'];
  const btn = (x, y, r, col, i) => `<circle cx="${x}" cy="${y + 4}" r="${r + 4}" fill="${dk(plate, .5)}"/><circle cx="${x}" cy="${y}" r="${r}" fill="url(#hBt${i})"/><ellipse cx="${x - r * .25}" cy="${y - r * .4}" rx="${r * .45}" ry="${r * .22}" fill="#fff" opacity=".35"/>`;
  const pos = o.six ? [[-20, -38], [26, -50], [72, -40], [-12, 14], [34, 2], [80, 12]] : [[-24, 8], [18, -20], [62, -26], [104, -8]];
  return {
    carve: { type: 'circle', r: R },
    svg: `<defs>${radial('hPlate', plate, { a: .14, b: .35 })}${radial('hBall', o.ball || '#d22', { cx: .35, cy: .3, r: .7, a: .55, b: .5 })}${C.map((c, i) => radial('hBt' + i, c, { a: .35, b: .35 })).join('')}${vgrad('hShaft', '#ddd', '#777')}</defs>
      <circle r="${R}" fill="url(#hPlate)" filter="url(#drop)"/>
      <circle r="${R - 2}" fill="none" stroke="${lt(plate, .25)}" stroke-opacity=".5" stroke-width="2"/>
      ${o.stripe ? `<path d="M${-R} 70 H${R}" stroke="${o.stripe}" stroke-width="8" opacity=".9"/>` : ''}
      <ellipse cx="-92" cy="34" rx="40" ry="16" fill="#000" opacity=".5"/>
      <circle cx="-92" cy="30" r="30" fill="${dk(plate, .45)}"/>
      <rect x="-96" y="-24" width="8" height="54" fill="url(#hShaft)"/>
      <circle cx="-92" cy="-34" r="32" fill="url(#hBall)" filter="url(#soft)"/>
      ${pos.slice(0, C.length).map(([x, y], i) => btn(x + 10, y, o.six ? 18 : 21, C[i], i)).join('')}
      ${mark(o.mark)}${arcText(o.arc)}`,
  };
}

// Fente cartouche vue de dessus, avec une cartouche insérée
function slot(o, T) {
  const w = o.w || 300, h = o.h || 210, c = o.case || T.body[1], cart = o.cart || '#2a2a2e';
  const n = o.double ? 2 : 1, cw = o.cartW || (o.double ? 110 : 190);
  const carts = [];
  for (let i = 0; i < n; i++) {
    const cx = n === 1 ? 0 : (i ? 65 : -65), x = cx - cw / 2, y = -h / 2 + 24;
    carts.push(`<rect x="${x - 10}" y="${y + 70}" width="${cw + 20}" height="24" rx="6" fill="#050506"/>
      <rect x="${x}" y="${y}" width="${cw}" height="84" rx="6" fill="url(#hCart)" filter="url(#soft)"/>
      ${[0, 1, 2, 3, 4, 5].map(j => `<rect x="${x + 10}" y="${y + 6 + j * 5}" width="${cw - 20}" height="2" fill="${dk(cart, .35)}"/>`).join('')}
      <rect x="${x + 14}" y="${y + 38}" width="${cw - 28}" height="40" rx="3" fill="url(#hLabel)"/>
      <rect x="${x + 20}" y="${y + 44}" width="${(cw - 40) * .6}" height="6" fill="#fff" opacity=".85"/><rect x="${x + 20}" y="${y + 56}" width="${(cw - 40) * .9}" height="16" fill="${dk(o.label || '#c33', .3)}" opacity=".6"/>`);
  }
  const ribs = o.ribs ? Array.from({ length: 9 }, (_, j) => `<rect x="${-w / 2 + 14}" y="${h / 2 - 82 + j * 8}" width="${w - 28}" height="3.5" rx="1.75" fill="${dk(c, .35)}"/><rect x="${-w / 2 + 14}" y="${h / 2 - 78.5 + j * 8}" width="${w - 28}" height="1" fill="${lt(c, .3)}" opacity=".5"/>`).join('') : '';
  return {
    carve: { type: 'rect', w: w + 20, h: h + 20, rx: 30 },
    svg: `<defs>${vgrad('hCase', lt(c, .14), c, dk(c, .2))}${vgrad('hCart', lt(cart, .15), dk(cart, .2))}${vgrad('hLabel', lt(o.label || '#c33', .2), dk(o.label || '#c33', .2))}</defs>
      <rect x="${-w / 2 - 10}" y="${-h / 2 - 10}" width="${w + 20}" height="${h + 20}" rx="30" fill="url(#hCase)" filter="url(#drop)"/>
      <rect x="${-w / 2 - 9}" y="${-h / 2 - 9}" width="${w + 18}" height="${h + 18}" rx="29" fill="none" stroke="${lt(c, .35)}" stroke-opacity=".5" stroke-width="1.5"/>
      ${o.band ? `<rect x="${-w / 2 - 10}" y="${h / 2 - 98}" width="${w + 20}" height="${o.bandH || 18}" fill="${o.band}"/>` : ''}
      ${ribs}${carts.join('')}${mark(o.mark)}`,
  };
}

// Lecteur de disquette (avec disquette à moitié insérée)
function disk(o, T) {
  const w = o.w || 300, h = o.h || 180, c = o.case || T.body[1], m = o.media || '#e8c21a';
  return {
    carve: { type: 'rect', w: w + 20, h: h + 20, rx: 26 },
    svg: `<defs>${vgrad('hCase', lt(c, .14), c, dk(c, .2))}${vgrad('hMedia', lt(m, .2), dk(m, .15))}</defs>
      <rect x="${-w / 2 - 10}" y="${-h / 2 - 10}" width="${w + 20}" height="${h + 20}" rx="26" fill="url(#hCase)" filter="url(#drop)"/>
      <rect x="${-w / 2 + 16}" y="${-h / 2 + 16}" width="${w - 32}" height="${h - 32}" rx="12" fill="${dk(c, .2)}"/>
      <rect x="${-w / 2 + 40}" y="-60" width="${w - 120}" height="100" rx="6" fill="url(#hMedia)" filter="url(#soft)"/>
      <rect x="${-w / 2 + 70}" y="-60" width="70" height="40" fill="${o.shutter || '#bfc3c9'}"/><rect x="${-w / 2 + 92}" y="-56" width="20" height="30" fill="${dk(o.shutter || '#bfc3c9', .4)}"/>
      <rect x="${-w / 2 + 60}" y="-6" width="${w - 160}" height="36" rx="3" fill="#fff" opacity=".85"/>
      <rect x="${-w / 2 + 30}" y="30" width="${w - 100}" height="16" rx="6" fill="#050506"/>
      <rect x="${w / 2 - 60}" y="18" width="34" height="22" rx="5" fill="${o.eject || dk(c, .35)}" stroke="${dk(c, .5)}"/>
      <circle cx="${w / 2 - 44}" cy="-30" r="5" fill="${o.led || '#f33'}"/><circle cx="${w / 2 - 44}" cy="-30" r="12" fill="${o.led || '#f33'}" opacity=".2"/>
      ${mark(o.mark)}`,
  };
}

// Manette à pavé numérique (Intellivision, ColecoVision, Jaguar)
function keypad(o, T) {
  const w = o.w || 230, h = o.h || 300, c = o.case || T.body[1], k = o.key || '#2a2a2e';
  const kw = 46, kh = 30, gx = 10, gy = 9, x0 = -(3 * kw + 2 * gx) / 2, y0 = -h / 2 + 34;
  const keys = [];
  for (let r = 0; r < 4; r++) for (let q = 0; q < 3; q++) {
    const x = x0 + q * (kw + gx), y = y0 + r * (kh + gy);
    keys.push(`<rect x="${x}" y="${y + 2}" width="${kw}" height="${kh}" rx="6" fill="${dk(k, .5)}"/><rect x="${x}" y="${y}" width="${kw}" height="${kh}" rx="6" fill="${k}"/><text x="${x + kw / 2}" y="${y + kh / 2 + 5}" text-anchor="middle" font-family="Arial" font-weight="700" font-size="13" fill="${o.keyInk || lt(k, .7)}">${'123456789*0#'[r * 3 + q]}</text>`);
  }
  const yd = y0 + 4 * (kh + gy) + 46;
  const ctrl = o.disc
    ? `<circle cy="${yd}" r="40" fill="${o.disc}" stroke="${dk(o.disc, .4)}" stroke-width="2"/><circle cy="${yd}" r="28" fill="none" stroke="${dk(o.disc, .25)}" stroke-dasharray="3 5" stroke-width="3"/>`
    : `<circle cy="${yd}" r="32" fill="${dk(c, .4)}"/><circle cy="${yd - 6}" r="22" fill="${o.stick || '#111'}" stroke="#000"/>`;
  return {
    carve: { type: 'rect', w: w + 20, h: h + 20, rx: 40 },
    svg: `<defs>${vgrad('hCase', lt(c, .14), c, dk(c, .22))}</defs>
      <rect x="${-w / 2 - 10}" y="${-h / 2 - 10}" width="${w + 20}" height="${h + 20}" rx="40" fill="url(#hCase)" filter="url(#drop)"/>
      <rect x="${x0 - 10}" y="${y0 - 10}" width="${3 * kw + 2 * gx + 20}" height="${4 * (kh + gy) + 12}" rx="10" fill="${o.overlay || dk(c, .25)}"/>
      ${keys.join('')}${ctrl}${(o.side || []).map((s, i) => `<rect x="${i ? w / 2 - 6 : -w / 2 - 4}" y="${-30}" width="10" height="60" rx="4" fill="${s}"/>`).join('')}${mark(o.mark)}`,
  };
}

module.exports = { dome, disc, buttons, screen, crt, keyboard, arcade, slot, disk, keypad };
