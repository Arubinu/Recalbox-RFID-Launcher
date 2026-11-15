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
    // une rangée de boutons (manette Vectrex : 4 boutons alignés), centrée
    if (o.row) {
      const n = o.row, rr = Math.min(r, (b.w - 8) / n / 2 - 4), sp = (b.w - 8) / n;
      return `<defs>${C.map((c, i) => `<radialGradient id="${g}${i}" cx=".38" cy=".32" r=".75"><stop offset="0" stop-color="${lt(c, .4)}"/><stop offset=".55" stop-color="${c}"/><stop offset="1" stop-color="${dk(c, .45)}"/></radialGradient>`).join('')}</defs>` +
        Array.from({ length: n }, (_, i) => `<circle cx="${f(b.x + 4 + sp * (i + .5))}" cy="${f(cy)}" r="${f(rr + 3)}" fill="${dk(T.body[1], .25)}"/><circle cx="${f(b.x + 4 + sp * (i + .5))}" cy="${f(cy)}" r="${f(rr)}" fill="url(#${g}${i % C.length})" filter="url(#soft)"/>`).join('');
    }
    // sans les boutons start/select à gauche, la paire est centrée dans sa zone
    const shift = o.pills === false ? -(b.w - r * 4.6 - 4) / 2 : 0;
    const x1 = b.x + b.w - r * 3.6 + shift, x2 = b.x + b.w - r - 4 + shift;
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
    const c = o.color || '#050506', n = o.n || 2;
    return Array.from({ length: n }, (_, i) => `<rect x="${b.x + 4}" y="${f(b.y + b.h / 2 - (n * 18 - 8) / 2 + i * 18)}" width="${b.w - 8}" height="10" rx="5" fill="${c}" stroke="${lt(T.body[1], .2)}" stroke-width="1"/>`).join('');
  },
  // lecteur de cassettes intégré (ordinateurs 8 bits) : fenêtre et deux bobines
  cassette(o, b, T) {
    const w = Math.min(b.w, 124), h = Math.min(b.h - 6, 46), x = b.x + (b.w - w) / 2, y = b.y + (b.h - h) / 2;
    const c = o.color || dk(T.body[1], .55), wx = x + w * .14, ww = w * .72, wy = y + h * .3, wh = h * .5, r = wh * .36;
    const reel = (cx) => `<circle cx="${f(cx)}" cy="${f(wy + wh / 2)}" r="${f(r)}" fill="#e9e6df"/><circle cx="${f(cx)}" cy="${f(wy + wh / 2)}" r="${f(r * .42)}" fill="#1a1a1c"/>` +
      [0, 120, 240].map(a => `<rect x="${f(cx - .9)}" y="${f(wy + wh / 2 - r * .95)}" width="1.8" height="${f(r * .5)}" fill="#1a1a1c" transform="rotate(${a} ${f(cx)} ${f(wy + wh / 2)})"/>`).join('');
    return `<rect x="${f(x)}" y="${f(y)}" width="${f(w)}" height="${f(h)}" rx="6" fill="${c}" stroke="${lt(c, .18)}" stroke-width="1.2"/>
      <rect x="${f(x + 8)}" y="${f(y + 4)}" width="${f(w - 16)}" height="${f(h * .14)}" rx="2" fill="${o.label || lt(c, .25)}"/>
      <rect x="${f(wx)}" y="${f(wy)}" width="${f(ww)}" height="${f(wh)}" rx="4" fill="#0b0b0c" stroke="${dk(c, .5)}"/>
      <rect x="${f(wx + ww * .2)}" y="${f(wy + wh / 2 - r * .7)}" width="${f(ww * .6)}" height="${f(r * 1.4)}" fill="#4a2c1a"/>
      ${reel(wx + ww * .24)}${reel(wx + ww * .76)}
      <rect x="${f(wx)}" y="${f(wy)}" width="${f(ww)}" height="${f(wh / 2)}" rx="4" fill="#fff" opacity=".08"/>`;
  },
  // prises joystick DB9 (Atari, Amiga, Commodore, MSX…)
  joyports(o, b, T) {
    const n = o.n || 2, c = o.color || dk(T.body[1], .62), pw = Math.min(42, (b.w - (n - 1) * 10) / n), ph = Math.min(24, b.h - 16);
    const x0 = b.x + (b.w - (n * pw + (n - 1) * 10)) / 2, y = b.y + (b.h - ph) / 2, s = pw * .14;
    return Array.from({ length: n }, (_, i) => {
      const x = x0 + i * (pw + 10);
      const pins = [...Array.from({ length: 5 }, (_, k) => [x + pw * .18 + k * pw * .16, y + ph * .36]), ...Array.from({ length: 4 }, (_, k) => [x + pw * .26 + k * pw * .16, y + ph * .68])];
      return `<path d="M${f(x)} ${f(y)} h${f(pw)} l${f(-s)} ${f(ph)} h${f(-(pw - 2 * s))} z" fill="${dk(c, .35)}" stroke="${lt(c, .3)}" stroke-width="1.6" stroke-linejoin="round"/>` +
        pins.map(([px, py]) => `<circle cx="${f(px)}" cy="${f(py)}" r="${f(Math.max(1.2, pw * .04))}" fill="#c9a24a"/>`).join('');
    }).join('');
  },
  // rangée de touches de fonction (couleur propre, inclinées façon Atari ST avec skew)
  fkeys(o, b, T) {
    const n = o.n || 5, C = o.colors || [o.color || dk(T.body[1], .3)], gap = 5;
    const kw = (b.w - 8 - (n - 1) * gap) / n, kh = Math.min(26, b.h - 18), y = b.y + (b.h - kh) / 2;
    return Array.from({ length: n }, (_, i) => {
      const x = b.x + 4 + i * (kw + gap), c = C[i % C.length], cx = x + kw / 2;
      return `<g transform="${o.skew ? `translate(${f(cx)} ${f(y + kh / 2)}) skewX(${o.skew}) translate(${f(-cx)} ${f(-(y + kh / 2))})` : ''}">
        <rect x="${f(x)}" y="${f(y + 2)}" width="${f(kw)}" height="${f(kh)}" rx="3" fill="${dk(c, .45)}"/>
        <rect x="${f(x)}" y="${f(y)}" width="${f(kw)}" height="${f(kh - 2)}" rx="3" fill="${c}"/>
        <rect x="${f(x + 2.5)}" y="${f(y + 2)}" width="${f(kw - 5)}" height="${f(kh * .45)}" rx="2" fill="${lt(c, .22)}"/></g>`;
    }).join('');
  },
  // tiroir de lecteur CD en façade + bouton d'éjection
  cdtray(o, b, T) {
    const c = o.color || dk(T.body[1], .2), h = Math.min(32, b.h - 12), y = b.y + (b.h - h) / 2, w = b.w - 4;
    const ex = b.x + w - 26, glow = o.glow;
    return `<rect x="${b.x}" y="${f(y)}" width="${f(w)}" height="${f(h)}" rx="5" fill="${c}" stroke="${dk(c, .45)}" stroke-width="1.2"/>
      <rect x="${b.x + 2}" y="${f(y + 2)}" width="${f(w - 4)}" height="${f(h * .3)}" rx="3" fill="#fff" opacity=".07"/>
      <rect x="${b.x + 10}" y="${f(y + h / 2 - 2.5)}" width="${f(w - 48)}" height="5" rx="2.5" fill="${glow || '#050506'}"/>
      ${glow ? `<rect x="${b.x + 6}" y="${f(y + h / 2 - 7)}" width="${f(w - 40)}" height="14" rx="7" fill="${glow}" opacity=".25"/>` : ''}
      <rect x="${f(ex)}" y="${f(y + h / 2 - 8)}" width="20" height="16" rx="3" fill="${dk(c, .3)}" stroke="${lt(c, .2)}"/>
      <path d="M${f(ex + 10)} ${f(y + h / 2 - 5)} l5 5.5 h-10 z M${f(ex + 5)} ${f(y + h / 2 + 2.5)} h10 v2 h-10 z" fill="${lt(c, .55)}"/>`;
  },
  // monnayeur de borne d'arcade : plaques chromées, fente et bouton lumineux
  coin(o, b, T) {
    const n = b.w >= 96 ? 2 : 1, pw = 40, ph = Math.min(b.h - 4, 54), g = id('co'), lit = o.color || '#ff3b2a';
    const x0 = b.x + (b.w - (n * pw + (n - 1) * 10)) / 2, y = b.y + (b.h - ph) / 2;
    return `<defs><linearGradient id="${g}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f4f5f8"/><stop offset=".5" stop-color="#9da1aa"/><stop offset="1" stop-color="#d9dbe1"/></linearGradient></defs>` +
      Array.from({ length: n }, (_, i) => {
        const x = x0 + i * (pw + 10);
        return `<rect x="${f(x)}" y="${f(y)}" width="${pw}" height="${f(ph)}" rx="5" fill="url(#${g})" stroke="#55585f" filter="url(#soft)"/>
          <rect x="${f(x + pw / 2 - 2.5)}" y="${f(y + ph * .14)}" width="5" height="${f(ph * .38)}" rx="2" fill="#0c0c0d"/>
          <circle cx="${f(x + pw / 2)}" cy="${f(y + ph * .76)}" r="7.5" fill="${lit}" opacity=".3"/>
          <circle cx="${f(x + pw / 2)}" cy="${f(y + ph * .76)}" r="4.6" fill="${lit}" stroke="${dk(lit, .5)}"/>`;
      }).join('');
  },
  // prises manette + fentes carte mémoire (consoles de salon à CD)
  pads(o, b, T) {
    const n = o.n || 2, c = o.color || dk(T.body[1], .55), pw = Math.min(46, (b.w - (n - 1) * 10) / n), x0 = b.x + (b.w - (n * pw + (n - 1) * 10)) / 2;
    const my = b.y + b.h / 2 - 17, py = b.y + b.h / 2 + 1;
    return Array.from({ length: n }, (_, i) => {
      const x = x0 + i * (pw + 10);
      return `<rect x="${f(x + 4)}" y="${f(my)}" width="${f(pw - 8)}" height="8" rx="2" fill="${dk(c, .5)}" stroke="${lt(c, .25)}"/>
        <rect x="${f(x)}" y="${f(py)}" width="${f(pw)}" height="16" rx="8" fill="${c}" stroke="${lt(c, .25)}"/>
        <rect x="${f(x + 8)}" y="${f(py + 5.5)}" width="${f(pw - 16)}" height="5" rx="2.5" fill="${dk(c, .6)}"/>`;
    }).join('');
  },
  // parabole satellite (Satellaview)
  dish(o, b, T) {
    const s = Math.min(b.h - 6, 50), cx = b.x + b.w / 2, cy = b.y + b.h / 2, c = o.color || '#e9e9ec', g = id('di');
    return `<defs><linearGradient id="${g}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${lt(c, .3)}"/><stop offset="1" stop-color="${dk(c, .35)}"/></linearGradient></defs>
      <path d="M${f(cx - s * .1)} ${f(cy + s * .2)} L${f(cx - s * .3)} ${f(cy + s * .5)} M${f(cx - s * .1)} ${f(cy + s * .2)} L${f(cx + s * .12)} ${f(cy + s * .5)}" stroke="${dk(c, .45)}" stroke-width="3" stroke-linecap="round"/>
      <ellipse cx="${f(cx - s * .1)}" cy="${f(cy - s * .05)}" rx="${f(s * .42)}" ry="${f(s * .3)}" transform="rotate(-30 ${f(cx - s * .1)} ${f(cy - s * .05)})" fill="url(#${g})" stroke="${dk(c, .4)}" stroke-width="1.2"/>
      <path d="M${f(cx - s * .1)} ${f(cy - s * .05)} L${f(cx + s * .38)} ${f(cy - s * .3)}" stroke="${dk(c, .45)}" stroke-width="2.4" stroke-linecap="round"/>
      <circle cx="${f(cx + s * .4)}" cy="${f(cy - s * .31)}" r="${f(s * .07)}" fill="${o.accent || '#3e5cc2'}"/>`;
  },
  // bouton d'éjection (lecteurs de disquettes, 64DD…)
  eject(o, b, T) {
    const c = o.color || dk(T.body[1], .35), w = Math.min(b.w - 4, 64), h = Math.min(b.h - 14, 30), x = b.x + (b.w - w) / 2, y = b.y + (b.h - h) / 2;
    return `<rect x="${f(x)}" y="${f(y + 2)}" width="${f(w)}" height="${f(h)}" rx="6" fill="${dk(c, .45)}"/>
      <rect x="${f(x)}" y="${f(y)}" width="${f(w)}" height="${f(h - 2)}" rx="6" fill="${c}" stroke="${lt(c, .2)}"/>
      <path d="M${f(x + w / 2)} ${f(y + h * .2)} l${f(h * .32)} ${f(h * .32)} h${f(-h * .64)} z M${f(x + w / 2 - h * .32)} ${f(y + h * .6)} h${f(h * .64)} v${f(h * .1)} h${f(-h * .64)} z" fill="${o.ink || lt(c, .6)}"/>`;
  },
  // stylet (Palm)
  stylus(o, b, T) {
    const c = o.color || '#9aa0aa', y = b.y + b.h / 2, x0 = b.x + 6, x1 = b.x + b.w - 6, g = id('st');
    return `<defs><linearGradient id="${g}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${lt(c, .45)}"/><stop offset=".5" stop-color="${c}"/><stop offset="1" stop-color="${dk(c, .4)}"/></linearGradient></defs>
      <g transform="rotate(-12 ${f((x0 + x1) / 2)} ${f(y)})" filter="url(#soft)">
        <path d="M${f(x0)} ${f(y)} L${f(x0 + 18)} ${f(y - 4.5)} H${f(x1 - 4)} Q${f(x1)} ${f(y - 4.5)} ${f(x1)} ${f(y)} Q${f(x1)} ${f(y + 4.5)} ${f(x1 - 4)} ${f(y + 4.5)} H${f(x0 + 18)} Z" fill="url(#${g})"/>
        <rect x="${f(x1 - 30)}" y="${f(y - 4.5)}" width="10" height="9" fill="${dk(c, .35)}"/></g>`;
  },
  // afficheur « turbo » des PC (7 segments) + bouton turbo
  turbo(o, b, T) {
    const c = o.color || dk(T.body[1], .55), led = o.led || '#ff3b2a', w = Math.min(b.w, 120), h = Math.min(b.h - 8, 40), x = b.x + (b.w - w) / 2, y = b.y + (b.h - h) / 2;
    return `<rect x="${f(x)}" y="${f(y)}" width="${f(w)}" height="${f(h)}" rx="5" fill="${c}" stroke="${lt(c, .15)}"/>
      <rect x="${f(x + 6)}" y="${f(y + 6)}" width="${f(w * .5)}" height="${f(h - 12)}" rx="3" fill="#120404"/>
      <text x="${f(x + 6 + w * .25)}" y="${f(y + h / 2 + (h - 12) * .3)}" text-anchor="middle" font-family="Consolas,'Courier New',monospace" font-weight="700" font-size="${f((h - 12) * .85)}" fill="${led}" filter="url(#glowW)">${o.text || '66'}</text>
      <rect x="${f(x + w * .62)}" y="${f(y + h / 2 - 8)}" width="${f(w * .3)}" height="16" rx="4" fill="${lt(c, .2)}" stroke="#000" filter="url(#soft)"/>`;
  },
  // boutons carrés en façade (POWER / RESET de la NES, PAUSE de la Master System…) + voyant
  squareButtons(o, b, T) {
    const n = o.n || 2, C = o.colors || [o.color || dk(T.body[1], .5)], s = Math.min(b.h - 18, 30, (b.w - (o.led ? 30 : 0) - (n - 1) * 12) / n);
    const y = b.y + (b.h - s) / 2, x0 = b.x + 4;
    return Array.from({ length: n }, (_, i) => {
      const x = x0 + i * (s + 12), c = C[i % C.length];
      return `<rect x="${f(x - 3)}" y="${f(y - 3)}" width="${f(s + 6)}" height="${f(s + 6)}" rx="5" fill="${dk(T.body[1], .3)}"/>
        <rect x="${f(x)}" y="${f(y)}" width="${f(s)}" height="${f(s)}" rx="3.5" fill="${c}" stroke="${dk(c, .45)}" filter="url(#soft)"/>
        <rect x="${f(x + 3)}" y="${f(y + 3)}" width="${f(s - 6)}" height="${f(s * .35)}" rx="2" fill="${lt(c, .25)}" opacity=".7"/>`;
    }).join('') + (o.led ? `<circle cx="${f(x0 + n * (s + 12) + 8)}" cy="${f(b.y + b.h / 2)}" r="11" fill="${o.led}" opacity=".25"/><circle cx="${f(x0 + n * (s + 12) + 8)}" cy="${f(b.y + b.h / 2)}" r="4.6" fill="${o.led}"/>` : '');
  },
  // interrupteurs à glissière (POWER / RESET de la Super Nintendo, de la N64…)
  sliders(o, b, T) {
    const n = o.n || 2, C = o.knobs || [o.knob || lt(T.body[1], .15)], tw = Math.min(70, (b.w - (n - 1) * 12) / n), th = 12;
    const y = b.y + b.h / 2, x0 = b.x + (b.w - (n * tw + (n - 1) * 12)) / 2, track = o.track || dk(T.body[1], .6);
    return Array.from({ length: n }, (_, i) => {
      const x = x0 + i * (tw + 12), c = C[i % C.length], kx = x + (i % 2 ? tw * .55 : 4);
      return `<rect x="${f(x)}" y="${f(y - th / 2)}" width="${f(tw)}" height="${th}" rx="${th / 2}" fill="${track}" stroke="${lt(T.body[1], .2)}"/>
        <rect x="${f(kx)}" y="${f(y - 12)}" width="${f(tw * .4)}" height="24" rx="5" fill="${c}" stroke="${dk(c, .45)}" filter="url(#soft)"/>
        <path d="M${f(kx + tw * .12)} ${f(y - 6)} v12 M${f(kx + tw * .2)} ${f(y - 6)} v12 M${f(kx + tw * .28)} ${f(y - 6)} v12" stroke="${dk(c, .3)}" stroke-width="1.2"/>`;
    }).join('');
  },
  // prise ronde DIN (manette PC Engine, 3DO…)
  din(o, b, T) {
    const n = o.n || 1, r = Math.min(b.h / 2 - 6, 19), c = o.color || dk(T.body[1], .55), x0 = b.x + (b.w - (n * 2 * r + (n - 1) * 14)) / 2 + r, cy = b.y + b.h / 2;
    return Array.from({ length: n }, (_, i) => {
      const cx = x0 + i * (2 * r + 14);
      // broches en arc de cercle, ouvert vers le bas
      const pins = Array.from({ length: 7 }, (_, k) => [cx + Math.cos(Math.PI * (.85 + k * .22)) * r * .52, cy + Math.sin(Math.PI * (.85 + k * .22)) * r * .52]);
      return `<circle cx="${f(cx)}" cy="${f(cy)}" r="${f(r + 3)}" fill="${lt(c, .25)}"/><circle cx="${f(cx)}" cy="${f(cy)}" r="${f(r)}" fill="${dk(c, .5)}"/>
        <rect x="${f(cx - 2.5)}" y="${f(cy - r)}" width="5" height="${f(r * .3)}" fill="${lt(c, .25)}"/>` +
        pins.map(([px, py]) => `<circle cx="${f(px)}" cy="${f(py)}" r="${f(Math.max(1.3, r * .09))}" fill="#c9a24a"/>`).join('') +
        `<circle cx="${f(cx)}" cy="${f(cy)}" r="${f(Math.max(1.3, r * .09))}" fill="#c9a24a"/>`;
    }).join('');
  },
  // souris et pointeur (jeux « pointer et cliquer »)
  mouse(o, b, T) {
    const c = o.color || '#e6e2d6', h = Math.min(b.h - 8, 46), w = h * .66, cx = b.x + b.w * .35, cy = b.y + b.h / 2;
    const ax = b.x + b.w * .72, ay = cy - h * .35, a = h * .55;
    return `<path d="M${f(cx)} ${f(cy - h / 2)} C${f(cx - 10)} ${f(cy - h / 2 - 10)} ${f(cx - 26)} ${f(cy - h / 2 + 2)} ${f(cx - 34)} ${f(cy - h / 2 - 6)}" fill="none" stroke="${dk(c, .45)}" stroke-width="2"/>
      <rect x="${f(cx - w / 2)}" y="${f(cy - h / 2)}" width="${f(w)}" height="${f(h)}" rx="${f(w / 2)}" fill="${c}" stroke="${dk(c, .4)}" filter="url(#soft)"/>
      <path d="M${f(cx - w / 2)} ${f(cy - h * .12)} H${f(cx + w / 2)} M${f(cx)} ${f(cy - h / 2)} V${f(cy - h * .12)}" stroke="${dk(c, .4)}" stroke-width="1.2"/>
      <path d="M${f(ax)} ${f(ay)} v${f(a)} l${f(a * .25)} ${f(-a * .24)} l${f(a * .17)} ${f(a * .36)} l${f(a * .12)} ${f(-a * .06)} l${f(-a * .17)} ${f(-a * .35)} h${f(a * .34)} z" fill="#fff" stroke="#000" stroke-width="1.4" stroke-linejoin="round"/>`;
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
