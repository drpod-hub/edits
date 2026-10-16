// Scripted demo of PADS·12 for the trailers: records the screen (Playwright video)
// and the site's own audio output (tapped off the AudioContext destination), plus a
// sync marker so the two can be lined up exactly in ffmpeg.
// Usage: node trailer/capture.mjs [steam|tiktok]   (run trailer/make_demo_kit.py once first)
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FORMAT = process.argv[2] === 'tiktok' ? 'tiktok' : 'steam';
// steam: 16:9 with the device centred and free strips either side for captions.
// tiktok: 9:16 with the device below a caption band and nudged left, clear of TikTok's right-side buttons.
const CFG = {
  steam: { w: 1920, h: 1080, zoom: 1.25, css: '', top: 40, drumsY: 70 },
  tiktok: { w: 1080, h: 1920, zoom: 1.16, css: 'body { padding-top: 470px !important; } .device { margin-left: 34px !important; }', top: 0, drumsY: 490 },
}[FORMAT];
const DIR = path.join(HERE, 'build', FORMAT);
const KIT = path.join(HERE, 'build', 'Night Drive Kit.zip');
fs.mkdirSync(DIR, { recursive: true });
// the site source is an Artifact body (no doctype/head): wrap it like the claude.ai viewer does
fs.writeFileSync(DIR + '/page.html', '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>[hidden]{display:none!important}</style></head><body>'
  + fs.readFileSync(path.join(HERE, '../site/sampler.html'), 'utf8') + '</body></html>');
const JSZIP = process.env.JSZIP || '/opt/node-tools/node_modules/jszip/dist/jszip.min.js';
const b = await chromium.launch({
  executablePath: process.env.CHROMIUM || undefined,
  args: ['--autoplay-policy=no-user-gesture-required'],
});
const ctx = await b.newContext({
  viewport: { width: CFG.w, height: CFG.h }, deviceScaleFactor: 1,
  recordVideo: { dir: DIR + '/raw', size: { width: CFG.w, height: CFG.h } },
  locale: 'en-US',
});
await ctx.addInitScript(() => {
  try { localStorage.setItem('pads12-lang', 'en'); localStorage.setItem('pads12-game', JSON.stringify({ mode: 'free', introDone: true })); } catch (e) {}
  const orig = AudioNode.prototype.connect;
  AudioNode.prototype.connect = function (t, ...r) {
    const res = orig.call(this, t, ...r);
    try {
      if (t instanceof AudioDestinationNode && this.context.createMediaStreamDestination) {
        const c = this.context;
        if (!c.__tap) { c.__tap = c.createMediaStreamDestination(); window.__tap = c.__tap; }
        orig.call(this, c.__tap);
      }
    } catch (e) {}
    return res;
  };
});
const p = await ctx.newPage();
const errs = []; p.on('pageerror', (e) => errs.push(e.message));
await p.route('**/jszip.min.js', (r) => fs.existsSync(JSZIP) ? r.fulfill({ path: JSZIP, contentType: 'application/javascript' }) : r.continue());
await p.goto('file://' + DIR + '/page.html');
await p.waitForTimeout(2500);

// tap ripples so viewers can see where the "hand" goes; hide scrollbar
await p.addStyleTag({ content: `
  html { scrollbar-width: none; } ::-webkit-scrollbar { display: none; } .device { zoom: ${CFG.zoom}; } .help, .bgbar { display: none !important; } ${CFG.css}
  .tap { position: fixed; width: 54px; height: 54px; margin: -27px 0 0 -27px; border-radius: 50%;
    border: 3px solid rgba(255,255,255,.95); background: rgba(255,255,255,.18); pointer-events: none; z-index: 99999;
    animation: tap .45s ease-out forwards; }
  @keyframes tap { from { transform: scale(.4); opacity: 1; } to { transform: scale(1.5); opacity: 0; } }
  #sync { position: fixed; left: 0; bottom: 0; width: 40px; height: 40px; background: #ff00ff; z-index: 100000; }` });
await p.evaluate(() => {
  document.addEventListener('pointerdown', (e) => {
    const d = document.createElement('div'); d.className = 'tap';
    d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px';
    document.body.appendChild(d); setTimeout(() => d.remove(), 500);
  }, true);
});

const scrollTo = (y) => p.evaluate((y) => window.scrollTo({ top: y, behavior: 'smooth' }), y);
const offsetOf = (sel) => p.evaluate((s) => document.querySelector(s).getBoundingClientRect().top + scrollY, sel);
await p.evaluate((y) => window.scrollTo(0, y), CFG.top);
await p.waitForTimeout(400);

// t0: start audio tap + drum groove + sync marker in one go
const t0 = await p.evaluate(() => {
  const mr = new MediaRecorder(window.__tap.stream, { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 192000 });
  window.__chunks = []; mr.ondataavailable = (e) => e.data.size && window.__chunks.push(e.data);
  mr.start(100); window.__mr = mr;
  const s = document.createElement('div'); s.id = 'sync'; document.body.appendChild(s);
  setTimeout(() => s.remove(), 400);
  document.getElementById('seqPlay').click();
  return performance.now();
});
const start = Date.now();
const at = async (sec) => { const w = start + sec * 1000 - Date.now(); if (w > 0) await p.waitForTimeout(w); };
const beat = 60 / 104, e8 = beat / 2;
const marks = {};

