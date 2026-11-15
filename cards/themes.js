// Thèmes par plateforme (clé = nom du fichier dans platforms/).
// name/short : textes provisoires (logo / mini-logo) en attendant les vrais logos.
// body : [clair, moyen, foncé] du plastique ; texture : grid | ribs | vribs | dots | carbon | wood | none
// hero : motif principal (lib/heroes.js) ; aux1 / aux2 : détails (lib/details.js)
// spine : languette { bg, texture, ink } ; ink : couleur du texte sur la carte.

const RAINBOW = ['#e8262b', '#f6a01a', '#f7e017', '#22a84a', '#1e8fd6'];
const SPECTRUM = ['#d8262e', '#f4cf1d', '#3fae4b', '#2a9fd8'];
const APPLE = ['#61bb46', '#fdb827', '#f5821f', '#e03a3e', '#963d97', '#009ddc'];
const NEO = ['#e3262e', '#f5c61b', '#22a84a', '#2a63d6'];
const SNESC = ['#3e5cc2', '#d3262e', '#f3b81f', '#1d9a4c'];

const dark = (a, b, c) => [a, b, c];
const BLACK = ['#1d1d20', '#121214', '#0a0a0b'];
const GREY = ['#d9d8dc', '#c6c5ca', '#a9a8ae'];
const BEIGE = ['#e9e1cc', '#d9cfb6', '#bdb194'];
const WHITE = ['#f6f6f4', '#e6e6e3', '#cfcfcb'];

