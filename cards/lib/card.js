// Dessin d'une carte (SVG) et de ses zones : utilisé par build.js et par l'éditeur de cartes
// (installer.html, via bundle.js). opts.spine remplace la languette du thème.

const { mix, lt, dk, luma, f } = require('./color');
const HEROES = require('./heroes');
const { renderAux } = require('./details');

const LONG = 856, SHORT = 540, R = 31.8, SPINE = 156, GAP = 20;
const VARIANTS = { 'h-right': 'right', 'h-left': 'left', 'v': 'bottom' };

/* ------------------------------------------------------------------ */
/* Géométrie de chaque variante                                        */
/* ------------------------------------------------------------------ */
function geometry(side) {
  if (side === 'bottom') {
    const W = SHORT, H = LONG, S0 = H - SPINE;
    return {
      W, H, side, spine: { x: 0, y: S0, w: W, h: SPINE },
      hero: { cx: 336, cy: 548, k: .8 },
      cover: { x: 24, y: 76, w: W - 48, h: 432, r: 16 },
      fade: [0, 430, 0, 530],
      aux1: { x: 26, y: 538, w: 166, h: 62 }, aux2: { x: 26, y: 616, w: 166, h: 58 },
      zones: {
        logo: { x: 70, y: 12, w: W - 140, h: 52 },
        title: { x: 134, y: S0 + 18, w: W - 268, h: 120 },
        players: { x: 26, y: S0 + 50, w: 96, h: 56 },
        spineLogo: { x: W - 122, y: S0 + 50, w: 96, h: 56 },
      },
    };
  }
  const W = LONG, H = SHORT, S0 = W - SPINE, m = side === 'left';
  const mx = (b) => (m ? { ...b, x: W - b.x - b.w } : b);
  return {
    W, H, side, spine: mx({ x: S0, y: 0, w: SPINE, h: H }),
    hero: { cx: m ? W - 566 : 566, cy: 262, k: 1 },
    cover: mx({ x: 24, y: 24, w: 448, h: 426, r: 16 }),
    fade: m ? [W - 428, 0, W - 548, 0] : [428, 0, 548, 0],
    aux1: mx({ x: 494, y: 28, w: 184, h: 66 }), aux2: mx({ x: 494, y: 460, w: 190, h: 58 }),
    zones: {
      logo: mx({ x: 70, y: 466, w: 356, h: 54 }),
      title: { ...mx({ x: S0 + 22, y: 116, w: SPINE - 44, h: 318 }), rotate: m ? 90 : -90 }, // lisible boîtier tourné
      players: mx({ x: S0 + 28, y: 36, w: SPINE - 56, h: 56 }),
      spineLogo: mx({ x: S0 + 28, y: 452, w: SPINE - 56, h: 52 }),
    },
  };
}

const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
const rrect = ({ x, y, w, h, r }) => `M${x + r} ${y} H${x + w - r} Q${x + w} ${y} ${x + w} ${y + r} V${y + h - r} Q${x + w} ${y + h} ${x + w - r} ${y + h} H${x + r} Q${x} ${y + h} ${x} ${y + h - r} V${y + r} Q${x} ${y} ${x + r} ${y} Z`;

function carveShape(c, G) {
  const { cx, cy, k } = G.hero;
  if (c.type === 'circle') return `<circle cx="${cx}" cy="${cy}" r="${f(c.r * k + GAP)}"/>`;
  const w = c.w * k + 2 * GAP, h = c.h * k + 2 * GAP;
  return `<rect x="${f(cx - w / 2)}" y="${f(cy - h / 2)}" width="${f(w)}" height="${f(h)}" rx="${f((c.rx || 20) * k + GAP)}"/>`;
}
const strokeOf = (shape, attrs) => shape.replace('/>', ` ${attrs}/>`);

