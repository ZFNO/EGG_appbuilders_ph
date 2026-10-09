/**
 * fetch_repo.mjs
 * Pulls commits from GitHub for the repo configured in public/timeline.json
 * and merges them into the data file, grouped into daily stages.
 *
 *   node scripts/fetch_repo.mjs                 # uses meta from public/timeline.json
 *   node scripts/fetch_repo.mjs --repo user/name --branch main
 *   GITHUB_TOKEN=... node scripts/fetch_repo.mjs   # optional, raises rate limit
 *
 * No dependencies. Public repos work without a token.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const DATA = join(here, '..', 'public', 'timeline.json');

const args = Object.fromEntries(
  process.argv.slice(2).join(' ').matchAll(/--(\w+)(?:\s+(\S+))?/g).map(m => [m[1], m[2] ?? true])
);

const data = JSON.parse(readFileSync(DATA, 'utf8'));
const user = (args.repo && String(args.repo).split('/')[0]) || data.github?.user || 'ZFNO';
const repo = (args.repo && String(args.repo).split('/')[1]) || data.github?.repo;
const branch = args.branch || data.github?.branch || 'main';

if (!repo || repo === 'REPO_NAME_HERE') {
  console.error('Set "github.repo" in public/timeline.json (or pass --repo user/name).');
  process.exit(1);
}

const headers = { 'Accept': 'application/vnd.github+json', 'User-Agent': 'build-log' };
if (process.env.GITHUB_TOKEN) headers['Authorization'] = 'Bearer ' + process.env.GITHUB_TOKEN;

const url = `https://api.github.com/repos/${user}/${repo}/commits?sha=${branch}&per_page=100`;
const res = await fetch(url, { headers });
if (!res.ok) { console.error('GitHub API error', res.status, await res.text()); process.exit(1); }
const commits = await res.json();

const existing = new Map();
for (const st of data.stages || []) for (const c of st.commits || []) existing.set(c.sha, c);

const byDay = new Map();
for (const raw of commits.reverse()) {
  const sha = raw.sha;
  const date = (raw.commit.author?.date || '').slice(0, 10);
  const time = (raw.commit.author?.date || '').slice(11, 16);
  const prev = existing.get(sha) || {};
  const item = {
    sha,
    date,
    time,
    branch,
    side: prev.side,
    title: raw.commit.message.split('\n')[0],
    body: raw.commit.message.split('\n').slice(1).join('\n').trim(),
    tags: prev.tags || [],
    images: prev.images || [],
    link: raw.html_url
  };
  const key = 'day-' + date;
  if (!byDay.has(key)) byDay.set(key, { id: key, name: date, summary: 'Commits on ' + date, commits: [] });
  byDay.get(key).commits.push(item);
}

data.github = { user, repo, branch };
data.stages = [...byDay.values()].sort((a, b) => a.id.localeCompare(b.id));
writeFileSync(DATA, JSON.stringify(data, null, 2) + '\n');
console.log(`Wrote ${commits.length} commits across ${data.stages.length} day(s) to public/timeline.json`);
