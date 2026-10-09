/* =========================================================================
   Build Log - app logic (vanilla, no framework)
   - loads public/timeline.json  (episodes[] - each episode = one commit/pulse)
   - renders scroll-triggered branch timeline + commit graph
   - media: images inline (ImgBB), videos as a link card (Drive)
   - filters, search, lightbox
   ========================================================================= */

const state = { data: null, stage: 'all', q: '', view: 'timeline', showImages: true };
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const stages = () => (state.data && (state.data.stages || state.data.episodes)) || [];

init();

async function init() {
  try {
    const res = await fetch('./timeline.json', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    state.data = await res.json();
  } catch (e) {
    $('#timeline').innerHTML =
      '<div class="empty">Could not load <code>timeline.json</code> &mdash; ' + esc(e.message) + '</div>';
    return;
  }
  hydrateMeta();
  buildChips();
  render();
  wireControls();
  initReveal();
  initProgress();
}

function flatten() {
  const out = [];
  for (const st of stages()) {
    for (const c of st.commits || []) out.push({ ...c, _stage: st.id, _stageName: st.name, _epTs: st.timestamp });
  }
  return out;
}

function hydrateMeta() {
  const g = state.data.github || {};
  const repo = g.repo || 'REPO';
  $('#repoName').textContent = repo;
  $('#repoLink').href = `https://github.com/${g.user || 'ZFNO'}/${repo}`;
  $('#repoAuthor').textContent = state.data.author || 'Mark Ong';
  $('#repoBranch').textContent = g.branch || 'main';
  const all = flatten();
  $('#heroCount').textContent = all.length;
  if (state.data.updated_at) $('#repoLast').textContent = fmt(state.data.updated_at);
}

function fmt(iso) {
  try { const d = new Date(iso); return d.toLocaleString(); } catch { return iso; }
}

function buildChips() {
  const chips = $('#stageChips');
  const mk = (id, label) => {
    const b = document.createElement('button');
    b.className = 'chip' + (id === 'all' ? ' active' : '');
    b.dataset.stage = id;
    b.textContent = label;
    b.onclick = () => { state.stage = id; $$('.chip').forEach(c => c.classList.toggle('active', c === b)); render(); };
    return b;
  };
  chips.appendChild(mk('all', 'All'));
  stages().forEach(s => chips.appendChild(mk(s.id, s.name || s.id)));
}

function matches(c) {
  if (state.stage !== 'all' && c._stage !== state.stage) return false;
  if (!state.q) return true;
  const media = (c.media || []).map(m => m.name + ' ' + m.url).join(' ');
  const hay = [c.title, c.body, c.sha, c.branch, c._stageName, media, (c.tags || []).join(' ')].join(' ').toLowerCase();
  return hay.includes(state.q);
}

function render() {
  if (state.view === 'graph') return renderGraph();
  const root = $('#timeline');
  root.hidden = false;
  $('#graph').hidden = true;
  root.innerHTML = '';
  root.appendChild(el('div', 'trunk'));
  const fill = el('div', 'trunk-fill'); fill.id = 'trunkFill'; root.appendChild(fill);

  let n = 0, shown = 0;
  stages().forEach((st, si) => {
    const commits = (st.commits || []).map(c => ({ ...c, _stage: st.id, _stageName: st.name })).filter(matches);
    if (!commits.length) return;
    shown += commits.length;
    const sec = document.createElement('section');
    sec.className = 'stage';
    sec.id = 'stage-' + st.id;
    sec.innerHTML = `<div class="stage-head">
        <span class="idx">${String(si + 1).padStart(2, '0')}</span>
        <span class="txt"><span class="name">${esc(st.name || st.id)}</span>
        <span class="meta">${esc(st.summary || '')}${st.manual ? ' &middot; manual note' : ''}</span></span>
      </div>`;
    commits.forEach(c => {
      const side = (c.side === 'left' || c.side === 'right') ? c.side : (n % 2 ? 'right' : 'left');
      n++;
      sec.appendChild(card(c, side));
    });
    root.appendChild(sec);
  });
  $('#empty').style.display = shown ? 'none' : 'block';
  $('#stat').innerHTML = `<b>${shown}</b> / ${flatten().length} entries`;
  initReveal();
}

function el(tag, cls) { const e = document.createElement(tag); if (cls) e.className = cls; return e; }

function card(c, side) {
  const wrap = el('article', 'tl-item ' + side);

  const media = state.showImages ? renderMedia(c.media || c.images, c.title) : '';
  const tags = (c.tags || []).length
    ? `<div class="tags">${c.tags.map(t => `<span class="tag">${esc(t)}</span>`).join('')}</div>` : '';
  const created = (c.files || []).filter(f => f.status === 'added' || f.status === 'created').length;
  const stat = c.stats && (c.stats.additions || c.stats.deletions)
    ? `<span class="dstat"><i class="add">+${c.stats.additions || 0}</i> <i class="del">-${c.stats.deletions || 0}</i></span>` : '';
  const meta = (c.files || []).length
    ? `<div class="files">${(c.files || []).length} file${c.files.length > 1 ? 's' : ''} changed${created ? ` &middot; ${created} created` : ''} ${stat}</div>` : '';
  const link = c.link ? `<a class="link" href="${esc(c.link)}" target="_blank" rel="noopener">view commit &rarr;</a>` : '';
  const branch = c.branch ? `<span class="branch">${esc(c.branch)}</span>` : '';
  const sha = c.sha ? esc(c.sha.slice(0, 7)) : 'note';

  wrap.innerHTML = `
    <span class="node"></span>
    <div class="card">
      <div class="head"><span class="sha">${sha}</span><span class="when">${esc(c.date || '')}${c.time ? ' &middot; ' + esc(c.time) : ''}</span></div>
      ${branch}
      <h3>${esc(c.title || '')}</h3>
      ${c.body ? `<p>${esc(c.body)}</p>` : ''}
      ${meta}${tags}${media}${link}
    </div>`;
  return wrap;
}

function renderMedia(media, title) {
  if (!media || !media.length) return '';
  const items = media.map(m => {
    const url = typeof m === 'string' ? m : m.url;
    const type = typeof m === 'string' ? 'image' : (m.type || 'image');
    if (!url) return '';
    if (type === 'video') {
      return `<a class="vid" href="${esc(url)}" target="_blank" rel="noopener" title="${esc((m.name) || title)}">
                <span class="play">&#9654;</span><span class="vlabel">${esc((m.name) || 'video')}</span></a>`;
    }
    return `<img src="${esc(url)}" alt="${esc(title)}" loading="lazy" data-cap="${esc(title)}">`;
  }).join('');
  return `<div class="shots">${items}</div>`;
}

function renderGraph() {
  const root = $('#graph');
  $('#timeline').hidden = true;
  root.hidden = false;
  root.innerHTML = '';
  const all = flatten().filter(matches);
  all.forEach(c => {
    const row = el('div', 'g-row');
    row.innerHTML = `<span class="g-lane"><span class="g-node"></span></span>
      <span class="g-hash">${c.sha ? esc(c.sha.slice(0, 7)) : 'note'}</span>
      <span class="g-date">${esc(c.date || '')} ${esc(c.time || '')}</span>
      <span class="g-msg">${esc(c.title || '')}</span>
      <span class="g-branch">${esc(c.branch || 'main')}</span>`;
    root.appendChild(row);
  });
  $('#empty').style.display = all.length ? 'none' : 'block';
  $('#stat').innerHTML = `<b>${all.length}</b> / ${flatten().length} entries`;
}

let observer;
function initReveal() {
  if (observer) observer.disconnect();
  observer = new IntersectionObserver((entries) => {
    entries.forEach(en => {
      if (en.isIntersecting) { en.target.classList.add('in'); observer.unobserve(en.target); }
    });
  }, { rootMargin: '0px 0px -12% 0px', threshold: 0.12 });
  $$('.tl-item').forEach(x => observer.observe(x));
}

function initProgress() {
  const bar = $('#progressBar');
  const onScroll = () => {
    const doc = document.documentElement;
    const pct = Math.min(1, doc.scrollTop / Math.max(1, doc.scrollHeight - doc.clientHeight));
    bar.style.width = (pct * 100) + '%';
    const tf = $('#trunkFill'), tl = $('#timeline');
    if (tf && tl) {
      const r = tl.getBoundingClientRect();
      const v = Math.min(1, Math.max(0, (window.innerHeight * 0.5 - r.top) / Math.max(1, r.height)));
      tf.style.height = (v * 100) + '%';
    }
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  onScroll();
}

function wireControls() {
  $('#q').addEventListener('input', e => { state.q = e.target.value.trim().toLowerCase(); render(); });
  $('#imgToggle').addEventListener('change', e => { state.showImages = e.target.checked; render(); });
  $$('.viewtoggle .vt').forEach(b => b.addEventListener('click', () => {
    state.view = b.dataset.view;
    $$('.viewtoggle .vt').forEach(x => x.classList.toggle('active', x === b));
    render();
  }));
  $('#navToggle').addEventListener('click', () => $('.nav').classList.toggle('open'));

  const lb = $('#lightbox');
  document.addEventListener('click', e => {
    if (e.target.matches('.shots img')) {
      $('#lbImg').src = e.target.src;
      $('#lbCap').textContent = e.target.dataset.cap || '';
      lb.classList.add('open'); lb.setAttribute('aria-hidden', 'false');
    }
  });
  const close = () => { lb.classList.remove('open'); lb.setAttribute('aria-hidden', 'true'); };
  $('#lbClose').addEventListener('click', close);
  lb.addEventListener('click', e => { if (e.target === lb) close(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
}

function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m])); }
