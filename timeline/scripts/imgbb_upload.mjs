/**
 * imgbb_upload.mjs
 * Uploads an image to ImgBB and (optionally) attaches the returned URL to a
 * commit in public/timeline.json.
 *
 *   node scripts/imgbb_upload.mjs ./shot.png
 *   node scripts/imgbb_upload.mjs ./shot.png --sha a1b2c3d
 *
 * Reads the API key from the environment variable: IMGBB_API_KEY
 * (also accepts IMGBB_API_KEY_old as a fallback).
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, basename } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const DATA = join(here, '..', 'public', 'timeline.json');

const KEY = process.env.IMGBB_API_KEY || process.env.IMGBB_API_KEY_old;
if (!KEY) { console.error('Missing env var IMGBB_API_KEY'); process.exit(1); }

const file = process.argv[2];
if (!file) { console.error('Usage: node scripts/imgbb_upload.mjs <image> [--sha <sha>]'); process.exit(1); }
const shaArg = (process.argv.find((a, i) => process.argv[i - 1] === '--sha')) || '';

const b64 = readFileSync(file).toString('base64');
const form = new FormData();
form.append('image', b64);
form.append('name', basename(file));

const res = await fetch(`https://api.imgbb.com/1/upload?key=${KEY}`, { method: 'POST', body: form });
const json = await res.json();
if (!json.success) { console.error('Upload failed:', JSON.stringify(json, null, 2)); process.exit(1); }

const url = json.data.display_url || json.data.url;
console.log('Uploaded:', url);

if (shaArg) {
  const data = JSON.parse(readFileSync(DATA, 'utf8'));
  let hit = false;
  for (const st of data.stages || []) for (const c of st.commits || []) {
    if (c.sha.startsWith(shaArg)) { (c.images ||= []).push(url); hit = true; }
  }
  if (hit) { writeFileSync(DATA, JSON.stringify(data, null, 2) + '\n'); console.log('Attached to commit', shaArg); }
  else console.warn('No commit matched sha', shaArg);
}