module.exports = {
  /* ---------------- Sega ---------------- */
  megadrive: {
    name: 'MEGA DRIVE', short: 'MD', body: BLACK, texture: { type: 'grid', color: '#3a3a3f', fade: true },
    hero: { type: 'dome', mark: { text: '16-BIT', style: 'gold', y: -52, size: 44 }, arc: { text: 'HIGH DEFINITION GRAPHIC', color: '#d8262e' } },
    aux1: { type: 'vents', skew: true }, aux2: { type: 'power' },
    spine: { bg: '#101012', texture: 'grid' },
  },
  sega32x: {
    name: 'SEGA 32X', short: '32X', body: BLACK, texture: { type: 'grid', color: '#3a3a3f', fade: true },
    hero: { type: 'dome', accent: '#e3262e', mark: { text: '32X', style: 'red', y: -50, size: 50 }, arc: { text: '32-BIT  SUPER  POWER', color: '#f5c61b' } },
    aux1: { type: 'hstripes', colors: ['#e3262e', '#f5c61b'] }, aux2: { type: 'power', led: '#ff3b2a' },
    spine: { bg: '#101012', texture: 'grid' },
  },
  megacd: {
    name: 'MEGA-CD', short: 'CD', body: BLACK, texture: { type: 'grid', color: '#3a3a3f', fade: true },
    hero: { type: 'disc', base: '#141416', lid: '#232327', hub: '#111', arc: { text: 'COMPACT DISC  ·  16-BIT', color: '#d8262e' }, mark: { text: 'CD', style: 'chrome', y: -62, size: 30 } },
    aux1: { type: 'vents' }, aux2: { type: 'power', volume: false },
    spine: { bg: '#101012', texture: 'grid' },
  },
  mastersystem: {
    name: 'MASTER SYSTEM', short: 'SMS', body: BLACK, texture: { type: 'grid', color: '#e8e8e8', opacity: .16, fade: true },
    hero: { type: 'slot', case: '#141416', cart: '#0f0f11', label: '#e3262e', band: '#d8262e', bandH: 6, ribs: true },
    aux1: { type: 'hstripes', colors: ['#d8262e', '#d8262e'], h: 4 }, aux2: [{ type: 'power', led: '#ff3b2a', volume: false }],
    spine: { bg: '#121214', texture: 'grid' }, frame: '#d8262e',
  },
  sg1000: {
    name: 'SG-1000', short: 'SG', body: WHITE, texture: { type: 'ribs', color: '#bdbdb8' },
    hero: { type: 'slot', case: '#e9e9e5', cart: '#2b2b2e', label: '#d8262e', band: '#d8262e', bandH: 10 },
    aux1: { type: 'hstripes', colors: ['#d8262e', '#1e1e20'], h: 5 }, aux2: { type: 'power', led: '#ff3b2a', panel: '#2a2a2e', volume: false },
    spine: { bg: '#1b1b1d' }, ink: '#2a2a2e',
  },
  gamegear: {
    name: 'GAME GEAR', short: 'GG', body: dark('#2c2c30', '#1c1c1f', '#101012'), texture: { type: 'noise' },
    hero: { type: 'screen', w: 300, h: 230, bezel: '#18181b', content: 'color', label: 'FULL COLOR', labelInk: '#6f86c8', led: '#3f6' },
    aux1: { type: 'dpad', color: '#18181a' }, aux2: { type: 'ab', colors: ['#2b2b2f', '#2b2b2f'], pill: '#2856c8' },
    spine: { bg: '#141416' },
  },
  saturn: {
    name: 'SATURN', short: 'SS', body: dark('#3a3a3f', '#26262a', '#161618'), texture: { type: 'carbon' },
    hero: { type: 'disc', base: '#1d1d21', lid: '#3b3b41', hub: '#2a2a2e', arc: { text: '32-BIT  ·  DUAL CPU', color: '#8fa0d8' },
      buttons: [{ x: 128, y: 100, r: 13, color: '#3f68d6' }, { x: 100, y: 128, r: 13, color: '#8f8f96' }] },
    aux1: { type: 'vents' }, aux2: { type: 'roundButtons', color: '#55555c', led: '#3f6' },
    spine: { bg: '#18181b', texture: 'carbon' },
  },
  dreamcast: {
    name: 'DREAMCAST', short: 'DC', body: WHITE, texture: { type: 'none' },
    hero: { type: 'disc', base: '#e1e1de', lid: '#f5f5f2', hub: '#e4e4e0', hub: false, swirl: '#f26a21', rings: false },
    aux1: { type: 'roundButtons', n: 2, color: '#d9d9d5', led: '#f26a21' }, aux2: { type: 'ports', n: 2, color: '#c9c9c4' },
    spine: { bg: '#ecece8' }, ink: '#3a3a3a', frame: '#f26a21',
  },
  pico: {
    name: 'PICO', short: 'PICO', body: dark('#3ba4e0', '#1f86c8', '#145f94'), texture: { type: 'dots', color: '#ffffff', opacity: .15 },
    hero: { type: 'slot', case: '#f4d22c', cart: '#e8432e', label: '#3ba4e0' },
    aux1: { type: 'hstripes', colors: ['#e8432e', '#f4d22c', '#3fae4b'] }, aux2: { type: 'ab', colors: ['#e8432e', '#3fae4b'] },
    spine: { bg: '#1a6fa8' },
  },
  naomi: {
    name: 'NAOMI', short: 'NAOMI', body: dark('#2c3a5c', '#1d2742', '#111729'), texture: { type: 'carbon' },
    hero: { type: 'arcade', plate: '#1a2238', ball: '#e3262e', colors: ['#2a63d6', '#2a63d6', '#2a63d6', '#e3262e', '#e3262e', '#e3262e'], six: true, arc: { text: 'ARCADE  ·  NEW ARCHITECTURE', color: '#8fb4ff' } },
    aux1: { type: 'vents' }, aux2: { type: 'leds', colors: ['#3f6', '#ff3b2a'] },
    spine: { bg: '#141b30', texture: 'carbon' },
  },
  naomi2: {
    name: 'NAOMI 2', short: 'N2', body: dark('#9aa3b5', '#7c8597', '#5a6273'), texture: { type: 'carbon' },
    hero: { type: 'arcade', plate: '#2b3040', ball: '#2a63d6', colors: ['#e3262e', '#e3262e', '#e3262e', '#f5c61b', '#f5c61b', '#f5c61b'], six: true, arc: { text: 'ARCADE  ·  DUAL GPU', color: '#cfd8ea' } },
    aux1: { type: 'vents' }, aux2: { type: 'leds', colors: ['#3f6', '#3f6', '#ff3b2a'] },
    spine: { bg: '#3b4150' },
  },
  naomigd: {
    name: 'NAOMI GD-ROM', short: 'GD', body: dark('#2c3a5c', '#1d2742', '#111729'), texture: { type: 'carbon' },
    hero: { type: 'disc', base: '#141b30', lid: '#c9ccd6', hub: '#9aa0ad', arc: { text: 'GD-ROM  ·  ARCADE', color: '#8fb4ff' } },
    aux1: { type: 'vents' }, aux2: { type: 'leds', colors: ['#3f6', '#ff3b2a'] },
    spine: { bg: '#141b30' },
  },
  atomiswave: {
    name: 'ATOMISWAVE', short: 'AW', body: dark('#3a3a3f', '#26262a', '#161618'), texture: { type: 'carbon' },
    hero: { type: 'arcade', plate: '#1c1c20', ball: '#f26a21', colors: ['#f26a21', '#f5c61b', '#22a84a', '#2a63d6'], stripe: '#f26a21', arc: { text: 'ARCADE  ·  CARTRIDGE SYSTEM', color: '#f26a21' } },
    aux1: { type: 'hstripes', colors: ['#f26a21', '#f5c61b'] }, aux2: { type: 'leds', colors: ['#f26a21', '#3f6'] },
    spine: { bg: '#18181b' },
  },

  /* ---------------- Nintendo ---------------- */
  nes: {
    name: 'NES', short: 'NES', body: dark('#dcdcd8', '#c9c9c4', '#adada8'), texture: { type: 'ribs', color: '#a9a9a4' },
    hero: { type: 'buttons', layout: 'nes', plate: '#c9c9c4' },
    aux1: { type: 'ribs', color: '#2a2a2c' }, aux2: [{ type: 'power', panel: '#2a2a2c', led: '#ff2a1a', knob: '#555', volume: false }],
    spine: { bg: '#2c2c2f', texture: 'ribs' }, ink: '#2c2c2f', frame: '#c4161c',
  },
  famicomdisksystem: {
    name: 'FAMICOM DISK', short: 'FDS', body: dark('#b42b33', '#9a1f27', '#741319'), texture: { type: 'ribs', color: '#6e1015' },
    hero: { type: 'disk', case: '#efe6d2', media: '#f2c21b', led: '#ff3b2a', eject: '#9a1f27' },
    aux1: { type: 'hstripes', colors: ['#efe6d2', '#d6b347'] }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#efe6d2' },
  },
  snes: {
    name: 'SUPER NINTENDO', short: 'SNES', body: GREY, texture: { type: 'dots', color: '#ffffff', opacity: .25 },
    hero: { type: 'buttons', layout: 'diamond', plate: '#c9c8ce', colors: SNESC },
    aux1: { type: 'hstripes', colors: ['#46474b', '#46474b'], h: 9 }, aux2: [{ type: 'power', panel: '#86878b', knob: '#5a5a62', led: '#c11b25', volume: false }],
    spine: { bg: '#86878b' }, ink: '#2e2f33',
  },
  satellaview: {
    name: 'SATELLAVIEW', short: 'BS-X', body: GREY, texture: { type: 'dots', color: '#ffffff', opacity: .25 },
    hero: { type: 'disc', base: '#b7b6bc', lid: '#e3e2e7', hub: '#9c9ba2', glow: '#6fa8ff', arc: { text: 'SATELLITE  DATA  BROADCAST', color: '#5b5ca8' } },
    aux1: { type: 'hstripes', colors: SNESC }, aux2: { type: 'leds', colors: ['#6fa8ff', '#3f6'] },
    spine: { bg: '#86878b' }, ink: '#2e2f33',
  },
  sufamiturbo: {
    name: 'SUFAMI TURBO', short: 'ST', body: GREY, texture: { type: 'dots', color: '#ffffff', opacity: .25 },
    hero: { type: 'slot', case: '#c9c8ce', cart: '#d9d8de', label: '#e6a21b', double: true },
    aux1: { type: 'hstripes', colors: SNESC }, aux2: { type: 'leds', colors: ['#c11b25'] },
    spine: { bg: '#86878b' }, ink: '#2e2f33',
  },
  nintendo64: {
    name: 'NINTENDO 64', short: 'N64', body: dark('#3c3c40', '#2b2b2e', '#18181a'), texture: { type: 'noise' },
    hero: { type: 'buttons', layout: 'n64', plate: '#9a9aa0', colors: ['#2b56c8', '#1f9a4a', '#f2c518'], mark: { text: '64-BIT', style: 'chrome', y: -112, size: 22 } },
    aux1: { type: 'hstripes', colors: ['#e3262e', '#22a84a', '#2a63d6', '#f5c61b'], h: 4 }, aux2: [{ type: 'power', led: '#ff3b2a', volume: false }],
    spine: { bg: '#1e1e21' },
  },
  nintendo64dd: {
    name: '64DD', short: '64DD', body: dark('#3c3c40', '#2b2b2e', '#18181a'), texture: { type: 'noise' },
    hero: { type: 'disk', case: '#2b2b2e', media: '#5a5a62', shutter: '#9a9aa0', led: '#3f6' },
    aux1: { type: 'hstripes', colors: ['#e3262e', '#22a84a', '#2a63d6', '#f5c61b'], h: 4 }, aux2: { type: 'leds', colors: ['#3f6', '#ff3b2a'] },
    spine: { bg: '#1e1e21' },
  },
  gamecube: {
    name: 'GAMECUBE', short: 'GC', body: dark('#5d4fa6', '#463a8c', '#2f2666'), texture: { type: 'none' },
    hero: { type: 'buttons', layout: 'gc', plate: '#4a3e93', colors: ['#1fb36a', '#e2312e', '#c9c9d4'] },
    aux1: { type: 'roundButtons', n: 2, color: '#6a5cba', led: '#3f6' }, aux2: { type: 'ports', n: 2, color: '#2f2666' },
    spine: { bg: '#3a2f7a' },
  },
  wii: {
    name: 'Wii', short: 'Wii', body: WHITE, texture: { type: 'none' },
    hero: { type: 'disc', base: '#e8e8e6', lid: '#fbfbfa', hub: '#e0e0de', glow: '#38b6ff', rings: false, dot: '#38b6ff' },
    aux1: { type: 'roundButtons', n: 2, color: '#ececea', led: '#38b6ff' }, aux2: { type: 'leds', colors: ['#38b6ff', '#38b6ff'] },
    spine: { bg: '#efefed' }, ink: '#404044', frame: '#38b6ff',
  },
  virtualboy: {
    name: 'VIRTUAL BOY', short: 'VB', body: dark('#2a2a2c', '#1a1a1c', '#0c0c0d'), texture: { type: 'noise' },
    hero: { type: 'screen', w: 310, h: 200, bezel: '#0d0d0e', body: '#b3121b', content: 'vb', rx: 60, top: 26, bottom: 26, pad: 46 },
    aux1: { type: 'hstripes', colors: ['#b3121b', '#b3121b'], h: 5 }, aux2: { type: 'ab', colors: ['#b3121b', '#b3121b'] },
    spine: { bg: '#121213' }, ink: '#ff3b3b', frame: '#b3121b',
  },
  gameboy: {
    name: 'GAME BOY', short: 'GB', body: dark('#d4d2cd', '#c3c1bb', '#a8a69f'), texture: { type: 'none' },
    hero: { type: 'screen', w: 290, h: 240, bezel: '#5c5d70', body: '#c9c7c1', content: 'dmg', label: 'DOT MATRIX · STEREO SOUND', labelInk: '#c8c8d8', led: '#e3262e', stripes: ['#8a2c5c', '#2d2e8a'], cornerCut: true, top: 32 },
    aux1: { type: 'dpad', color: '#2a2a2c' }, aux2: { type: 'ab', colors: ['#9a2257', '#9a2257'], pill: '#8f8d88' },
    spine: { bg: '#bdbbb4' }, ink: '#2d2e8a', frame: '#5c5d70',
  },
  gameboycolor: {
    name: 'GAME BOY COLOR', short: 'GBC', body: dark('#8a55c9', '#6b3fa6', '#4a2a78'), texture: { type: 'dots', color: '#fff', opacity: .12 },
    hero: { type: 'screen', w: 290, h: 230, bezel: '#2a2a33', content: 'color', label: 'COLOR', labelInk: '#fff', led: '#3f6', stripes: ['#e3262e', '#f5c61b', '#22a84a', '#2a63d6'] },
    aux1: { type: 'dpad', color: '#1e1e22' }, aux2: { type: 'ab', colors: ['#2e2e36', '#2e2e36'], pill: '#3a2560' },
    spine: { bg: '#4f2f86' },
  },
  gameboyadvance: {
    name: 'GAME BOY ADVANCE', short: 'GBA', body: dark('#6a5fc9', '#5246ad', '#372d80'), texture: { type: 'none' },
    hero: { type: 'screen', w: 320, h: 210, bezel: '#26263a', content: 'color', rx: 40, led: '#3f6', pad: 54, top: 24, bottom: 24, pal: ['#8fd3ff', '#ffe08a', '#e0663a', '#2a3a8a'] },
    aux1: { type: 'dpad', color: '#2a2a33' }, aux2: { type: 'ab', colors: ['#b8b8c6', '#b8b8c6'], pill: '#3e348c' },
    spine: { bg: '#3d3290' },
  },
  nds: {
    name: 'NINTENDO DS', short: 'DS', body: dark('#d2d5da', '#b9bdc4', '#959aa3'), texture: { type: 'none' },
    hero: { type: 'screen', w: 230, h: 300, bezel: '#2a2c31', body: '#c9ccd2', content: 'dual', pad: 26, top: 24, bottom: 24, led: '#3f6' },
    aux1: { type: 'dpad', color: '#2a2c31' }, aux2: { type: 'buttons4' },
    spine: { bg: '#3a3d44' }, ink: '#2a2c31',
  },
  pokemini: {
    name: 'POKEMON MINI', short: 'MINI', body: dark('#4a8fd6', '#2f74c0', '#1f5394'), texture: { type: 'dots', color: '#fff', opacity: .12 },
    hero: { type: 'screen', w: 250, h: 220, bezel: '#24324a', content: 'mono', rx: 40, led: '#f5c61b' },
    aux1: { type: 'dpad', color: '#24324a' }, aux2: { type: 'ab', colors: ['#24324a', '#24324a'] },
    spine: { bg: '#1f5394' },
  },
  gameandwatch: {
    name: 'GAME & WATCH', short: 'G&W', body: dark('#d9c58c', '#c2a96a', '#9c8448'), texture: { type: 'vribs', color: '#b39a5c' },
    hero: { type: 'screen', w: 310, h: 220, bezel: '#2a2a2c', body: '#d6c38a', content: 'lcd', rx: 10, label: 'WIDE SCREEN', labelInk: '#d9c58c' },
    aux1: { type: 'dpad', color: '#e8622b' }, aux2: { type: 'ab', colors: ['#e8622b', '#e8622b'], pills: false },
    spine: { bg: '#2a2a2c' }, ink: '#2a2a2c', frame: '#2a2a2c',
  },

  /* ---------------- Sony ---------------- */
  playstation1: {
    name: 'PLAYSTATION', short: 'PS1', body: dark('#d6d6d8', '#c3c3c6', '#a8a8ac'), texture: { type: 'none' },
    hero: { type: 'disc', base: '#b9b9bd', lid: '#cfcfd2', hub: '#bdbdc1', buttons: [{ x: -132, y: 100, r: 15, color: '#c9c9cc' }, { x: 132, y: 100, r: 15, color: '#c9c9cc' }] },
    aux1: { type: 'ps' }, aux2: { type: 'roundButtons', n: 2, color: '#cfcfd2', led: '#3f6' },
    spine: { bg: '#a5a5aa' }, ink: '#3a3a40',
  },
  playstation2: {
    name: 'PLAYSTATION 2', short: 'PS2', body: BLACK, texture: { type: 'ribs', color: '#2a2a30' },
    hero: { type: 'disc', base: '#0e0e10', lid: '#1d1d22', hub: '#111', glow: '#2f5bff', dot: '#2f5bff' },
    aux1: { type: 'ps' }, aux2: { type: 'leds', colors: ['#3f6', '#2f5bff'] },
    spine: { bg: '#0f0f12', texture: 'ribs' }, frame: '#2f5bff',
  },
  psp: {
    name: 'PSP', short: 'PSP', body: BLACK, texture: { type: 'none' },
    hero: { type: 'screen', w: 320, h: 190, bezel: '#0b0b0d', body: '#151518', content: 'color', rx: 80, pad: 60, top: 22, bottom: 22, pal: ['#1c2a5a', '#7fb8ff', '#3a5ac8', '#0a1030'] },
    aux1: { type: 'dpad', color: '#2a2a2e' }, aux2: { type: 'ps' },
    spine: { bg: '#0d0d0f' }, frame: 'chrome',
  },

  /* ---------------- NEC ---------------- */
  pcengine: {
    name: 'PC ENGINE', short: 'PCE', body: WHITE, texture: { type: 'vribs', color: '#d0d0cc' },
    hero: { type: 'slot', case: '#ececea', cart: '#2b2b2e', label: '#e3262e', cartW: 150, mark: { text: 'HuCARD', style: '#e3262e', y: 82, size: 20 } },
    aux1: { type: 'hstripes', colors: ['#e3262e', '#f26a21'], h: 5 }, aux2: [{ type: 'power', panel: '#bdbdb8', knob: '#ececea', led: '#ff3b2a', volume: false }],
    spine: { bg: '#2b2b2e' }, ink: '#c41a1a', frame: '#e3262e',
  },
  supergrafx: {
    name: 'SUPERGRAFX', short: 'SGX', body: dark('#5a5a60', '#46464c', '#2e2e33'), texture: { type: 'vribs', color: '#3a3a40' },
    hero: { type: 'slot', case: '#3a3a40', cart: '#2b2b2e', label: '#e3262e', cartW: 150, mark: { text: 'SUPER', style: 'chrome', y: 82, size: 20 } },
    aux1: { type: 'hstripes', colors: ['#e3262e', '#f26a21'], h: 5 }, aux2: { type: 'power', led: '#ff3b2a', volume: false },
    spine: { bg: '#2b2b30' },
  },
  pcenginecd: {
    name: 'PC ENGINE CD', short: 'CD', body: WHITE, texture: { type: 'vribs', color: '#d0d0cc' },
    hero: { type: 'disc', base: '#d9d9d5', lid: '#ececea', hub: '#cfcfcb', arc: { text: 'CD-ROM²  SYSTEM', color: '#e3262e' } },
    aux1: { type: 'hstripes', colors: ['#e3262e', '#f26a21'], h: 5 }, aux2: { type: 'roundButtons', n: 2, color: '#e3e3df', led: '#ff3b2a' },
    spine: { bg: '#2b2b2e' }, ink: '#c41a1a', frame: '#e3262e',
  },
  pcfx: {
    name: 'PC-FX', short: 'FX', body: dark('#2e2e33', '#1f1f23', '#121214'), texture: { type: 'vribs', color: '#2a2a30' },
    hero: { type: 'disc', base: '#161619', lid: '#3a3a40', hub: '#2a2a2e', arc: { text: '32-BIT  ·  FULL MOTION', color: '#f26a21' } },
    aux1: { type: 'vents' }, aux2: { type: 'leds', colors: ['#3f6', '#f26a21'] },
    spine: { bg: '#141416' },
  },

  /* ---------------- SNK ---------------- */
  neogeo: {
    name: 'NEO GEO', short: 'NEO', body: dark('#2d2d2d', '#212121', '#141414'), texture: { type: 'carbon' },
    hero: { type: 'arcade', plate: '#1a1a1a', ball: '#e3262e', colors: NEO, stripe: '#c19528', mark: { text: 'MAX 330 MEGA', style: 'gold', y: 112, size: 18, italic: false } },
    aux1: { type: 'hstripes', colors: ['#c19528', '#c19528'], h: 4 }, aux2: { type: 'power', led: '#f7b210', volume: false },
    spine: { bg: '#161616', texture: 'carbon' }, ink: '#f7d36a', frame: 'gold',
  },
  neogeocd: {
    name: 'NEO GEO CD', short: 'NGCD', body: dark('#2d2d2d', '#212121', '#141414'), texture: { type: 'carbon' },
    hero: { type: 'disc', base: '#151515', lid: '#2c2c2c', hub: '#1c1c1c', arc: { text: 'CD-ROM  ·  ARCADE AT HOME', color: '#c19528' }, buttons: [{ x: 120, y: -112, r: 12, color: '#e3262e' }, { x: 140, y: -82, r: 12, color: '#2a63d6' }] },
    aux1: { type: 'hstripes', colors: ['#c19528', '#c19528'], h: 4 }, aux2: { type: 'leds', colors: ['#f7b210', '#3f6'] },
    spine: { bg: '#161616', texture: 'carbon' }, ink: '#f7d36a', frame: 'gold',
  },
  ngp: {
    name: 'NEO GEO POCKET', short: 'NGP', body: dark('#3a4a7a', '#2b3a66', '#1c264a'), texture: { type: 'none' },
    hero: { type: 'screen', w: 260, h: 230, bezel: '#1a1a22', content: 'mono', rx: 30, led: '#3f6' },
    aux1: { type: 'dpad', color: '#c9c9cf' }, aux2: { type: 'ab', colors: ['#c9c9cf', '#c9c9cf'] },
    spine: { bg: '#1c264a' },
  },
  ngpc: {
    name: 'NEO GEO POCKET COLOR', short: 'NGPC', body: dark('#c9ccd4', '#aeb2bc', '#8a8f9a'), texture: { type: 'none' },
    hero: { type: 'screen', w: 260, h: 230, bezel: '#1a1a22', content: 'color', rx: 30, led: '#3f6', label: 'COLOR', labelInk: '#f7b210' },
    aux1: { type: 'dpad', color: '#2a2a2e' }, aux2: { type: 'ab', colors: ['#e3262e', '#2a63d6'] },
    spine: { bg: '#2a2a33' }, ink: '#2a2a33',
  },

  /* ---------------- Atari ---------------- */
  atari2600: {
    name: 'ATARI 2600', short: '2600', body: BLACK, texture: { type: 'ribs', color: '#2a2a2e' },
    hero: { type: 'slot', case: '#141416', cart: '#0f0f11', label: '#caa049', ribs: true },
    aux1: { type: 'wood' }, aux2: { type: 'switches', n: 4 },
    spine: { bg: '#5a3a1c', texture: 'wood' }, frame: '#caa049',
  },
  atari5200: {
    name: 'ATARI 5200', short: '5200', body: BLACK, texture: { type: 'ribs', color: '#2a2a2e' },
    hero: { type: 'keypad', case: '#141416', key: '#2c2c30', overlay: '#c9ccd4', keyInk: '#f2c94c', side: ['#e3262e', '#e3262e'] },
    aux1: { type: 'hstripes', colors: ['#c9ccd4', '#8f9298'], h: 5 }, aux2: { type: 'power', led: '#ff3b2a', volume: false },
    spine: { bg: '#121214', texture: 'ribs' }, frame: 'chrome',
  },
  atari7800: {
    name: 'ATARI 7800', short: '7800', body: BLACK, texture: { type: 'none' },
    hero: { type: 'slot', case: '#18181a', cart: '#1f1f22', label: '#2a63d6', band: '#9aa0aa', bandH: 14, ribs: true },
    aux1: { type: 'hstripes', colors: ['#9aa0aa', '#2a63d6', '#9aa0aa'], h: 4 }, aux2: { type: 'roundButtons', n: 2, color: '#9aa0aa', led: '#ff3b2a' },
    spine: { bg: '#121214' }, frame: 'chrome',
  },
  atarijaguar: {
    name: 'JAGUAR', short: 'JAG', body: BLACK, texture: { type: 'none' },
    hero: { type: 'keypad', case: '#141416', key: '#1d1d20', keyInk: '#e3262e', overlay: '#0b0b0c', mark: { text: '64-BIT', style: 'red', y: -168, size: 22 } },
    aux1: { type: 'hstripes', colors: ['#e3262e', '#e3262e'], h: 3 }, aux2: { type: 'ab', colors: ['#2a2a2e', '#2a2a2e'], pill: '#e3262e' },
    spine: { bg: '#0f0f11' }, ink: '#ff3b3b', frame: '#e3262e',
  },
  atari800: {
    name: 'ATARI 800', short: '800', body: BEIGE, texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#e2d8c0', key: '#4a3a2a', fkeys: { n: 5, color: '#e3a21a' }, deck: '#6b5a44' },
    aux1: { type: 'hstripes', colors: ['#4a3a2a', '#e3a21a'], h: 4 }, aux2: { type: 'ports', n: 2, color: '#6b5a44' },
    spine: { bg: '#5a4a38' }, ink: '#4a3a2a',
  },
  atarist: {
    name: 'ATARI ST', short: 'ST', body: dark('#d9d9d6', '#c6c6c2', '#a9a9a4'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#d9d9d6', key: '#bdbdb8', fkeys: { n: 10, color: '#a9a9a4' }, deck: '#9a9a96' },
    aux1: { type: 'grille' }, aux2: { type: 'leds', colors: ['#3f6', '#ff3b2a'] },
    spine: { bg: '#4a4a4e' }, ink: '#2a2a2e',
  },
  lynx: {
    name: 'LYNX', short: 'LYNX', body: BLACK, texture: { type: 'none' },
    hero: { type: 'screen', w: 320, h: 200, bezel: '#0f0f11', body: '#1d1d20', content: 'color', rx: 50, pad: 70, top: 22, bottom: 22, led: '#3f6', pal: ['#ffb070', '#ffe08a', '#d04a3a', '#3a1a2a'] },
    aux1: { type: 'dpad', color: '#2a2a2e' }, aux2: { type: 'ab', colors: ['#3a3a40', '#3a3a40'], pill: '#f26a21' },
    spine: { bg: '#121214' }, frame: '#f26a21',
  },

  /* ---------------- Autres consoles ---------------- */
  '3do': {
    name: '3DO', short: '3DO', body: BLACK, texture: { type: 'none' },
    hero: { type: 'disc', base: '#111113', lid: '#26262a', hub: '#1a1a1c', mark: { text: '3D', style: 'gold', y: -62, size: 28 }, arc: { text: 'INTERACTIVE MULTIPLAYER', color: '#c19528' } },
    aux1: { type: 'vents' }, aux2: { type: 'leds', colors: ['#3f6', '#f7b210'] },
    spine: { bg: '#101012' }, frame: 'gold',
  },
  cdi: {
    name: 'CD-i', short: 'CD-i', body: dark('#3a3a3f', '#26262a', '#161618'), texture: { type: 'none' },
    hero: { type: 'disc', base: '#1d1d21', lid: '#33333a', hub: '#26262a', arc: { text: 'COMPACT DISC INTERACTIVE', color: '#8fa0d8' } },
    aux1: { type: 'vents' }, aux2: { type: 'leds', colors: ['#3f6'] },
    spine: { bg: '#18181b' },
  },
  amigacd32: {
    name: 'AMIGA CD32', short: 'CD32', body: dark('#3a3a3f', '#2a2a2e', '#18181a'), texture: { type: 'none' },
    hero: { type: 'disc', base: '#1d1d21', lid: '#3a3a40', hub: '#2a2a2e', arc: { text: '32-BIT  CD  GAME SYSTEM', color: '#e3262e' } },
    aux1: { type: 'boing' }, aux2: { type: 'leds', colors: ['#3f6', '#ff3b2a'] },
    spine: { bg: '#18181b' },
  },
  amigacdtv: {
    name: 'AMIGA CDTV', short: 'CDTV', body: BLACK, texture: { type: 'ribs', color: '#26262a' },
    hero: { type: 'disk', case: '#141416', media: '#2a2a2e', shutter: '#9aa0aa', led: '#3f6' },
    aux1: { type: 'boing' }, aux2: { type: 'leds', colors: ['#3f6', '#ff3b2a'] },
    spine: { bg: '#121214' },
  },
  xbox: {
    name: 'XBOX', short: 'XBOX', body: BLACK, texture: { type: 'carbon' },
    hero: { type: 'disc', base: '#141416', lid: '#24242a', hub: false, rings: false, jewel: '#2fbf2f', glow: '#2fbf2f' },
    aux1: { type: 'vents' }, aux2: { type: 'roundButtons', n: 2, color: '#3a3a40', led: '#2fbf2f' },
    spine: { bg: '#101012', texture: 'carbon' }, ink: '#7dff7d', frame: '#2fbf2f',
  },
  channelf: {
    name: 'CHANNEL F', short: 'CH F', body: BLACK, texture: { type: 'none' },
    hero: { type: 'slot', case: '#1b1b1d', cart: '#f2c21b', label: '#e3262e', ribs: true },
    aux1: { type: 'wood' }, aux2: { type: 'roundButtons', n: 4, color: '#e9e9e5' },
    spine: { bg: '#5a3a1c', texture: 'wood' }, frame: '#caa049',
  },
  colecovision: {
    name: 'COLECOVISION', short: 'COLECO', body: BLACK, texture: { type: 'ribs', color: '#26262a' },
    hero: { type: 'keypad', case: '#141416', key: '#2c2c30', overlay: '#3a3a40', side: ['#e3262e', '#e3262e'] },
    aux1: { type: 'hstripes', colors: ['#9aa0aa', '#9aa0aa'], h: 3 }, aux2: { type: 'power', led: '#ff3b2a', volume: false },
    spine: { bg: '#121214' }, frame: 'chrome',
  },
  intellivision: {
    name: 'INTELLIVISION', short: 'INTV', body: dark('#8a6a3a', '#6b4f28', '#4a3518'), texture: { type: 'wood' },
    hero: { type: 'keypad', case: '#1b1b1d', key: '#c19528', keyInk: '#1b1b1d', overlay: '#d9c58c', disc: '#c19528' },
    aux1: { type: 'hstripes', colors: ['#c19528', '#c19528'], h: 4 }, aux2: { type: 'roundButtons', n: 2, color: '#c19528' },
    spine: { bg: '#2a2116' }, ink: '#f2d27a', frame: 'gold',
  },
  videopac: {
    name: 'VIDEOPAC', short: 'G7000', body: BLACK, texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#141416', key: '#2a4fb0', flat: true, rows: 4, cols: 12, space: false, deck: '#c9ccd4' },
    aux1: { type: 'hstripes', colors: ['#9aa0aa', '#9aa0aa'], h: 4 }, aux2: { type: 'power', led: '#ff3b2a', volume: false },
    spine: { bg: '#121214' }, frame: 'chrome',
  },
  videopacplus: {
    name: 'VIDEOPAC+', short: 'G7400', body: dark('#3a3a40', '#2a2a2e', '#18181a'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#2a2a2e', key: '#d9d9de', flat: true, rows: 4, cols: 12, space: false, deck: '#1a1a1d' },
    aux1: { type: 'hstripes', colors: ['#e3262e', '#2a63d6'], h: 4 }, aux2: { type: 'power', led: '#ff3b2a', volume: false },
    spine: { bg: '#18181a' }, frame: 'chrome',
  },
  vectrex: {
    name: 'VECTREX', short: 'VECTREX', body: BLACK, texture: { type: 'none' },
    hero: { type: 'crt', case: '#141416', content: 'vector', w: 260, h: 300 },
    aux1: { type: 'grille', color: '#2a2a2e' }, aux2: { type: 'ab', colors: ['#e3262e', '#e3262e'], pills: false },
    spine: { bg: '#0d0d0f' }, frame: 'chrome',
  },
  scv: {
    name: 'SUPER CASSETTE VISION', short: 'SCV', body: dark('#e85a4f', '#d43c33', '#a82820'), texture: { type: 'none' },
    hero: { type: 'slot', case: '#f2f0ea', cart: '#2b2b2e', label: '#2a63d6', ribs: true },
    aux1: { type: 'hstripes', colors: ['#f2f0ea', '#2b2b2e'], h: 5 }, aux2: { type: 'power', led: '#ff3b2a', panel: '#2b2b2e', volume: false },
    spine: { bg: '#2b2b2e' },
  },
  multivision: {
    name: 'MULTIVISION', short: 'MV', body: dark('#c98a45', '#a86c30', '#7a4a1a'), texture: { type: 'none' },
    hero: { type: 'slot', case: '#e9dcc0', cart: '#2b2b2e', label: '#e3262e' },
    aux1: { type: 'hstripes', colors: ['#2b2b2e', '#e9dcc0'], h: 5 }, aux2: { type: 'ab', colors: ['#2b2b2e', '#2b2b2e'] },
    spine: { bg: '#5a3a1c' },
  },
  supervision: {
    name: 'SUPERVISION', short: 'SV', body: dark('#8a8f99', '#6f747e', '#50545c'), texture: { type: 'none' },
    hero: { type: 'screen', w: 270, h: 240, bezel: '#202228', content: 'mono', led: '#ff3b2a', pal: ['#c8d0b8', '#a0a890', '#505848', '#20281c'] },
    aux1: { type: 'dpad', color: '#202228' }, aux2: { type: 'ab', colors: ['#e3262e', '#e3262e'] },
    spine: { bg: '#2a2c33' },
  },
  wonderswan: {
    name: 'WONDERSWAN', short: 'WS', body: dark('#e9e9ec', '#d6d6db', '#b9b9c0'), texture: { type: 'none' },
    hero: { type: 'screen', w: 320, h: 200, bezel: '#2a2c34', content: 'mono', pad: 60, top: 24, bottom: 24, rx: 30 },
    aux1: { type: 'dpad', color: '#3a3c44' }, aux2: { type: 'ab', colors: ['#3a3c44', '#3a3c44'] },
    spine: { bg: '#3a3c44' }, ink: '#2a2c34',
  },
  wonderswancolor: {
    name: 'WONDERSWAN COLOR', short: 'WSC', body: dark('#4a8fd6', '#2f6fbf', '#1f4f94'), texture: { type: 'dots', color: '#fff', opacity: .12 },
    hero: { type: 'screen', w: 320, h: 200, bezel: '#1a2232', content: 'color', pad: 60, top: 24, bottom: 24, rx: 30 },
    aux1: { type: 'dpad', color: '#1a2232' }, aux2: { type: 'ab', colors: ['#1a2232', '#1a2232'] },
    spine: { bg: '#1f4f94' },
  },
  megaduck: {
    name: 'MEGA DUCK', short: 'DUCK', body: dark('#3f3f45', '#2e2e33', '#1c1c20'), texture: { type: 'none' },
    hero: { type: 'screen', w: 280, h: 240, bezel: '#1a1a1d', content: 'dmg', led: '#ff3b2a', label: 'DUCK', labelInk: '#f5c61b' },
    aux1: { type: 'dpad', color: '#18181b' }, aux2: { type: 'ab', colors: ['#f5c61b', '#f5c61b'] },
    spine: { bg: '#18181b' }, ink: '#f5c61b',
  },
  pcv2: {
    name: 'POCKET CHALLENGE V2', short: 'PCV2', body: dark('#f2f2ef', '#dededa', '#c2c2bd'), texture: { type: 'none' },
    hero: { type: 'screen', w: 320, h: 200, bezel: '#3a6fc8', content: 'mono', pad: 60, top: 24, bottom: 24, rx: 30 },
    aux1: { type: 'dpad', color: '#3a6fc8' }, aux2: { type: 'ab', colors: ['#f26a21', '#3fae4b'] },
    spine: { bg: '#3a6fc8' }, ink: '#2a4f94',
  },
  arduboy: {
    name: 'ARDUBOY', short: 'ARDU', body: dark('#2a2a2e', '#1b1b1e', '#0e0e10'), texture: { type: 'carbon' },
    hero: { type: 'screen', w: 290, h: 200, bezel: '#050506', body: '#c9ccd4', content: 'oled', rx: 14, pad: 40 },
    aux1: { type: 'dpad', color: '#c9ccd4' }, aux2: { type: 'ab', colors: ['#c9ccd4', '#c9ccd4'], pills: false },
    spine: { bg: '#121214' },
  },
  wasm4: {
    name: 'WASM-4', short: 'W4', body: dark('#3a3060', '#2a2248', '#1a1530'), texture: { type: 'grid', color: '#86c06c', opacity: .14 },
    hero: { type: 'screen', w: 260, h: 260, bezel: '#071821', content: 'dmg', pal: ['#e0f8cf', '#86c06c', '#306850', '#071821'], rx: 18 },
    aux1: { type: 'hstripes', colors: ['#e0f8cf', '#86c06c', '#306850'], h: 4 }, aux2: { type: 'ab', colors: ['#86c06c', '#306850'] },
    spine: { bg: '#1a1530' }, ink: '#e0f8cf', frame: '#86c06c',
  },
  lowresnx: {
    name: 'LOWRES NX', short: 'NX', body: dark('#3a5fd6', '#2a47b0', '#1a2f7a'), texture: { type: 'grid', color: '#8fb4ff', opacity: .14 },
    hero: { type: 'crt', case: '#e9e9ec', content: 'prompt', lines: ['LOWRES NX', 'READY', 'PRINT "HI"', '_'], ink: '#ffd84a', screen: '#1a2f7a' },
    aux1: { type: 'hstripes', colors: ['#ffd84a', '#ff6a8a', '#6fe0ff'], h: 4 }, aux2: { type: 'ab', colors: ['#ff6a8a', '#ffd84a'] },
    spine: { bg: '#1a2f7a' }, ink: '#ffd84a',
  },
  palm: {
    name: 'PALM OS', short: 'PALM', body: dark('#8a8f99', '#6f747e', '#50545c'), texture: { type: 'none' },
    hero: { type: 'screen', w: 240, h: 290, bezel: '#2a2c33', content: 'mono', rx: 20, pal: ['#b8c8a0', '#98a888', '#4a5a44', '#1c2a1a'], pad: 28, top: 28, bottom: 60 },
    aux1: { type: 'roundButtons', n: 4, color: '#3a3c44' }, aux2: { type: 'leds', colors: ['#3f6'] },
    spine: { bg: '#3a3c44' },
  },
  gx4000: {
    name: 'GX4000', short: 'GX', body: dark('#3a3a40', '#2a2a2e', '#18181a'), texture: { type: 'none' },
    hero: { type: 'slot', case: '#2a2a2e', cart: '#1b1b1d', label: '#e3262e', band: '#e3262e', bandH: 8 },
    aux1: { type: 'hstripes', colors: ['#e3262e', '#22a84a', '#2a63d6'], h: 4 }, aux2: { type: 'power', led: '#ff3b2a', volume: false },
    spine: { bg: '#18181a' }, frame: '#e3262e',
  },

  /* ---------------- Ordinateurs ---------------- */
  amiga500: null,
  amiga600: {
    name: 'AMIGA 600', short: 'A600', body: BEIGE, texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#e6dfcb', key: '#e9e3d2', fkeys: { n: 10, color: '#cfc7b0' }, deck: '#9a9280', special: [{ color: '#bdb5a0', at: [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]] }] },
    aux1: { type: 'boing' }, aux2: { type: 'leds', colors: ['#3f6', '#ff3b2a'] },
    spine: { bg: '#5a5446' }, ink: '#3a3528',
  },
  amiga1200: {
    name: 'AMIGA 1200', short: 'A1200', body: dark('#e0d8c2', '#cec5ac', '#b1a78c'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#ddd5bf', key: '#e9e3d2', fkeys: { n: 10, color: '#bdb5a0' }, deck: '#8f8774', alt: '#bdb5a0' },
    aux1: { type: 'boing' }, aux2: { type: 'leds', colors: ['#3f6', '#f7b210'] },
    spine: { bg: '#5a5446' }, ink: '#3a3528',
  },
  amstradcpc: {
    name: 'AMSTRAD CPC', short: 'CPC', body: dark('#42413c', '#36352f', '#24231f'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#36352f', key: '#2a2924', deck: '#1a1916', special: [{ color: '#4f8e3a', at: [[0, 12], [1, 12], [2, 12]] }, { color: '#bf0811', at: [[3, 12], [4, 12]] }, { color: '#2a63d6', at: [[0, 11], [1, 11], [2, 11]] }], fkeys: { n: 12, color: '#7aa678' } },
    aux1: { type: 'hstripes', colors: ['#bf0811', '#4f8e3a', '#2a63d6'], h: 5 }, aux2: { type: 'leds', colors: ['#bf0811'] },
    spine: { bg: '#24231f' },
  },
  apple2: {
    name: 'APPLE II', short: 'II', body: dark('#e2d6b8', '#cfc19f', '#ad9f7c'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#d9cba9', key: '#4a3a2a', deck: '#7a6a4f', rows: 4, cols: 12 },
    aux1: { type: 'stripes', colors: APPLE, w: 9, skew: 0 }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#4a3a2a' }, ink: '#4a3a2a',
  },
  apple2gs: {
    name: 'APPLE IIGS', short: 'IIGS', body: dark('#d4d4d0', '#bdbdb8', '#9f9f9a'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#cfcfca', key: '#e6e6e2', deck: '#8f8f8a', fkeys: { n: 8, color: '#bdbdb8' } },
    aux1: { type: 'stripes', colors: APPLE, w: 9, skew: 0 }, aux2: { type: 'leds', colors: ['#3f6'] },
    spine: { bg: '#4a4a4e' }, ink: '#3a3a3e',
  },
  bbcmicro: {
    name: 'BBC MICRO', short: 'BBC', body: BEIGE, texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#e2d8c0', key: '#1d1d20', fkeys: { n: 10, color: '#c4161c' }, deck: '#2a2a2e', special: [{ color: '#a5a07f', at: [[0, 0], [4, 0], [4, 1]] }] },
    aux1: { type: 'hstripes', colors: ['#c4161c', '#1d1d20'], h: 4 }, aux2: { type: 'leds', colors: ['#ff3b2a', '#ff3b2a', '#ff3b2a'] },
    spine: { bg: '#2a2a2e' }, ink: '#2a2a2e',
  },
  commodore64: {
    name: 'COMMODORE 64', short: 'C64', body: dark('#8a7e6a', '#776b57', '#5a4f3f'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#7a6e5a', key: '#3a3330', deck: '#292522', special: [{ color: '#c9b99a', at: [[0, 12], [1, 12], [2, 12], [3, 12]] }] },
    aux1: { type: 'stripes', colors: ['#c4161c', '#f6a01a', '#f7e017', '#22a84a', '#1e8fd6'], w: 9 }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#3a3330' }, ink: '#f2e6c9',
  },
  vic20: {
    name: 'VIC-20', short: 'VIC', body: BEIGE, texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#e2d8c0', key: '#5a4636', deck: '#3a2e24', special: [{ color: '#e9dfc6', at: [[0, 12], [1, 12], [2, 12], [3, 12]] }] },
    aux1: { type: 'stripes', colors: ['#c4161c', '#f6a01a', '#f7e017', '#22a84a', '#1e8fd6'], w: 9 }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#5a4636' }, ink: '#5a4636',
  },
  dos: {
    name: 'MS-DOS', short: 'DOS', body: BEIGE, texture: { type: 'vribs', color: '#c9bea3' },
    hero: { type: 'crt', case: '#e2d8c0', content: 'prompt', lines: ['C:\\>CD GAMES', 'C:\\GAMES>DIR', 'C:\\GAMES>_'], ink: '#c9c9c9', screen: '#0a0a0a', slot: true },
    aux1: { type: 'floppy' },
    aux2: { type: 'leds', colors: ['#3f6', '#f7b210'] },
    spine: { bg: '#3a3a3e' }, ink: '#3a3528',
  },
  dragon: {
    name: 'DRAGON 32', short: 'DRAGON', body: dark('#e2d8c0', '#cfc4a8', '#ada284'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#d9cfb6', key: '#1d1d20', deck: '#2a2a2e', special: [{ color: '#c4161c', at: [[4, 0], [4, 12]] }] },
    aux1: { type: 'hstripes', colors: ['#c4161c', '#c4161c'], h: 5 }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#c4161c' }, ink: '#3a3528',
  },
  elektronikabk: {
    name: 'ELEKTRONIKA BK', short: 'BK', body: dark('#3a3a3f', '#2a2a2e', '#18181a'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#2a2a2e', key: '#c9c9c4', deck: '#18181a', special: [{ color: '#c4161c', at: [[0, 0], [0, 12]] }], fkeys: { n: 6, color: '#8f8f8a' } },
    aux1: { type: 'hstripes', colors: ['#c4161c', '#c4161c'], h: 4 }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#18181a' },
  },
  macintosh: {
    name: 'MACINTOSH', short: 'MAC', body: BEIGE, texture: { type: 'none' },
    hero: { type: 'crt', case: '#e6dcc4', content: 'mac', slot: true, stripes: APPLE, w: 260, h: 300 },
    aux1: { type: 'vents', color: '#9a8f78' }, aux2: { type: 'stripes', colors: APPLE, w: 8, skew: 0 },
    spine: { bg: '#cfc4a8' }, ink: '#3a3528',
  },
  msx1: {
    name: 'MSX', short: 'MSX', body: BLACK, texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#1d1d20', key: '#2c2c30', deck: '#0e0e10', fkeys: { n: 5, color: '#3a5fd6' }, alt: '#55555c' },
    aux1: { type: 'slot2' }, aux2: { type: 'leds', colors: ['#ff3b2a', '#3f6'] },
    spine: { bg: '#121214' },
  },
  msx2: {
    name: 'MSX2', short: 'MSX2', body: dark('#c9c9c4', '#b5b5b0', '#95958f'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#bdbdb8', key: '#2c2c30', deck: '#4a4a4e', fkeys: { n: 5, color: '#c4161c' }, alt: '#6a6a70' },
    aux1: { type: 'hstripes', colors: ['#c4161c', '#2a2a2e'], h: 4 }, aux2: { type: 'leds', colors: ['#ff3b2a', '#3f6'] },
    spine: { bg: '#2a2a2e' }, ink: '#2a2a2e',
  },
  msxturbor: {
    name: 'MSX turbo R', short: 'turbo R', body: dark('#3a3a3f', '#2a2a2e', '#18181a'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#2a2a2e', key: '#d9d9d6', deck: '#18181a', fkeys: { n: 5, color: '#c4161c' }, alt: '#9a9a96', mark: { text: 'turbo R', style: 'red', y: -122, size: 18 } },
    aux1: { type: 'hstripes', colors: ['#c4161c', '#c4161c'], h: 4 }, aux2: { type: 'leds', colors: ['#ff3b2a', '#3f6', '#f7b210'] },
    spine: { bg: '#18181a' },
  },
  oricatmos: {
    name: 'ORIC ATMOS', short: 'ORIC', body: BLACK, texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#1b1b1d', key: '#2a2a2e', deck: '#c4161c', special: [{ color: '#c4161c', at: [[0, 0], [4, 0], [4, 12]] }] },
    aux1: { type: 'hstripes', colors: ['#c4161c', '#c4161c'], h: 5 }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#c4161c' }, frame: '#c4161c',
  },
  pc88: {
    name: 'PC-8801', short: 'PC-88', body: BEIGE, texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#e2d8c0', key: '#d9cfb6', deck: '#8f8774', fkeys: { n: 10, color: '#3a3a3e' }, alt: '#bdb5a0' },
    aux1: { type: 'vents', color: '#9a8f78' }, aux2: { type: 'leds', colors: ['#3f6', '#ff3b2a'] },
    spine: { bg: '#5a5446' }, ink: '#3a3528',
  },
  pc98: {
    name: 'PC-9801', short: 'PC-98', body: dark('#e6e1d4', '#d6d0c0', '#b8b19e'), texture: { type: 'none' },
    hero: { type: 'crt', case: '#e2dccb', content: 'prompt', lines: ['A>DIR', ' GAME  EXE', 'A>GAME', '_'], ink: '#7ef', screen: '#000814', slot: true },
    aux1: { type: 'vents', color: '#9a8f78' }, aux2: { type: 'leds', colors: ['#3f6', '#f7b210'] },
    spine: { bg: '#5a5446' }, ink: '#3a3528',
  },
  samcoupe: {
    name: 'SAM COUPE', short: 'SAM', body: dark('#5a5a60', '#46464c', '#2e2e33'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#46464c', key: '#2a2a2e', deck: '#1a1a1d', round: true, fkeys: { n: 10, color: '#9a9aa0' } },
    aux1: { type: 'hstripes', colors: ['#e3262e', '#f5c61b', '#2a63d6'], h: 4 }, aux2: { type: 'leds', colors: ['#3f6'] },
    spine: { bg: '#2a2a2e' },
  },
  sharpx1: {
    name: 'SHARP X1', short: 'X1', body: dark('#c94040', '#a82828', '#7a1818'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#e9e9e5', key: '#2c2c30', deck: '#4a4a4e', fkeys: { n: 10, color: '#a82828' } },
    aux1: { type: 'vents', color: '#5a1010' }, aux2: { type: 'leds', colors: ['#3f6', '#ff3b2a'] },
    spine: { bg: '#2c2c30' },
  },
  sharpx68000: {
    name: 'X68000', short: 'X68K', body: dark('#3a3a3f', '#2a2a2e', '#18181a'), texture: { type: 'vribs', color: '#222226' },
    hero: { type: 'crt', case: '#2a2a2e', content: 'prompt', lines: ['Human68k', 'A>GAME.X', '_'], ink: '#9fe', screen: '#00101a', slot: true },
    aux1: { type: 'vents' }, aux2: { type: 'leds', colors: ['#3f6', '#ff3b2a', '#f7b210'] },
    spine: { bg: '#18181a', texture: 'vribs' },
  },
  spectravideo: {
    name: 'SPECTRAVIDEO', short: 'SVI', body: BLACK, texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#1b1b1d', key: '#2c2c30', deck: '#0e0e10', fkeys: { n: 5, color: '#c9c9c4' } },
    aux1: { type: 'hstripes', colors: ['#e3262e', '#f5c61b', '#2a63d6'], h: 4 }, aux2: { type: 'dpad', color: '#2a2a2e', right: true },
    spine: { bg: '#121214' },
  },
  thomson: {
    name: 'THOMSON', short: 'MO5', body: BLACK, texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#1b1b1d', key: '#3a3a40', deck: '#0e0e10', flat: true, special: [{ color: '#c4161c', at: [[0, 0], [0, 12], [4, 0]] }] },
    aux1: { type: 'hstripes', colors: ['#2a63d6', '#ffffff', '#c4161c'], h: 4 }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#c4161c' },
  },
  ti994a: {
    name: 'TI-99/4A', short: 'TI-99', body: dark('#c9ccd4', '#aeb2bc', '#8a8f9a'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#2a2a2e', key: '#3a3a40', deck: '#1a1a1d', fkeys: { n: 6, color: '#aeb2bc' } },
    aux1: { type: 'hstripes', colors: ['#2a2a2e', '#2a2a2e'], h: 4 }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#2a2a2e' }, ink: '#2a2a2e', frame: 'chrome',
  },
  trs80coco: {
    name: 'TRS-80 COCO', short: 'COCO', body: dark('#c9c9c4', '#b5b5b0', '#95958f'), texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#bdbdb8', key: '#2c2c30', deck: '#4a4a4e', special: [{ color: '#c4161c', at: [[4, 0]] }] },
    aux1: { type: 'hstripes', colors: ['#c4161c', '#2a63d6'], h: 4 }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#2c2c30' }, ink: '#2c2c30',
  },
  vg5000: {
    name: 'VG 5000', short: 'VG5K', body: BLACK, texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#1b1b1d', key: '#2c2c30', deck: '#0e0e10', special: [{ color: '#c4161c', at: [[0, 12], [1, 12], [4, 0]] }, { color: '#9aa0aa', at: [[2, 12], [3, 12]] }] },
    aux1: { type: 'hstripes', colors: ['#c4161c', '#9aa0aa'], h: 4 }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#121214' }, frame: 'chrome',
  },
  zx81: {
    name: 'ZX81', short: 'ZX81', body: BLACK, texture: { type: 'ribs', color: '#222226' },
    hero: { type: 'keyboard', case: '#141416', key: '#1d1d20', deck: '#0b0b0c', flat: true, rows: 4, cols: 10, space: false },
    aux1: { type: 'hstripes', colors: ['#c4161c'], h: 4 }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#121214', texture: 'ribs' }, ink: '#ff5a4a', frame: '#c4161c',
  },
  zxspectrum: {
    name: 'ZX SPECTRUM', short: 'ZX', body: BLACK, texture: { type: 'none' },
    hero: { type: 'keyboard', case: '#1b1b1d', key: '#5b585b', deck: '#0e0e10', round: true, rows: 4, cols: 10, space: false, stripe: SPECTRUM },
    aux1: { type: 'stripes', colors: SPECTRUM, w: 12 }, aux2: { type: 'leds', colors: ['#ff3b2a'] },
    spine: { bg: '#121214' }, frame: 'chrome',
  },

  /* ---------------- Moteurs ---------------- */
  scummvm: {
    name: 'SCUMMVM', short: 'SCUMM', body: dark('#3a2a5c', '#2a1f48', '#1a1230'), texture: { type: 'dots', color: '#7ef', opacity: .1 },
    hero: { type: 'crt', case: '#e2d8c0', content: 'scumm', slot: true },
    aux1: { type: 'hstripes', colors: ['#f7d26a', '#7ef', '#3a8'], h: 4 }, aux2: { type: 'leds', colors: ['#3f6'] },
    spine: { bg: '#1a1230' }, ink: '#f7d26a',
  },
  zmachine: {
    name: 'Z-MACHINE', short: 'Z', body: dark('#2a2a2e', '#1b1b1e', '#0e0e10'), texture: { type: 'none' },
    hero: { type: 'crt', case: '#3a3a40', content: 'prompt', lines: ['WEST OF HOUSE', 'You are standing', 'in an open field.', '>open mailbox_'], ink: '#ffb000', screen: '#120a00', fontSize: 15 },
    aux1: { type: 'vents' }, aux2: { type: 'leds', colors: ['#ffb000'] },
    spine: { bg: '#0e0e10' }, ink: '#ffb000', frame: '#ffb000',
  },
};
// nettoyage : clés vides
for (const k of Object.keys(module.exports)) if (!module.exports[k]) delete module.exports[k];
