// Petits outils couleur (hex #rrggbb)
const hex = c => {
  c = c.replace('#', '');
  if (c.length === 3) c = c.split('').map(x => x + x).join('');
  return [0, 2, 4].map(i => parseInt(c.slice(i, i + 2), 16));
};
const toHex = a => '#' + a.map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');
const mix = (a, b, t) => { const A = hex(a), B = hex(b); return toHex(A.map((v, i) => v + (B[i] - v) * t)); };
const lt = (c, t) => mix(c, '#ffffff', t);
const dk = (c, t) => mix(c, '#000000', t);
const luma = c => { const [r, g, b] = hex(c); return (0.299 * r + 0.587 * g + 0.114 * b) / 255; };
const f = n => +(+n).toFixed(2);

module.exports = { mix, lt, dk, luma, f };