/* ------------------------------------------------------------------ */
/* Textures                                                            */
/* ------------------------------------------------------------------ */
function pattern(id, type, color) {
  switch (type) {
    case 'grid': return `<pattern id="${id}" width="17" height="17" patternUnits="userSpaceOnUse"><path d="M17 0H0V17" fill="none" stroke="${color}" stroke-width="1.1"/></pattern>`;
    case 'ribs': return `<pattern id="${id}" width="12" height="12" patternUnits="userSpaceOnUse"><rect y="3" width="12" height="3.5" fill="${dk(color, .25)}"/><rect y="6.5" width="12" height="1.2" fill="${lt(color, .35)}"/></pattern>`;
    case 'vribs': return `<pattern id="${id}" width="12" height="12" patternUnits="userSpaceOnUse"><rect x="3" width="3.5" height="12" fill="${dk(color, .25)}"/><rect x="6.5" width="1.2" height="12" fill="${lt(color, .35)}"/></pattern>`;
    case 'dots': return `<pattern id="${id}" width="9" height="9" patternUnits="userSpaceOnUse"><circle cx="4.5" cy="4.5" r="1.3" fill="${color}"/></pattern>`;
    case 'carbon': return `<pattern id="${id}" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="4" height="4" fill="${color}" opacity=".07"/><rect x="4" y="4" width="4" height="4" fill="${color}" opacity=".07"/><rect x="4" width="4" height="4" fill="#000" opacity=".12"/><rect y="4" width="4" height="4" fill="#000" opacity=".12"/></pattern>`;
  }
  return '';
}
function textureLayer(id, tex, x, y, w, h, extra = '') {
  if (!tex || tex.type === 'none' || tex.type === 'noise') return '';
  if (tex.type === 'wood') return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="#000" filter="url(#woodF)" opacity="${tex.opacity ?? .85}" ${extra}/>`;
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="url(#${id})" opacity="${tex.opacity ?? (tex.type === 'grid' ? .9 : .6)}" ${extra}/>`;
}

const FRAME = {
  chrome: ['#ffffff', '#b9bcc4', '#5d6068', '#d9dbe0'],
  gold: ['#fff6cf', '#e9c35c', '#9c6d12', '#f3d27a'],
};
const auto = bg => (luma(bg) > .55 ? '#26272b' : '#f4f4f6');
const pick = (want, bg) => (want && Math.abs(luma(want) - luma(bg)) > .35 ? want : auto(bg));

