let DATA = null;

const $ = (s) => document.querySelector(s);
const fmt$ = (n) => (n == null ? 'no price' : '$' + n.toLocaleString());
const ago = (ts) => {
  if (!ts) return 'never';
  const m = Math.floor((Date.now() - ts) / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m} min ago`;
  if (m < 48 * 60) return `${Math.floor(m / 60)} h ago`;
  return `${Math.floor(m / 1440)} d ago`;
};
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');

async function load() {
  const r = await fetch('/api/listings');
  DATA = await r.json();
  const srcSel = $('#f-source');
  const cur = srcSel.value;
  srcSel.innerHTML = '<option value="">all</option>' +
    DATA.sources.map((s) => `<option value="${s.source}">${esc(s.label)}</option>`).join('');
  srcSel.value = cur;
  render();
}

function visible() {
  const donorMode = $('#f-donor').checked;
  const fPrice = parseInt($('#f-price').value, 10) || null;
  const fDist = parseInt($('#f-dist').value, 10) || null;
  const fYear = $('#f-year').value;
  const fTurbo = $('#f-turbo').value;
  const fSource = $('#f-source').value;
  const showGone = $('#f-gone').checked;
  const favOnly = $('#f-fav').checked;
  const showHidden = $('#f-hidden').checked;

  let rows = DATA.listings.filter((l) => {
    if (!showHidden && l.hidden) return false;
    if (favOnly && !l.favorite) return false;
    if (!showGone && l.status === 'gone') return false;
    if (fSource && l.source !== fSource) return false;
    if (fPrice && l.price != null && l.price > fPrice) return false;
    if (fDist && (l.distance_mi == null || l.distance_mi > fDist)) return false;
    if (fYear === 'unknown' && l.year != null) return false;
    if (fYear && fYear !== 'unknown' && l.year !== parseInt(fYear, 10)) return false;
    if (!donorMode) {
      if (fTurbo === 'default' && l.turbo_status === 'non_turbo') return false;
      if (fTurbo === 'confirmed' && l.turbo_status !== 'confirmed') return false;
    }
    return true;
  });

  const sort = $('#f-sort').value;
  if (sort === 'price') rows.sort((a, b) => (a.price ?? 9e9) - (b.price ?? 9e9));
  else if (sort === 'distance') rows.sort((a, b) => (a.distance_mi ?? 9e9) - (b.distance_mi ?? 9e9));
  else if (sort === 'donor' || (donorMode && sort === 'newest')) rows.sort((a, b) => b.donor_score - a.donor_score);
  else rows.sort((a, b) => b.first_seen - a.first_seen);
  return rows;
}

function cardHtml(l) {
  const isNew = l.first_seen > DATA.newSince && l.status === 'active';
  const drop = l.prev_price != null && l.price != null && l.price < l.prev_price;
  const rise = l.prev_price != null && l.price != null && l.price > l.prev_price;
  const src = DATA.sources.find((s) => s.source === l.source);
  const donorMode = $('#f-donor').checked;
  const tierColor = { great: 'var(--green)', possible: 'var(--accent)', poor: 'var(--red)' }[l.donor_tier];
  const donorChip = donorMode
    ? `<span class="badge donor" style="border-color:${tierColor};color:${tierColor}">🔧 ${l.donor_score}</span>`
    : '';
  const donorReasons = donorMode
    ? `<div class="meta reasons">${l.donor_reasons.slice(0, 3).map((r) =>
        `<span>${r.delta > 0 ? '+' : ''}${r.delta} ${esc(r.text)}</span>`).join('<br>')}</div>`
    : '';
  const badges = [
    donorChip,
    isNew ? '<span class="badge new">NEW</span>' : '',
    l.year === 1991 ? '<span class="badge star">⭐ 1991</span>' : '',
    l.status === 'gone' ? '<span class="badge gone">GONE</span>' : '',
    l.is_auction ? '<span class="badge auction">AUCTION</span>' : '',
    l.turbo_status === 'confirmed' ? '<span class="badge">TURBO ✓</span>' : '',
    l.turbo_status === 'unconfirmed' ? '<span class="badge warn">⚠️ turbo unconfirmed</span>' : '',
    l.turbo_status === 'non_turbo' ? '<span class="badge">non-turbo</span>' : '',
    `<span class="badge">${esc(src ? src.label : l.source)}</span>`,
  ].join('');
  const where = [l.city, l.state].filter(Boolean).join(', ') || 'location unknown';
  const dist = l.distance_mi != null ? `${Math.round(l.distance_mi)} mi away` : '? mi';
  const img = l.photo_url
    ? `style="background-image:url('${esc(l.photo_url)}')"`
    : '';
  return `<div class="card ${l.status === 'gone' ? 'gone' : ''}">
    <a class="img" href="${esc(l.url)}" target="_blank" rel="noopener" ${img}>${l.photo_url ? '' : '🚗'}</a>
    <div class="body">
      <div class="badges">${badges}</div>
      <a class="title" href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.title)}</a>
      <div class="row">
        <span class="price">${fmt$(l.price)}
          ${drop ? `<span class="drop">📉 was ${fmt$(l.prev_price)}</span>` : ''}
          ${rise ? `<span class="rise">📈 was ${fmt$(l.prev_price)}</span>` : ''}</span>
        <span class="meta">${l.year ?? '??'}</span>
      </div>
      <div class="meta">${esc(where)} · ${dist}</div>
      <div class="meta">found ${ago(l.first_seen)}</div>
      ${donorReasons}
      <div class="actions">
        <button class="${l.favorite ? 'on' : ''}" onclick="flag(${l.id},'favorite',${l.favorite ? 0 : 1})">❤️</button>
        <button class="${l.hidden ? 'on' : ''}" onclick="flag(${l.id},'hidden',${l.hidden ? 0 : 1})">🚫</button>
      </div>
    </div>
  </div>`;
}

function render() {
  $('#f-turbo').disabled = $('#f-donor').checked;
  const rows = visible();
  const active = DATA.listings.filter((l) => l.status === 'active' && !l.hidden);
  const fresh = active.filter((l) => l.first_seen > DATA.newSince);
  $('#counts').innerHTML = `<b>${active.length}</b> active · <b>${fresh.length}</b> new since last visit`;
  $('#cards').innerHTML = rows.length
    ? rows.map(cardHtml).join('')
    : '<div class="empty">Nothing matches these filters yet. The scanners are out hunting — check back soon.</div>';

  $('#tier2').innerHTML = DATA.tier2.map((t) => `<div class="t2">
      <a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.label)} ↗</a>
      <div class="when"><span>checked ${ago(t.lastChecked)}</span>
      <button onclick="checked('${esc(t.key)}')">mark checked</button></div>
    </div>`).join('');

  $('#status').innerHTML = DATA.sources.map((s) => {
    let stat;
    if (s.demoted) stat = `<span class="demoted">blocks robots — use links above${s.manualUrl ? ` (<a href="${esc(s.manualUrl)}" target="_blank" rel="noopener" style="color:var(--new)">search ↗</a>)` : ''}</span>`;
    else if (s.lastError) stat = `<span class="err" title="${esc(s.lastError)}">problem · last good ${ago(s.lastOk)}</span>`;
    else stat = `<span class="ok">✓ ${ago(s.lastOk)}</span>`;
    return `<div class="src"><span>${esc(s.label)}</span>${stat}</div>`;
  }).join('');
}

async function flag(id, field, value) {
  await fetch(`/api/listings/${id}/flag`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ field, value: !!value }),
  });
  const l = DATA.listings.find((x) => x.id === id);
  if (l) l[field] = value;
  render();
}

async function checked(key) {
  await fetch(`/api/tier2/${key}/checked`, { method: 'POST' });
  const t = DATA.tier2.find((x) => x.key === key);
  if (t) t.lastChecked = Date.now();
  render();
}

document.querySelectorAll('#filters input, #filters select')
  .forEach((el) => el.addEventListener('change', render));
load();
setInterval(load, 5 * 60e3); // refresh data every 5 min while the tab is open