// Scene 1 — sampler pads over the groove (3.0 → 9.6)
marks.pads = 3.0;
const hits = [11, 0, 3, 12, 11, 3, 12, 12, 11, 0, 3, 12, 11, 2, 3, 10];
const seq = [0, 2, 3, 4, 6, 7, 8, 10, 12, 14, 15, 16, 18, 19, 20, 22]; // in 8ths
for (let k = 0; k < hits.length; k++) {
  if (!hits[k]) continue;
  await at(3.2 + seq[k] * e8);
  await p.click('#pad' + hits[k], { delay: 20 });
}

// Scene 2 — import a whole kit (9.6 → 14.6)
await at(9.6); marks.kit = 9.6;
await p.hover('#kitBtn'); await at(10.2);
await p.click('#kitBtn', { trial: true });
await p.evaluate(() => { const r = document.getElementById('kitBtn').getBoundingClientRect(); document.dispatchEvent(new PointerEvent('pointerdown', { clientX: r.x + r.width / 2, clientY: r.y + r.height / 2 })); });
await p.setInputFiles('#kitFile', KIT);
await p.waitForTimeout(150); await scrollTo(CFG.top);
await at(12.0);
for (const k of [1, 2, 3, 4]) { await p.hover('#pad' + k); await p.waitForTimeout(120); }

// Scene 3 — organic drums + sequencer (14.6 → 22.0)
await at(14.6); marks.drums = 14.6;
await scrollTo(0); await p.click('#modeDrums');
await p.waitForTimeout(350);
await scrollTo((await offsetOf('#drumPads')) - CFG.drumsY);
await at(16.2);
for (const id of ['#step-4-12', '#step-4-13', '#step-5-14', '#step-5-15']) { await p.click(id); await p.waitForTimeout(260); }
await at(18.2);
for (const k of [1, 2, 1, 7]) { await p.click('#drum' + k); await p.waitForTimeout(e8 * 1000 - 40); }
await at(20.0); await scrollTo(0); await p.waitForTimeout(500);
await p.click('#phaserBtn'); await p.waitForTimeout(600); await p.click('#phaserBtn');

// Scene 4 — chords on the keys (22.0 → 31.2)
await at(22.0); marks.keys = 22.0;
await p.click('#modeKeys');
await p.selectOption('#instSel', 'pad');
await scrollTo(0);
const chords = [['#chord-m7', 'KeyN'], ['#chord-maj7', 'KeyV'], ['#chord-maj7', 'KeyZ'], ['#chord-maj', 'KeyB']];
let tc = 22.6;
for (const [chip, key] of chords) {
  await at(tc - 0.35); await p.click(chip);
  await at(tc); await p.keyboard.down(key);
  await at(tc + beat * 4 - 0.12); await p.keyboard.up(key);
  tc += beat * 4;
}

// Scene 5 — chop a sample over the groove (≈31.8 → 39.5)
await at(tc); marks.chop = tc;
await p.click('#modeChop');
await p.setInputFiles('#chopFile', path.join(HERE, 'build', 'Night Drive Loop.wav'));
await scrollTo(CFG.top);
await p.waitForTimeout(900);
const wave = await p.locator('#chopWave').boundingBox();
await p.mouse.click(wave.x + wave.width * 0.69, wave.y + wave.height * 0.6);
await p.waitForTimeout(350);
await p.mouse.move(wave.x + wave.width * 0.69, wave.y + 30);
await p.mouse.down(); await p.mouse.move(wave.x + wave.width * 0.72, wave.y + 30, { steps: 10 }); await p.mouse.up();
// finger-drum the slices on the beat grid of the running groove (it started at t0 + 0.06 s)
const bar = beat * 4, now = (Date.now() - start) / 1000;
const base = 0.06 + Math.ceil((now + 0.3 - 0.06) / bar) * bar;
const SLICE_KEYS = ['KeyA', 'KeyS', 'KeyD', 'KeyF', 'KeyQ', 'KeyW', 'KeyE', 'KeyR'];
const order = [0, 1, 2, 3, 0, 0, 2, 3, 4, 5, 6, 7, 4, 6, 1, 3];
for (let k = 0; k < order.length; k++) { await at(base + k * e8); await p.keyboard.press(SLICE_KEYS[order[k]]); }
tc = base + order.length * e8;
marks.end = tc;
await at(tc + 3.6);
marks.total = tc + 3.6;

const audioB64 = await p.evaluate(async () => {
  await new Promise((res) => { window.__mr.onstop = res; window.__mr.stop(); });
  const blob = new Blob(window.__chunks, { type: 'audio/webm' });
  const buf = new Uint8Array(await blob.arrayBuffer());
  let s = ''; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  return btoa(s);
});
fs.writeFileSync(DIR + '/audio.webm', Buffer.from(audioB64, 'base64'));
const video = p.video();
await ctx.close();
fs.renameSync(await video.path(), DIR + '/screen.webm');
fs.writeFileSync(DIR + '/marks.json', JSON.stringify(marks, null, 2));
console.log('marks', marks, 'errors', errs);
await b.close();