/* ------------------------------------------------------------------ */
/* Carte                                                               */
/* ------------------------------------------------------------------ */
function card(T, side, opts = {}) {
  const G = geometry(side), { W, H, spine: SP } = G;
  const body = T.body, sp = { bg: dk(body[1], .15), ...(opts.spine || T.spine || {}) };
  const hero = HEROES[T.hero.type](T.hero, T);
  // motif rectangulaire : on le garde entièrement visible (pas sous la languette)
  if (hero.carve.type === 'rect') {
    const hw = hero.carve.w / 2 * G.hero.k, hh = hero.carve.h / 2 * G.hero.k;
    if (side === 'right') G.hero.cx = Math.min(G.hero.cx, SP.x - 8 - hw);
    if (side === 'left') G.hero.cx = Math.max(G.hero.cx, SP.x + SP.w + 8 + hw);
    if (side === 'bottom') { G.hero.cy = Math.min(G.hero.cy, SP.y - 8 - hh); G.hero.cx = Math.min(G.hero.cx, W - 14 - hw); }
  }
  const carve = carveShape(hero.carve, G);
  const win = rrect(G.cover);
  const tex = T.texture || { type: 'noise' };
  const texColor = tex.color || (luma(body[1]) > .5 ? dk(body[1], .18) : lt(body[1], .16));
  const frameC = T.frame && !FRAME[T.frame] ? [lt(T.frame, .45), T.frame, dk(T.frame, .35), lt(T.frame, .2)] : FRAME[T.frame || 'chrome'];
  const v = side === 'bottom', m = side === 'left';
  const toSpine = v ? 'x1="0" y1="0" x2="0" y2="1"' : m ? 'x1="1" y1="0" x2="0" y2="0"' : 'x1="0" y1="0" x2="1" y2="0"';
  const shade = v ? { x: 0, y: SP.y - 30, w: W, h: 30 } : { x: m ? SP.x + SP.w : SP.x - 30, y: 0, w: 30, h: H };
  const edge = v ? { x: 0, y: SP.y, w: W, h: 1.2 } : { x: m ? SP.x + SP.w - 1.2 : SP.x, y: 0, w: 1.2, h: H };
  const spTex = sp.texture ? { type: sp.texture, opacity: sp.texture === 'grid' ? .55 : .5 } : null;
  const [g1, g2, g3, g4] = G.fade;
  const titleInk = pick(sp.ink || T.ink, sp.bg);
  const logoInk = pick(T.logoInk || T.ink, body[1]);
  const filet = T.frame && !FRAME[T.frame] ? T.frame : null;

  const defs = `
    <clipPath id="card"><rect width="${W}" height="${H}" rx="${R}"/></clipPath>
    <clipPath id="win"><path d="${win}"/></clipPath>
    <mask id="hole" maskUnits="userSpaceOnUse" x="0" y="0" width="${W}" height="${H}"><rect width="${W}" height="${H}" fill="#fff"/><path d="${win}" fill="#000"/>${strokeOf(carve, 'fill="#fff"')}</mask>
    <mask id="noCarve" maskUnits="userSpaceOnUse" x="0" y="0" width="${W}" height="${H}"><rect width="${W}" height="${H}" fill="#fff"/>${strokeOf(carve, 'fill="#000"')}</mask>
    <linearGradient id="bodyG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${body[0]}"/><stop offset=".6" stop-color="${body[1]}"/><stop offset="1" stop-color="${body[2]}"/></linearGradient>
    <linearGradient id="spineG" ${toSpine}><stop offset="0" stop-color="${dk(sp.bg, .55)}"/><stop offset=".08" stop-color="${lt(sp.bg, .1)}"/><stop offset=".5" stop-color="${sp.bg}"/><stop offset="1" stop-color="${dk(sp.bg, .35)}"/></linearGradient>
    <linearGradient id="spineShade" ${toSpine}><stop offset="0" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="${luma(body[1]) > .5 ? .35 : .75}"/></linearGradient>
    <linearGradient id="fadeG" gradientUnits="userSpaceOnUse" x1="${g1}" y1="${g2}" x2="${g3}" y2="${g4}"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
    <mask id="fadeM" maskUnits="userSpaceOnUse" x="0" y="0" width="${W}" height="${H}"><rect width="${W}" height="${H}" fill="url(#fadeG)"/></mask>
    ${pattern('tex', tex.type, texColor)}
    ${spTex ? pattern('spTex', spTex.type, lt(sp.bg, luma(sp.bg) > .5 ? -0 : .18)) : ''}
    <linearGradient id="frameG" x1="0" y1="0" x2="0" y2="1">${frameC.map((c, i) => `<stop offset="${[0, .45, .52, 1][i]}" stop-color="${c}"/>`).join('')}</linearGradient>
    <linearGradient id="filetG" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="${filet || '#9a9da6'}" stop-opacity="0"/><stop offset=".5" stop-color="${filet || '#e8e9ee'}"/><stop offset="1" stop-color="${filet || '#9a9da6'}" stop-opacity="0"/></linearGradient>
    <linearGradient id="sheen" x1="0" y1="0" x2="1" y2=".62"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".38" stop-color="#fff" stop-opacity="0"/><stop offset=".46" stop-color="#fff" stop-opacity=".07"/><stop offset=".6" stop-color="#fff" stop-opacity="0"/></linearGradient>
    <linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".22"/><stop offset=".35" stop-color="#fff" stop-opacity=".04"/><stop offset=".36" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
    <radialGradient id="crtVignette" r=".75"><stop offset=".6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".6"/></radialGradient>
    <pattern id="scan" width="4" height="3" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#000" opacity=".5"/></pattern>
    <pattern id="dither" width="2" height="2" patternUnits="userSpaceOnUse"><rect width="1" height="1" fill="#000" opacity=".25"/><rect x="1" y="1" width="1" height="1" fill="#000" opacity=".25"/></pattern>
    <filter id="noise" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="2" seed="3"/><feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .07 0"/><feComposite in2="SourceGraphic" operator="in"/></filter>
    <filter id="woodF" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".008 .16" numOctaves="3" seed="7"/><feColorMatrix values=".55 0 0 0 .22  .34 0 0 0 .12  .16 0 0 0 .04  0 0 0 0 1"/><feComposite in2="SourceGraphic" operator="in"/></filter>
    <filter id="drop" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="6" stdDeviation="7" flood-color="#000" flood-opacity="${luma(body[1]) > .5 ? .45 : .8}"/></filter>
    <filter id="soft" x="-10%" y="-10%" width="120%" height="120%"><feDropShadow dx="0" dy="1.5" stdDeviation="1.2" flood-color="#000" flood-opacity=".7"/></filter>
    <filter id="glowW" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>`;

  const art = `
      <rect width="${W}" height="${H}" fill="url(#bodyG)"/>
      ${textureLayer('tex', tex, 0, 0, W, H, tex.fade ? 'mask="url(#fadeM)"' : '')}
      <rect width="${W}" height="${H}" filter="url(#noise)"/>

      <!-- encadré de la jaquette -->
      <g mask="url(#noCarve)">
        <path d="${win}" fill="none" stroke="#000" stroke-width="14" stroke-opacity="${luma(body[1]) > .5 ? .3 : .7}" transform="translate(0 2)"/>
        <path d="${win}" fill="none" stroke="url(#frameG)" stroke-width="3.2"/>
      </g>
      <g clip-path="url(#win)">
        ${strokeOf(carve, `fill="none" stroke="#000" stroke-width="14" stroke-opacity="${luma(body[1]) > .5 ? .3 : .7}"`)}
        ${strokeOf(carve, 'fill="none" stroke="url(#frameG)" stroke-width="3.2"')}
      </g>

      <!-- détails -->
      <g id="aux1">${renderAux(T.aux1, G.aux1, T)}</g>
      <g id="aux2">${renderAux(T.aux2, G.aux2, T)}</g>

      <!-- motif principal -->
      <g id="hero" transform="translate(${G.hero.cx} ${G.hero.cy}) scale(${G.hero.k})">${hero.svg}</g>

      <rect width="${W}" height="${H}" fill="url(#sheen)"/>

      <!-- languette (partie qui dépasse du lecteur) -->
      <g id="spine">
        <rect x="${shade.x}" y="${shade.y}" width="${shade.w}" height="${shade.h}" fill="url(#spineShade)"/>
        <rect x="${SP.x}" y="${SP.y}" width="${SP.w}" height="${SP.h}" fill="url(#spineG)"/>
        ${spTex ? textureLayer('spTex', spTex, SP.x, SP.y, SP.w, SP.h) : ''}
        <rect x="${edge.x}" y="${edge.y}" width="${edge.w}" height="${edge.h}" fill="${lt(sp.bg, .35)}" opacity=".6"/>
      </g>`;

  const lg = G.zones.logo, ly = lg.y + lg.h / 2, cv = G.cover;
  const overlay = `
    <rect x="${cv.x}" y="${ly}" width="40" height="1.6" fill="url(#filetG)"/>
    <rect x="${cv.x + cv.w - 40}" y="${ly}" width="40" height="1.6" fill="url(#filetG)"/>`;

  const label = { right: 'horizontale, languette à droite', left: 'horizontale, languette à gauche', bottom: 'verticale, languette en bas' }[side];
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W / 10}mm" height="${H / 10}mm">
  <title>${esc(T.name)} — carte ${label}</title>
  <defs>${defs}
  </defs>
  <g clip-path="url(#card)">
    <g id="art" mask="url(#hole)">${art}
    </g>${overlay}
  </g>
</svg>
`;
  const zones = {
    viewBox: [W, H],
    cover: { x: cv.x, y: cv.y, w: cv.w, h: cv.h, note: 'cover sits underneath; the card hides the notch carved by the motif' },
    ...G.zones,
    style: { titleColor: titleInk, logoColor: logoInk, spineColor: sp.bg },
  };
  return { svg, zones };
}

module.exports = { card, VARIANTS, R };
