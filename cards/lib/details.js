// Détails secondaires, dessinés dans une boîte {x,y,w,h} (coordonnées absolues).
const { mix, lt, dk, luma, f } = require('./color');

let uid = 0;
const id = p => `${p}${++uid}`;

const A = {
  // fentes d'aération horizontales
  vents(o, b, T) {
    const n = Math.max(3, Math.floor(b.h / 10.5)), c = o.color || dk(T.body[1], .5), g = id('v');
    return `<defs><linearGradient id="${g}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${dk(c, .6)}"/><stop offset=".55" stop-color="${dk(c, .3)}"/><stop offset=".56" stop-color="${lt(T.body[1], .18)}"/><stop offset="1" stop-color="${T.body[1]}"/></linearGradient></defs>` +
      Array.from({ length: n }, (_, i) => `<rect x="${b.x + (o.skew ? i * 3 : 0)}" y="${f(b.y + 4 + i * 10.5)}" width="${b.w - (o.skew ? i * 3 : 0)}" height="6.5" rx="3.25" fill="url(#${g})"/>`).join('');
  },
  // rainures verticales
  ribs(o, b, T) {
    const c = o.color || dk(T.body[1], .3), n = Math.floor(b.w / 9);
    return Array.from({ length: n }, (_, i) => `<rect x="${b.x + i * 9}" y="${b.y + 4}" width="4" height="${b.h - 8}" rx="2" fill="${c}"/><rect x="${b.x + i * 9 + 4}" y="${b.y + 4}" width="1.2" height="${b.h - 8}" fill="${lt(T.body[1], .3)}" opacity=".5"/>`).join('');
  },
  // interrupteur + voyant (+ volume)
  power(o, b, T) {
    const c = o.panel || dk(T.body[1], .55), led = o.led || '#ff3b2a', g = id('l'), k = id('k');
    const knob = o.knob || '#3a3a40';
    const x = b.x, y = b.y + (b.h - 52) / 2, w = Math.min(b.w, o.volume === false ? 140 : 186);
    return `<defs><radialGradient id="${g}" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="${lt(led, .7)}"/><stop offset=".35" stop-color="${led}"/><stop offset="1" stop-color="${dk(led, .6)}"/></radialGradient>
      <linearGradient id="${k}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="${lt(knob, .25)}"/><stop offset=".5" stop-color="${knob}"/><stop offset="1" stop-color="${dk(knob, .4)}"/></linearGradient></defs>
      <rect x="${x}" y="${y}" width="${w}" height="52" rx="12" fill="${c}" stroke="${lt(c, .15)}" stroke-width="1.2"/>
      <rect x="${x + 14}" y="${y + 19}" width="70" height="14" rx="7" fill="#000" stroke="${dk(c, .5)}"/>
      <rect x="${x + 16}" y="${y + 12}" width="30" height="28" rx="5" fill="url(#${k})" stroke="#000" filter="url(#soft)"/>
      <path d="M${x + 23} ${y + 18} v16 M${x + 29} ${y + 18} v16 M${x + 35} ${y + 18} v16 M${x + 41} ${y + 18} v16" stroke="${lt(knob, .35)}" stroke-width="1.2"/>
      <circle cx="${x + 106}" cy="${y + 26}" r="16" fill="${led}" opacity=".22"/>
      <circle cx="${x + 106}" cy="${y + 26}" r="5.2" fill="url(#${g})" stroke="${dk(led, .7)}" stroke-width=".8"/>
      ${o.volume === false || w < 180 ? '' : `<rect x="${x + 128}" y="${y + 19}" width="46" height="14" rx="7" fill="#000"/><rect x="${x + 152}" y="${y + 15}" width="12" height="22" rx="3" fill="url(#${k})" stroke="#000"/>`}`;
  },
  // boutons ronds (power / reset) + voyant
  roundButtons(o, b, T) {
    const n = o.n || 2, c = o.color || lt(T.body[1], .1), r = Math.min(20, b.h / 2 - 6, (b.w - (o.led ? 30 : 6)) / n / 2 - 11), cy = b.y + b.h / 2, g = id('r');
    return `<defs><radialGradient id="${g}" cx=".4" cy=".35" r=".75"><stop offset="0" stop-color="${lt(c, .3)}"/><stop offset="1" stop-color="${dk(c, .2)}"/></radialGradient></defs>` +
      Array.from({ length: n }, (_, i) => `<circle cx="${b.x + r + 6 + i * (2 * r + 22)}" cy="${cy}" r="${r + 4}" fill="${dk(T.body[1], .25)}"/><circle cx="${b.x + r + 6 + i * (2 * r + 22)}" cy="${cy}" r="${r}" fill="url(#${g})" filter="url(#soft)"/>`).join('') +
      (o.led ? `<circle cx="${b.x + n * (2 * r + 22) + 14}" cy="${cy}" r="5" fill="${o.led}"/><circle cx="${b.x + n * (2 * r + 22) + 14}" cy="${cy}" r="12" fill="${o.led}" opacity=".25"/>` : '');
  },
  // deux boutons d'action inclinés (A / B) + start/select
  ab(o, b, T) {
    const C = o.colors || ['#a8205a', '#a8205a'], r = Math.min(19, b.h / 2 - 6), cy = b.y + b.h / 2, g = id('ab');
    const x1 = b.x + b.w - r * 3.6, x2 = b.x + b.w - r - 4;
    return `<defs>${C.map((c, i) => `<radialGradient id="${g}${i}" cx=".38" cy=".32" r=".75"><stop offset="0" stop-color="${lt(c, .4)}"/><stop offset=".55" stop-color="${c}"/><stop offset="1" stop-color="${dk(c, .45)}"/></radialGradient>`).join('')}</defs>` +
      (o.pills !== false ? `<rect x="${b.x + 4}" y="${cy - 4}" width="30" height="9" rx="4.5" fill="${o.pill || dk(T.body[1], .35)}" transform="rotate(-25 ${b.x + 19} ${cy})"/><rect x="${b.x + 42}" y="${cy - 4}" width="30" height="9" rx="4.5" fill="${o.pill || dk(T.body[1], .35)}" transform="rotate(-25 ${b.x + 57} ${cy})"/>` : '') +
      `<circle cx="${x1}" cy="${cy + 7}" r="${r}" fill="url(#${g}0)" filter="url(#soft)"/><circle cx="${x2}" cy="${cy - 7}" r="${r}" fill="url(#${g}1)" filter="url(#soft)"/>`;
  },
  // croix directionnelle
  dpad(o, b, T) {
    const s = Math.min(b.h - 8, 54), c = o.color || '#1d1d20', cx = b.x + (o.right ? b.w - s / 2 - 4 : s / 2 + 4), cy = b.y + b.h / 2, t = s / 3;
    return `<circle cx="${cx}" cy="${cy}" r="${s / 2 + 5}" fill="${dk(T.body[1], .2)}"/>
      <path d="M${cx - t / 2} ${cy - s / 2} h${t} v${t} h${t} v${t} h${-t} v${t} h${-t} v${-t} h${-t} v${-t} h${t} z" fill="${c}" stroke="${dk(c, .5)}" filter="url(#soft)"/>
      <circle cx="${cx}" cy="${cy}" r="${t * .3}" fill="${dk(c, .4)}"/>`;
  },
  // symboles PlayStation
  ps(o, b, T) {
    const r = Math.min(13, b.h / 4), cx = b.x + b.w - 3.2 * r, cy = b.y + b.h / 2, s = r * 2.1, c = o.color || '#2a2a2e';
    const sym = [`<path d="M0 -5 L4.6 3.2 H-4.6 Z" fill="none" stroke="#3fbf8a" stroke-width="1.8"/>`, `<circle r="4.4" fill="none" stroke="#f2516b" stroke-width="1.8"/>`,
      `<path d="M-3.8 -3.8 L3.8 3.8 M3.8 -3.8 L-3.8 3.8" stroke="#6f9cf2" stroke-width="1.8"/>`, `<rect x="-4" y="-4" width="8" height="8" fill="none" stroke="#e98ad8" stroke-width="1.8"/>`];
    return [[0, -s / 2], [s / 2, 0], [0, s / 2], [-s / 2, 0]].map(([x, y], i) =>
      `<circle cx="${cx + x}" cy="${cy + y}" r="${r * .62}" fill="${c}" stroke="#000" stroke-width=".6"/><g transform="translate(${cx + x} ${cy + y}) scale(${r / 13 * 1.15})">${sym[i]}</g>`).join('');
  },
  // bande de couleurs inclinée
  stripes(o, b, T) {
    const C = o.colors, sw = o.w || 12, total = C.length * sw;
    const x0 = b.x + (b.w - total) / 2 + 10;
    return `<g transform="translate(${x0} ${b.y + b.h / 2}) skewX(${o.skew ?? -28})">${C.map((c, i) => `<rect x="${i * sw}" y="${-b.h / 2 + 6}" width="${sw}" height="${b.h - 12}" fill="${c}"/>`).join('')}</g>`;
  },
  // bandes horizontales
  hstripes(o, b, T) {
    const C = o.colors, sh = Math.min(o.h || 6, (b.h - 10) / C.length);
    return C.map((c, i) => `<rect x="${b.x}" y="${f(b.y + (b.h - C.length * (sh + 3)) / 2 + i * (sh + 3))}" width="${b.w}" height="${f(sh)}" rx="${f(sh / 2)}" fill="${c}"/>`).join('');
  },
  // interrupteurs à levier métalliques
  switches(o, b, T) {
    const n = o.n || 4, sp = b.w / n, g = id('sw');
    return `<defs><linearGradient id="${g}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#8d8f96"/><stop offset=".5" stop-color="#eef0f4"/><stop offset="1" stop-color="#6b6d74"/></linearGradient></defs>` +
      Array.from({ length: n }, (_, i) => { const cx = b.x + sp * i + sp / 2, cy = b.y + b.h / 2; return `<rect x="${cx - 14}" y="${cy - 18}" width="28" height="36" rx="5" fill="#0c0c0d"/><rect x="${cx - 5}" y="${cy - (i % 2 ? 18 : 2)}" width="10" height="20" rx="3" fill="url(#${g})" filter="url(#soft)"/>`; }).join('');
  },
  // voyants
  leds(o, b, T) {
    const C = o.colors || ['#3f6'], cy = b.y + b.h / 2;
    return C.map((c, i) => `<circle cx="${b.x + 14 + i * 26}" cy="${cy}" r="12" fill="${c}" opacity=".22"/><circle cx="${b.x + 14 + i * 26}" cy="${cy}" r="5" fill="${c}"/><circle cx="${b.x + 12.5 + i * 26}" cy="${cy - 1.5}" r="1.6" fill="#fff" opacity=".7"/>`).join('');
  },
  // grille de haut-parleur
  grille(o, b, T) {
    const c = o.color || dk(T.body[1], .45), d = [];
    for (let y = b.y + 8; y < b.y + b.h - 4; y += 9) for (let x = b.x + 8; x < b.x + b.w - 4; x += 9) d.push(`<circle cx="${x}" cy="${y}" r="2.6" fill="${c}"/>`);
    return d.join('');
  },
  // texte de marquage
  text(o, b, T) {
    return `<text x="${b.x + (o.align === 'start' ? 4 : b.w / 2)}" y="${b.y + b.h / 2 + (o.size || 18) * .36}" text-anchor="${o.align === 'start' ? 'start' : 'middle'}" font-family="${o.font || "'Arial Black',sans-serif"}" font-style="${o.italic ? 'italic' : 'normal'}" font-weight="900" font-size="${o.size || 18}" letter-spacing="${o.ls ?? 2}" fill="${o.color}" filter="url(#soft)">${o.text}</text>`;
  },
  // sphère en damier
  boing(o, b, T) {
    const r = Math.min(b.h / 2 - 4, 26), cx = b.x + b.w - r - 8, cy = b.y + b.h / 2, g = id('bo'), cl = id('bc');
    const cells = [];
    for (let i = -4; i < 4; i++) for (let j = -4; j < 4; j++) if ((i + j) % 2 === 0) cells.push(`<rect x="${i * r / 4 * 1.0}" y="${j * r / 4}" width="${r / 4}" height="${r / 4}"/>`);
    return `<defs><clipPath id="${cl}"><circle r="${r}"/></clipPath><radialGradient id="${g}" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#fff" stop-opacity=".45"/><stop offset="1" stop-color="#000" stop-opacity=".35"/></radialGradient></defs>
      <ellipse cx="${cx + 6}" cy="${cy + r - 2}" rx="${r}" ry="5" fill="#000" opacity=".3"/>
      <g transform="translate(${cx} ${cy})"><circle r="${r}" fill="#fff"/><g clip-path="url(#${cl})" transform="rotate(-18)" fill="#d4141c">${cells.join('')}</g><circle r="${r}" fill="url(#${g})"/></g>`;
  },
  // bois
  wood(o, b, T) {
    return `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="8" fill="#000" filter="url(#woodF)"/><rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="8" fill="none" stroke="#000" stroke-opacity=".4"/>`;
  },
  // 4 petits boutons en losange
  buttons4(o, b, T) {
    const r = Math.min(10, b.h / 6), s = r * 2.3, cx = b.x + b.w - s - r - 6, cy = b.y + b.h / 2, c = o.color || '#e9e9ec';
    return [[0, -s], [s, 0], [0, s], [-s, 0]].map(([x, y]) => `<circle cx="${cx + x}" cy="${cy + y}" r="${r}" fill="${c}" stroke="${dk(c, .35)}" filter="url(#soft)"/>`).join('');
  },
  // fentes cartouches (ordinateurs)
  slot2(o, b, T) {
    const c = o.color || '#050506';
    return [0, 1].map(i => `<rect x="${b.x + 4}" y="${b.y + b.h / 2 - 14 + i * 18}" width="${b.w - 8}" height="10" rx="5" fill="${c}" stroke="${lt(T.body[1], .2)}" stroke-width="1"/>`).join('');
  },
  // lecteur de disquette 3.5"
  floppy(o, b, T) {
    const c = o.color || dk(T.body[1], .15);
    return `<rect x="${b.x}" y="${b.y + 6}" width="${b.w}" height="${b.h - 12}" rx="6" fill="${c}" stroke="${dk(c, .3)}"/>
      <rect x="${b.x + 14}" y="${b.y + b.h / 2 - 4}" width="${b.w * .62}" height="8" rx="4" fill="#0a0a0a"/>
      <rect x="${b.x + b.w - 40}" y="${b.y + b.h / 2 - 7}" width="26" height="14" rx="3" fill="${dk(c, .2)}" stroke="${dk(c, .4)}"/>
      <circle cx="${b.x + 22}" cy="${b.y + 16}" r="3.5" fill="#3f6"/>`;
  },
  // ports (manettes)
  ports(o, b, T) {
    const n = o.n || 2, c = o.color || dk(T.body[1], .6);
    return Array.from({ length: n }, (_, i) => { const x = b.x + 6 + i * 64; return `<rect x="${x}" y="${b.y + b.h / 2 - 14}" width="54" height="28" rx="7" fill="${c}"/><rect x="${x + 8}" y="${b.y + b.h / 2 - 6}" width="38" height="12" rx="3" fill="${dk(c, .6)}"/>`; }).join('');
  },
};

function renderAux(spec, box, T) {
  if (!spec) return '';
  const list = Array.isArray(spec) ? spec : [spec];
  const ws = list.map(s => s.flex || 1), tot = ws.reduce((a, b) => a + b, 0);
  let x = box.x;
  const gap = 10;
  return list.map((s, i) => {
    const w = (box.w - gap * (list.length - 1)) * ws[i] / tot;
    const b = { x, y: box.y, w, h: box.h };
    x += w + gap;
    return A[s.type] ? A[s.type](s, b, T) : '';
  }).join('');
}

module.exports = { renderAux };
