/* ModaRadar · app web (PWA) para el móvil. Sin dependencias. */
'use strict';

// ── utilidades ──────────────────────────────────────────────────────────────
const $ = (sel, el = document) => el.querySelector(sel);
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
const safeUrl = (u) => (/^https?:\/\//i.test(u || '') ? u : '#');
const fold = (s) => (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();
const store = {
  get(k, d) { try { const v = localStorage.getItem('mr:' + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('mr:' + k, JSON.stringify(v)); } catch { /* modo privado */ } },
};
const money = (v, cur = 'EUR') => {
  if (v === null || v === undefined) return '';
  try {
    const whole = Math.abs(v - Math.round(v)) < 0.005;
    return new Intl.NumberFormat('es-ES', { style: 'currency', currency: cur || 'EUR', minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: whole ? 0 : 2 }).format(v);
  } catch { return `${v.toFixed(2)} ${cur}`; }
};
const rtf = new Intl.RelativeTimeFormat('es', { numeric: 'auto' });
const rtfShort = new Intl.RelativeTimeFormat('es', { numeric: 'auto', style: 'short' });
function agoShort(iso) {  // "hace 5 min" (para la cabecera)
  const s = (new Date(iso).getTime() - Date.now()) / 1000;
  if (Number.isNaN(s)) return '';
  for (const [u, n] of [['day', 86400], ['hour', 3600], ['minute', 60]]) if (Math.abs(s) >= n) return rtfShort.format(Math.round(s / n), u);
  return 'ahora mismo';
}
function ago(iso) {
  if (!iso) return '';
  const s = (new Date(iso).getTime() - Date.now()) / 1000;
  if (Number.isNaN(s)) return '';
  const units = [['year', 31536000], ['month', 2592000], ['week', 604800], ['day', 86400], ['hour', 3600], ['minute', 60]];
  for (const [u, n] of units) if (Math.abs(s) >= n) return rtf.format(Math.round(s / n), u);
  return 'ahora mismo';
}
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

const CATS = [['ropa', 'Ropa'], ['calzado', 'Calzado'], ['bolsos', 'Bolsos'], ['accesorios', 'Accesorios'], ['todo', 'Todo']];
const PRENDAS = [
  ['vestidos', 'Vestidos', '👗'], ['abrigos', 'Abrigos, chaquetas y blazers', '🧥'], ['punto', 'Punto: jerséis y cárdigans', '🧶'],
  ['camisas', 'Camisas y blusas', '👚'], ['camisetas', 'Camisetas y tops', '👕'], ['faldas', 'Faldas', '💃'],
  ['pantalones', 'Pantalones', '👖'], ['vaqueros', 'Vaqueros', '👖'], ['shorts', 'Shorts y bermudas', '🩳'],
  ['sudaderas', 'Sudaderas', '🧥'], ['monos', 'Monos', '🩱'], ['conjuntos', 'Conjuntos', '✨'], ['bano', 'Baño', '👙'],
  ['lenceria', 'Lencería y pijamas', '🩲'], ['otras', 'Otras prendas', '🛍️'],
];
const PRENDA = Object.fromEntries(PRENDAS.map(([k, l, e]) => [k, { label: l, emoji: e }]));
const CAT_EMOJI = { calzado: '👠', bolsos: '👜', accesorios: '💍' };
const emojiOf = (p) => (p.category === 'ropa' ? (PRENDA[p.prenda] || PRENDA.otras).emoji : CAT_EMOJI[p.category] || '🛍️');
const EVENT = { new: ['🆕', 'Nuevo en outlet'], price_drop: ['💸', 'Rebajado aún más'], restock: ['🔁', 'Vuelve a haber stock'] };
const SORTS = [['nuevas', 'Más nuevas'], ['descuento', 'Mayor descuento'], ['precio', 'Más baratas']];
const PAGE = 40;
// sinónimos habituales al buscar
const SYN = {
  vestido: ['vestido', 'dress', 'robe'], falda: ['falda', 'skirt', 'jupe'], abrigo: ['abrigo', 'coat', 'manteau'],
  chaqueta: ['chaqueta', 'cazadora', 'jacket', 'blazer', 'americana'], jersey: ['jersey', 'jersei', 'sueter', 'punto', 'knit', 'cardigan'],
  pantalon: ['pantalon', 'trouser', 'pants'], vaquero: ['vaquero', 'jean', 'denim', 'tejano'], vaqueros: ['vaquero', 'jean', 'denim', 'tejano'],
  camisa: ['camisa', 'blusa', 'shirt'], blusa: ['blusa', 'camisa', 'blouse'], camiseta: ['camiseta', 't-shirt', 'top', 'tee'],
  piel: ['piel', 'cuero', 'leather'], cuero: ['cuero', 'piel', 'leather'], cachemir: ['cachemir', 'cashmere', 'cachemira'],
  bolso: ['bolso', 'bag', 'bandolera', 'shopper'], zapatos: ['zapato', 'zapatilla', 'bota', 'botin', 'sandalia', 'mocasin'],
};

// ── estado ──────────────────────────────────────────────────────────────────
const S = {
  tab: store.get('tab', 'novedades'),
  seg: store.get('seg', 'nuevas'),
  cat: store.get('cat', 'ropa'),
  prenda: store.get('prenda', 'todas'),
  shop: store.get('shop', 'todas'),
  sort: store.get('sort', 'nuevas'),
  stockOnly: store.get('stockOnly', true),
  mySize: store.get('mySize', false),
  big: store.get('big', false),
  sizes: store.get('sizes', []),
  dest: store.get('dest', ''),
  expanded: {},
  query: '',
  limit: PAGE,
  data: null,
};

// ── datos ───────────────────────────────────────────────────────────────────
async function getJSON(name) {
  const r = await fetch(`data/${name}?t=${Date.now()}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
  return r.json();
}

async function load() {
  const btn = $('#refresh');
  btn.classList.add('spin');
  try {
    const [status, products, events, stores, state] = await Promise.all(
      ['status.json', 'products.json', 'events.json', 'stores.json', 'state.json'].map((n) => getJSON(n).catch(() => ({}))),
    );
    const meta = Object.fromEntries((stores.stores || []).map((s) => [s.id, s]));
    const seededAt = Object.fromEntries(Object.entries(state.stores || {}).map(([k, v]) => [k, v.seeded_at]));
    const items = (products.items || []);
    S.data = {
      status, meta, seededAt, byId: new Map(items.map((p) => [p.id, p])),
      products: items, events: events.items || [], stores: stores.stores || [],
    };
    $('#updated').textContent = status.generated ? `Revisado ${agoShort(status.generated)}` : 'Sin datos todavía';
  } catch (e) {
    $('#updated').textContent = 'Sin conexión';
  } finally {
    btn.classList.remove('spin');
  }
  render();
}

// ── reglas ──────────────────────────────────────────────────────────────────
const shopName = (id) => S.data.meta[id]?.name || id;
const isDest = (id) => !!S.data.meta[id]?.destacada;
const COUNTRY = { ES: 'España', FR: 'Francia', IT: 'Italia', PT: 'Portugal', DE: 'Alemania' };
const flag = (cc) => (cc && cc.length === 2 ? String.fromCodePoint(...[...cc.toUpperCase()].map((c) => 0x1f1a5 + c.charCodeAt(0))) : '');
const umbral = () => S.data.status.umbral || { min: 40, dest: 30, chollo: 50, drop: 10 };
const storePaused = (id) => ((S.data.status.stores || []).find((s) => s.id === id) || {}).status === 'blocked';
const gone = (p) => !!(p.extra && p.extra.unseen);              // ya no está rebajada o se agotó del todo
const inStock = (p) => p.available === true && !gone(p);
const isHot = (p) => (p.pct || 0) >= umbral().chollo;
const dropped = (p) => p.prev_price && p.price && p.prev_price > p.price;

// tallas: «XS-S» → {XS, S} · «M/L» → {M, L} · talla única vale para todas
const ONE_SIZE = new Set(['U', 'TU', 'UNICA', 'UNICO', 'ONE SIZE', 'ONESIZE', 'OS', 'T.U.', 'TALLA UNICA', 'UNIQUE', 'TAILLE UNIQUE', 'UNI']);
function sizeTokens(label) {
  const f = fold(label).toUpperCase().trim();
  if (ONE_SIZE.has(f)) return new Set(['*']);
  return new Set(f.split(/[\s/\-–,()|+]+/).filter(Boolean));
}
const mySizes = () => (S.sizes || []).map((s) => fold(s).toUpperCase()).filter(Boolean);
function sizeFits(label) {
  const t = sizeTokens(label);
  return t.has('*') || mySizes().some((m) => t.has(m));
}
function fitsMe(p) {   // si la tienda no publica tallas (Zara), no se descarta
  if (!mySizes().length || !Array.isArray(p.sizes)) return true;
  return p.sizes.some(sizeFits);
}

function baseFilter(p, { cat = S.cat, prenda = S.prenda, shop = S.shop } = {}) {
  return !gone(p)
    && (cat === 'todo' || p.category === cat)
    && (prenda === 'todas' || cat !== 'ropa' || (p.prenda || 'otras') === prenda)
    && (shop === 'todas' || p.store === shop)
    && (!S.stockOnly || inStock(p))
    && (!S.mySize || fitsMe(p))
    && (!S.big || isHot(p));
}
const newKey = (p) => (p.first_seen === S.data.seededAt[p.store] ? '' : p.first_seen) || '';
function sortItems(list, how = S.sort) {
  const cmp = {
    nuevas: (a, b) => newKey(b).localeCompare(newKey(a)) || (b.pct || 0) - (a.pct || 0),
    descuento: (a, b) => (b.pct || 0) - (a.pct || 0) || (a.price ?? 1e9) - (b.price ?? 1e9),
    precio: (a, b) => (a.price ?? 1e9) - (b.price ?? 1e9) || (b.pct || 0) - (a.pct || 0),
  }[how] || (() => 0);
  return list.sort((a, b) => inStock(b) - inStock(a) || cmp(a, b));
}

// ── componentes ─────────────────────────────────────────────────────────────
function img(src, emoji, cls = 'pimg') {
  return src
    ? `<img class="${cls}" src="${esc(safeUrl(src))}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'${cls} ph',textContent:'${emoji}'}))">`
    : `<div class="${cls} ph">${emoji}</div>`;
}

const offPill = (p) => (p.pct ? `<span class="pill ${isHot(p) ? 'hot' : 'accent'}">−${p.pct} %</span>` : '');
const priceHTML = (p) => (p.price ? `<span class="price">${money(p.price, p.currency)}</span>${p.original ? `<s class="was">${money(p.original, p.currency)}</s>` : ''}` : '');

function sizesLine(p, max = 6) {
  if (!Array.isArray(p.sizes)) return p.category === 'ropa' ? '<span class="muted">Tallas: en su web</span>' : '';
  if (!p.sizes.length) return '<span class="muted">Sin tallas disponibles</span>';
  if (p.sizes.length === 1 && p.sizes[0] === 'Única') return '<span>Talla única</span>';
  const mine = mySizes().length;
  const list = p.sizes.slice(0, max).map((s) => (mine && sizeFits(s) ? `<b class="mine">${esc(s)}</b>` : esc(s))).join(' · ');
  return `<span>${list}${p.sizes.length > max ? ' …' : ''}</span>`;
}

function stockPill(p) {
  if (gone(p)) return '<span class="pill info" title="No aparece en la última revisión">Ya no está en outlet</span>';
  if (p.available === true && storePaused(p.store)) return '<span class="pill info">Sin confirmar</span>';
  if (p.available === true) return '<span class="pill ok">En stock</span>';
  if (p.available === false) return '<span class="pill no">Agotada</span>';
  return '';
}

function productCard(p) {
  const when = newKey(p);
  return `
  <article class="pcard tap${isHot(p) ? ' hot' : ''}" data-open="${esc(p.id)}" tabindex="0" aria-label="${esc(p.title)}">
    <div class="pmedia">${img(p.image, emojiOf(p))}
      ${p.pct ? `<span class="off${isHot(p) ? ' hot' : ''}">−${p.pct} %</span>` : ''}
      ${isDest(p.store) ? '<span class="star" title="Marca destacada">⭐</span>' : ''}
      ${!inStock(p) ? `<span class="sold">${gone(p) ? 'Ya no está' : 'Agotada'}</span>` : ''}
    </div>
    <div class="pbody">
      <div class="pshop">${esc(shopName(p.store))}${when ? ` · ${esc(agoShort(when))}` : ''}</div>
      <p class="ptitle">${esc(p.title)}</p>
      <div class="prices">${priceHTML(p)}</div>
      <div class="psizes">${dropped(p) ? `<span class="drop">💸 bajó de ${money(p.prev_price)}</span>` : sizesLine(p, 5)}</div>
    </div>
  </article>`;
}

const grid = (items) => `<div class="grid">${items.map(productCard).join('')}</div>`;
const moreBtn = (n) => (n > S.limit ? `<p style="text-align:center"><button class="btn ghost" data-more>Ver más (${n - S.limit})</button></p>` : '');

function eventCard(e) {
  const [icon, label] = EVENT[e.type] || ['•', e.type];
  const known = e.id && S.data.byId.has(e.id);
  return `
  <a class="card${known ? ' tap' : ''}" href="${esc(safeUrl(e.url))}" target="_blank" rel="noopener" ${known ? `data-open="${esc(e.id)}"` : ''}>
    ${img(e.image, emojiOf(e), 'thumb')}
    <div class="body">
      <div class="meta"><span class="pill ${e.type === 'restock' ? 'ok' : e.type === 'price_drop' ? 'warn' : 'accent'}">${icon} ${label}</span>${e.pct ? ` <span class="pill ${e.hot ? 'hot' : 'accent'}">−${e.pct} %</span>` : ''}${e.dest ? ' <span class="pill star-pill">⭐</span>' : ''} ${esc(ago(e.at))}</div>
      <p class="title" style="margin-top:4px">${esc(e.title)}</p>
      <div class="meta"><span class="price sm">${money(e.price, e.currency)}</span>${e.old_price ? `<s class="was">${money(e.old_price)}</s>` : e.original ? `<s class="was">${money(e.original)}</s>` : ''} · ${esc(shopName(e.store))}</div>
    </div>
  </a>`;
}

const segmented = (name, options, current) => `
  <div class="segmented" role="group">${options.map(([v, l]) => `<button data-${name}="${esc(v)}" aria-pressed="${v === current}">${esc(l)}</button>`).join('')}</div>`;

const empty = (title, text) => `<div class="empty"><b>${esc(title)}</b>${text}</div>`;

function shopSelect() {
  const shops = S.data.stores.filter((s) => s.items > 0 || s.id === S.shop);
  return `<select class="chip" data-shop aria-label="Tienda" ${S.shop !== 'todas' ? 'aria-pressed="true"' : ''}>
    <option value="todas">Todas las tiendas</option>
    ${shops.map((s) => `<option value="${esc(s.id)}" ${s.id === S.shop ? 'selected' : ''}>${s.destacada ? '⭐ ' : ''}${esc(s.name)}</option>`).join('')}
  </select>`;
}
function prendaSelect() {
  if (S.cat !== 'ropa') return '';
  const counts = {};
  for (const p of S.data.products) if (!gone(p) && p.category === 'ropa') counts[p.prenda || 'otras'] = (counts[p.prenda || 'otras'] || 0) + 1;
  return `<select class="chip" data-prenda aria-label="Tipo de prenda" ${S.prenda !== 'todas' ? 'aria-pressed="true"' : ''}>
    <option value="todas">Todas las prendas</option>
    ${PRENDAS.filter(([k]) => counts[k] || k === S.prenda).map(([k, l, e]) => `<option value="${k}" ${k === S.prenda ? 'selected' : ''}>${e} ${esc(l)}</option>`).join('')}
  </select>`;
}
const catChips = () => CATS.map(([v, l]) => `<button class="chip" data-cat="${esc(v)}" aria-pressed="${v === S.cat}">${esc(l)}</button>`).join('');
const sortSelect = () => `<select class="chip" data-sort aria-label="Ordenar">${SORTS.map(([v, l]) => `<option value="${v}" ${v === S.sort ? 'selected' : ''}>↕ ${esc(l)}</option>`).join('')}</select>`;
const stockChip = () => `<button class="chip" data-stock aria-pressed="${S.stockOnly}">Solo con stock</button>`;
const sizeChip = () => (mySizes().length
  ? `<button class="chip" data-mysize aria-pressed="${S.mySize}">Mi talla (${esc(S.sizes.join(', '))})</button>`
  : '<button class="chip" data-gosizes>＋ Mi talla</button>');
const bigChip = () => `<button class="chip" data-big aria-pressed="${S.big}">🔥 Desde −${umbral().chollo} %</button>`;

// ── vistas ──────────────────────────────────────────────────────────────────
function welcome() {
  const links = repoLinks();
  return `<h2 class="section">¡Hola! 👋</h2>
    <p class="lead">ModaRadar aún no ha revisado las tiendas. En cuanto lo haga verás aquí las prendas rebajadas de Zara, Brownie, Zadig&amp;Voltaire y el resto de tiendas.</p>
    <div class="panel"><b>Para empezar</b><ol>
      <li>En GitHub: <b>Actions → ModaRadar → Run workflow</b>${links ? ` (<a href="${esc(links.run)}" target="_blank" rel="noopener">abrir</a>)` : ''}.</li>
      <li>La primera pasada memoriza lo que ya está rebajado (sin avisos). A partir de ahí te avisa de cada rebaja nueva.</li>
      <li>Activa los avisos en la pestaña <b>Avisos</b>.</li>
    </ol></div>`;
}

const destNames = () => {
  const n = S.data.stores.filter((s) => s.destacada).map((s) => s.short || s.name);
  return n.length > 1 ? `${n.slice(0, -1).join(', ')} y ${n[n.length - 1]}` : (n[0] || 'las destacadas');
};
// tiendas con un umbral de aviso propio (p. ej. Polo Club desde −60 %)
const ownThr = () => S.data.stores.filter((s) => !s.destacada && s.thr != null && s.thr !== umbral().min)
  .map((s) => `; <b>${s.thr} %</b> en ${esc(s.name)}`).join('');

function viewNovedades() {
  const D = S.data;
  if (!D.status.generated) return welcome();
  const u = umbral();
  let html = `<h2 class="section">Novedades</h2>
    ${segmented('seg', [['nuevas', 'Rebajas'], ['chollos', `🔥 −${u.chollo} %`], ['bajadas', '💸 Bajadas']], S.seg)}`;

  if (S.seg === 'chollos') {
    const hot = sortItems(D.products.filter((p) => isHot(p) && baseFilter(p, { cat: 'todo', prenda: 'todas' })), 'descuento');
    html += `<p class="lead">Prendas rebajadas un <b>${u.chollo} % o más</b>. Te avisamos al momento y con prioridad de cada una nueva.</p>
      <div class="chips">${stockChip()} ${sizeChip()} ${shopSelect()}</div>`;
    html += hot.length ? grid(hot.slice(0, S.limit)) + moreBtn(hot.length)
      : empty(`Nada a −${u.chollo} % ahora mismo`, 'En cuanto una tienda rebaje una prenda a la mitad o más, aparecerá aquí y te llegará un aviso.');
    return html;
  }

  if (S.seg === 'bajadas') {
    const list = D.products.filter((p) => dropped(p) && baseFilter(p, { cat: 'todo', prenda: 'todas' }))
      .sort((a, b) => (1 - b.price / b.prev_price) - (1 - a.price / a.prev_price));
    html += `<p class="lead">Prendas que ya estaban rebajadas y <b>han bajado otra vez</b> (segundas rebajas, «last chance»…).</p>
      <div class="chips">${stockChip()} ${sizeChip()} ${shopSelect()}</div>`;
    html += list.length ? grid(list.slice(0, S.limit)) + moreBtn(list.length)
      : empty('Sin bajadas todavía', 'Cuando una prenda ya rebajada baje de precio otra vez, la verás aquí.');
    return html;
  }

  const items = sortItems(D.products.filter((p) => baseFilter(p)));
  const total = D.products.filter((p) => !gone(p)).length;
  html += `<p class="lead">${total} prendas rebajadas en ${D.stores.filter((s) => s.items > 0).length} tiendas. Te avisamos desde un <b>${u.min} %</b> de descuento (<b>${u.dest} %</b> en ${esc(destNames())}${ownThr()}).</p>
    <div class="chips">${catChips()}</div>
    <div class="chips">${prendaSelect()} ${shopSelect()} ${sortSelect()} ${stockChip()} ${sizeChip()} ${bigChip()}</div>`;
  html += items.length ? grid(items.slice(0, S.limit)) + moreBtn(items.length)
    : empty('Nada por aquí', 'Prueba con otra categoría, tienda o quita algún filtro.');
  return html;
}

function viewDestacadas() {
  const D = S.data;
  const dest = D.status.destacadas || D.stores.filter((s) => s.destacada).map((s) => ({ id: s.id, name: s.name, short: s.short || s.name }));
  let html = '<h2 class="section">Marcas destacadas</h2>';
  if (!dest.length) return html + empty('Ninguna marca destacada', 'Se marcan en config.toml con destacada = true.');
  if (!dest.some((f) => f.id === S.dest)) S.dest = dest[0].id;
  const m = D.meta[S.dest] || {};
  const st = (D.status.stores || []).find((s) => s.id === S.dest) || {};
  const all = D.products.filter((p) => p.store === S.dest && !gone(p));
  const items = all.filter((p) => (S.cat === 'todo' || p.category === S.cat) && (!S.stockOnly || inStock(p)) && (!S.mySize || fitsMe(p)) && (!S.big || isHot(p)));
  const maxPct = Math.max(0, ...all.map((p) => p.pct || 0));
  html += `${segmented('dest', dest.map((f) => [f.id, f.short || f.name]), S.dest)}`;
  html += all.length
    ? `<p class="lead"><b>${esc(m.name || S.dest)}</b>: ${all.length} prendas rebajadas, hasta <b>−${maxPct} %</b>${m.avg ? ` (−${m.avg} % de media)` : ''}. Te avisamos con prioridad de cada prenda nueva desde un <b>${umbral().dest} %</b>, de cada segunda rebaja y de las reposiciones.</p>`
    : `<p class="lead"><b>${esc(m.name || S.dest)}</b> no tiene prendas de mujer rebajadas ahora mismo. Lo vigilamos cada 15 minutos: en cuanto rebaje algo (Black Friday, rebajas, outlet…) te llega un aviso.</p>`;
  if (st.sections && st.sections.length) html += `<p class="muted" style="margin:-6px 0 10px;font-size:12.5px">Secciones vigiladas: ${st.sections.map(esc).join(' · ')}</p>`;
  html += `<div class="chips">${catChips()}</div><div class="chips">${stockChip()} ${sizeChip()} ${bigChip()}
      ${m.outlet_url ? `<a class="chip linkchip" href="${esc(safeUrl(m.outlet_url))}" target="_blank" rel="noopener">Abrir su outlet ↗</a>` : ''}</div>`;
  if (m.note) html += `<p class="note">${esc(m.note)}</p>`;
  const moves = D.events.filter((e) => e.store === S.dest).slice(0, 3);
  if (moves.length) html += `<h3 class="sub">Últimos avisos</h3><div class="list">${moves.map(eventCard).join('')}</div>`;
  if (!all.length) return html;
  const groups = new Map();
  for (const p of items) {
    const k = p.category === 'ropa' ? (p.prenda || 'otras') : p.category;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(p);
  }
  const order = [...PRENDAS.map(([k]) => k), 'calzado', 'bolsos', 'accesorios'];
  const label = (k) => (PRENDA[k] ? `${PRENDA[k].emoji} ${PRENDA[k].label}` : `${CAT_EMOJI[k] || ''} ${CATS.find(([c]) => c === k)?.[1] || k}`);
  let any = false;
  for (const k of order) {
    const list = groups.get(k);
    if (!list) continue;
    any = true;
    sortItems(list, 'descuento');
    const key = `${S.dest}:${k}`;
    const open = S.expanded[key];
    const best = list[0];
    html += `<h3 class="sub">${esc(label(k))} · ${list.length}</h3>
      <p class="kind-best">Hasta <b>−${best.pct} %</b>: desde ${money(Math.min(...list.filter(inStock).map((p) => p.price).concat([best.price])))}</p>
      ${grid(list.slice(0, open ? list.length : 4))}
      ${list.length > 4 && !open ? `<button class="btn ghost more-row" data-expand="${esc(key)}">Ver las ${list.length}</button>` : ''}`;
  }
  if (!any) html += empty('Nada con estos filtros', 'Prueba con «Todo» o quita «Solo con stock».');
  return html;
}

function viewBuscar() {
  return `<h2 class="section">Buscar en el outlet</h2>
    <p class="lead">Busca entre todas las prendas rebajadas de las tiendas vigiladas.</p>
    <label class="search">
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M10 3a7 7 0 0 1 5.6 11.2l5.1 5.1-1.4 1.4-5.1-5.1A7 7 0 1 1 10 3Zm0 2a5 5 0 1 0 0 10 5 5 0 0 0 0-10Z"/></svg>
      <input id="q" type="search" placeholder="p. ej. vestido negro, abrigo lana, piel…" value="${esc(S.query)}" autocomplete="off" enterkeyhint="search">
    </label>
    <div class="chips">${catChips()}</div>
    <div class="chips">${prendaSelect()} ${shopSelect()} ${stockChip()} ${sizeChip()} ${bigChip()}</div>
    <div id="results">${resultsHTML()}</div>`;
}

function resultsHTML() {
  const D = S.data;
  const q = S.query.trim();
  const terms = fold(q).split(/\s+/).filter(Boolean).map((w) => SYN[w] || [w]);
  const hits = D.products.filter((p) => baseFilter(p))
    .filter((p) => { const t = fold(`${p.title} ${shopName(p.store)} ${p.category === 'ropa' ? (PRENDA[p.prenda] || PRENDA.otras).label : p.category}`); return terms.every((alts) => alts.some((w) => t.includes(w))); });
  sortItems(hits, q ? 'descuento' : S.sort === 'nuevas' ? 'descuento' : S.sort);
  let html = `<h3 class="sub">${hits.length} prenda${hits.length === 1 ? '' : 's'}${q ? ` con «${esc(q)}»` : ''} · mayor descuento primero</h3>`;
  html += hits.length ? grid(hits.slice(0, S.limit)) + moreBtn(hits.length)
    : empty('Sin resultados', 'Prueba con menos palabras o quita algún filtro.');
  const outlets = D.stores.filter((s) => s.outlet_url);
  if (outlets.length) {
    html += `<h3 class="sub">Outlets de las tiendas</h3>
      <div class="quick">${outlets.map((s) => `<a href="${esc(safeUrl(s.outlet_url))}" target="_blank" rel="noopener"><span>${s.destacada ? '⭐ ' : ''}${esc(s.name)}<small>${s.items ? `${s.items} rebajadas` : 'sin rebajas ahora'}</small></span></a>`).join('')}</div>`;
  }
  return html;
}

function storeCard(s, statusById) {
  const st = statusById[s.id];
  const avg = s.avg ?? 0;
  const color = avg >= 45 ? 'var(--hot)' : avg >= 30 ? 'var(--accent)' : 'var(--info)';
  let statusTxt = '—';
  if (st) {
    const map = { ok: ['ok', 'Vigilando'], skipped: ['info', 'Sin configurar'], blocked: ['warn', 'En pausa'], error: ['no', 'Error'] };
    const [cls, l] = map[st.status] || ['info', st.status];
    statusTxt = `<span class="pill ${cls}">${l}</span>`;
  }
  const thr = s.thr ?? (s.destacada ? umbral().dest : umbral().min);
  return `<article class="store">
    <div class="store-head">
      <div class="ring" style="--v:${Math.min(100, avg * 1.4)};--ring-color:${color}" title="Descuento medio"><span>${s.avg != null ? `−${s.avg}%` : '–'}</span></div>
      <div><h4>${s.country && s.country !== 'ES' ? flag(s.country) + ' ' : ''}${esc(s.name)} ${s.destacada ? '<span class="pill star-pill">⭐ Destacada</span>' : ''}</h4>
        <div class="meta">${s.items ? `${s.items} prendas rebajadas${s.ropa != null && s.ropa !== s.items ? ` (${s.ropa} de ropa)` : ''}` : 'Sin rebajas ahora mismo'}${s.country && s.country !== 'ES' ? ` · envía desde ${esc(COUNTRY[s.country] || s.country)}` : ''}</div></div>
    </div>
    <dl class="facts">
      <div><dt>Descuento medio · máximo</dt><dd>${s.avg != null ? `−${s.avg} % · −${s.max} %` : '—'}</dd></div>
      <div><dt>🔥 Desde −${umbral().chollo} %</dt><dd>${s.big || 0}</dd></div>
      <div><dt>Te avisaría (desde −${thr} %)</dt><dd>${s.alert || 0}</dd></div>
      <div><dt>Nuevas esta semana</dt><dd>${s.week || 0}</dd></div>
      <div><dt>Estado</dt><dd>${statusTxt}</dd></div>
    </dl>
    ${s.note ? `<p class="note">${esc(s.note)}</p>` : ''}
    <div class="actions">
      ${s.outlet_url ? `<a class="btn" href="${esc(safeUrl(s.outlet_url))}" target="_blank" rel="noopener">Ver outlet</a>` : ''}
      <a class="btn ghost" href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener">Abrir tienda</a>
      ${s.items ? `<button class="btn ghost" data-goshop="${esc(s.id)}">Ver sus ${s.items} en la app</button>` : ''}
    </div>
  </article>`;
}

// marcas muy buscadas en España que no se pueden vigilar (comprobado en noviembre de 2026):
// bloquean el acceso automático a su catálogo o solo lo cargan dentro del navegador
const OTHER_SHOPS = [
  ['Shein', 'https://es.shein.com/', 'Pide un captcha a los programas automáticos.'],
  ['Mango y Mango Outlet', 'https://www.mangooutlet.com/', 'Mucha ropa de mujer a −50 % y más en el outlet. Bloquea el acceso automático.'],
  ['Pull&Bear, Bershka, Stradivarius, Massimo Dutti, Lefties y Oysho', 'https://www.pullandbear.com/es/', 'Del grupo Inditex (como Zara), pero sus webs tienen una protección anti-bots que el radar no se salta.'],
  ['H&M, COS y & Other Stories', 'https://www2.hm.com/', 'Bloquean el acceso automático.'],
  ['Adidas y ASICS', 'https://www.adidas.es/', 'Bloquean el acceso automático.'],
  ['El Corte Inglés, Zalando y ASOS', 'https://www.zalando.es/', 'Grandes tiendas multimarca. Bloquean el acceso automático.'],
  ['Primark y Kiabi', 'https://www.kiabi.es/', 'Bloquean el acceso automático.'],
  ['Ralph Lauren', 'https://www.ralphlauren.es/', 'Bloquea el acceso automático.'],
  ['On, Under Armour y Salomon', 'https://www.on.com/es-es/', 'Cargan sus productos dentro del navegador: no se pueden leer sin simular uno.'],
];

function viewTiendas() {
  const D = S.data;
  const statusById = Object.fromEntries((D.status.stores || []).map((s) => [s.id, s]));
  const dest = D.stores.filter((s) => s.destacada);
  const rest = D.stores.filter((s) => !s.destacada);
  return `<h2 class="section">Tiendas</h2>
    <h3 class="sub">⭐ Destacadas · revisadas cada 15 min</h3>
    <div class="list">${dest.map((s) => storeCard(s, statusById)).join('')}</div>
    <h3 class="sub">Otras tiendas de moda mujer · ${rest.length}</h3>
    <p class="lead">Ordenadas por rebajas: primero las que más prendas tienen con un descuento que te avisaría. Todas son las <b>webs oficiales</b> de cada marca.</p>
    <div class="list">${rest.map((s) => storeCard(s, statusById)).join('')}</div>
    <h3 class="sub">Marcas que no se pueden vigilar</h3>
    <p class="lead">Están entre las más buscadas en España, pero no dejan leer su catálogo de forma automática y el radar no se salta esas protecciones. Aquí tienes sus webs.</p>
    <div class="tips"><ul>${OTHER_SHOPS.map(([n, u, d]) => `<li><a href="${esc(u)}" target="_blank" rel="noopener"><b>${esc(n)}</b></a><br><span class="muted">${esc(d)}</span></li>`).join('')}</ul></div>
    <h3 class="sub">Consejos para comprar en rebajas</h3>
    <div class="tips"><ul>
      <li>Compra solo en la <b>web oficial</b> de la marca (las de esta app lo son). Abundan las webs falsas que copian a Zara o Zadig con descuentos del 70-80 %.</li>
      <li>En rebajas las tallas vuelan: pon <b>tu talla</b> en Avisos y solo te avisaremos si queda la tuya.</li>
      <li>Un −60 % sobre un precio inflado no es un chollo: en la ficha verás el <b>precio más bajo</b> que hemos visto de esa prenda.</li>
      <li>Revisa la política de <b>devoluciones</b> de outlet: algunas tiendas solo admiten cambio o cobran la devolución.</li>
      <li>Fíjate en los <b>gastos de envío</b> (sobre todo en tiendas de Francia o Italia) y en el pedido mínimo para envío gratis.</li>
    </ul></div>`;
}

function repoInfo() {
  const fromStatus = S.data?.status?.repo;
  if (fromStatus && fromStatus.includes('/')) { const [owner, repo] = fromStatus.split('/'); return { owner, repo }; }
  const m = location.hostname.match(/^([^.]+)\.github\.io$/);
  const repo = location.pathname.split('/').filter(Boolean)[0];
  return m && repo ? { owner: m[1], repo } : null;
}

function repoLinks() {
  const r = repoInfo();
  if (!r) return null;
  const base = `https://github.com/${r.owner}/${r.repo}`;
  return { config: `${base}/edit/main/config.toml`, actions: `${base}/actions`, run: `${base}/actions/workflows/monitor.yml` };
}

// ── Revisar las tiendas ahora (lanza el radar en GitHub) ───────────────────
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let toastTimer;
function toast(msg, ms = 3500) {
  const t = $('#toast');
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer);
  if (ms) toastTimer = setTimeout(() => { t.hidden = true; }, ms);
}
function setRunBtn(label, busy) {
  const b = $('#runnow');
  b.disabled = busy; b.classList.toggle('busy', busy);
  b.querySelector('span').textContent = label;
}
const ghHeaders = (token) => ({ Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' });
let running = false;

async function runNow() {
  if (running) return;
  const r = repoInfo();
  const token = store.get('ghToken', '');
  if (!r || !token) {
    S.tab = 'avisos'; store.set('tab', S.tab); render();
    setTimeout(() => $('#runnow-setup')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60);
    toast('Configura el botón una sola vez (aquí abajo)', 4000);
    return;
  }
  running = true;
  setRunBtn('Revisando…', true);
  const api = `https://api.github.com/repos/${r.owner}/${r.repo}`;
  const headers = ghHeaders(token);
  const since = new Date(Date.now() - 60000).toISOString().replace(/\.\d+Z$/, 'Z');
  const before = S.data?.status?.generated || '';
  try {
    const res = await fetch(`${api}/actions/workflows/monitor.yml/dispatches`, {
      method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ ref: 'main', inputs: { test_notify: false } }),
    });
    if (res.status === 401) throw new Error('El token no es válido o ha caducado: vuelve a configurarlo en Avisos.');
    if (res.status === 403 || res.status === 404) throw new Error('El token no tiene el permiso «Actions: Read and write» sobre este repositorio.');
    if (!res.ok) throw new Error(`GitHub ha respondido ${res.status}.`);
    toast('📡 Revisando las tiendas… tarda 1-2 minutos', 5000);

    let run = null;
    const deadline = Date.now() + 8 * 60 * 1000;
    while (Date.now() < deadline) {
      await sleep(8000);
      const rr = await fetch(`${api}/actions/runs?event=workflow_dispatch&per_page=5`, { headers }).catch(() => null);
      if (!rr || !rr.ok) continue;
      const js = await rr.json();
      // la nuestra (no la que lanza el reloj cada 15 min)
      run = (js.workflow_runs || []).find((w) => w.created_at >= since && !/^Reloj/.test(w.display_title || '')) || run;
      if (run) setRunBtn(run.status === 'completed' ? 'Publicando…' : run.status === 'queued' ? 'En cola…' : 'Revisando…', true);
      if (run && run.status === 'completed') break;
    }
    if (!run || run.status !== 'completed') throw new Error('Está tardando más de lo normal; los datos aparecerán cuando termine.');
    if (run.conclusion === 'cancelled') {  // GitHub la sustituye por otra revisión que ya estaba en marcha
      toast('⏳ Ya había otra revisión en marcha: los datos se actualizan en 1-2 minutos', 6000);
      return;
    }
    if (run.conclusion !== 'success') throw new Error('La revisión ha fallado: mira los detalles en GitHub → Actions.');

    setRunBtn('Cargando…', true);
    for (let i = 0; i < 12; i += 1) {  // la web tarda unos segundos en publicar los datos nuevos
      const st = await getJSON('status.json').catch(() => ({}));
      if ((st.generated || '') > before) break;
      await sleep(5000);
    }
    await load();
    const n = S.data?.status?.events_this_run || 0;
    toast(n ? `✅ Listo: ${n} rebaja${n === 1 ? '' : 's'} nueva${n === 1 ? '' : 's'}` : '✅ Revisado: nada nuevo por ahora', 5000);
  } catch (e) {
    toast(`⚠️ ${e.message}`, 7000);
  } finally {
    running = false;
    setRunBtn('Revisar', false);
  }
}

async function saveToken() {
  const input = $('#gh-token');
  const token = (input?.value || '').trim();
  const r = repoInfo();
  if (!token || !r) return;
  toast('Comprobando el token…', 0);
  try {
    const res = await fetch(`https://api.github.com/repos/${r.owner}/${r.repo}/actions/workflows/monitor.yml`, { headers: ghHeaders(token) });
    if (!res.ok) throw new Error(res.status === 401 ? 'token no válido' : `sin acceso al repositorio (${res.status})`);
    store.set('ghToken', token);
    toast('✅ Botón configurado. Pulsa «Revisar» cuando quieras.', 4500);
    render();
  } catch (e) {
    toast(`⚠️ No se ha guardado: ${e.message}`, 6000);
  }
}

function runNowPanel(links) {
  const r = repoInfo();
  if (store.get('ghToken', '')) {
    return `<div class="panel">
      <b>✅ Configurado en este móvil</b>
      <p class="muted" style="margin:6px 0 0">Pulsa <b>Revisar</b> (arriba) para revisar todas las tiendas al momento. Tarda 1-2 minutos y la app se actualiza sola.</p>
      <div class="actions" style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
        <button class="btn" data-runnow>📡 Revisar ahora</button>
        <button class="btn ghost" data-clear-token>Quitar token</button>
      </div></div>`;
  }
  const owner = r ? encodeURIComponent(r.owner) : '';
  const tokenUrl = `https://github.com/settings/personal-access-tokens/new?name=ModaRadar&description=Boton%20Revisar%20de%20ModaRadar&target_name=${owner}&expires_in=365&actions=write`;
  return `<div class="panel">
    <b>Revisar las tiendas cuando tú quieras</b>
    <p class="muted" style="margin:6px 0 0">Se configura una sola vez. El token se guarda solo en este móvil.</p>
    <ol>
      <li>Abre <a href="${esc(tokenUrl)}" target="_blank" rel="noopener"><b>Crear token en GitHub</b></a> (inicia sesión si te lo pide).</li>
      <li>En <b>Repository access</b> elige <b>Only select repositories</b> → <b>${esc(r ? r.repo : 'modaradar')}</b>.</li>
      <li>En <b>Permissions</b> → <b>Repository permissions</b> → <b>Actions</b> elige <b>Read and write</b>.</li>
      <li>Pulsa <b>Generate token</b>, cópialo y pégalo aquí:</li>
    </ol>
    <div class="field">
      <input id="gh-token" type="password" placeholder="github_pat_…" autocomplete="off" autocapitalize="off" spellcheck="false">
      <button class="btn" data-save-token>Guardar</button>
    </div>
    ${links ? `<p class="muted" style="margin:12px 0 0">Sin token también puedes lanzarlo desde <a href="${esc(links.run)}" target="_blank" rel="noopener">GitHub → Run workflow</a>.</p>` : ''}
  </div>`;
}

const TRIGGER = {
  reloj: ['⏱️', 'Reloj'], schedule: ['🐢', 'GitHub'], workflow_dispatch: ['👆', 'Botón'], push: ['🛠️', 'Ajustes'], local: ['💻', 'Manual'],
};
const hhmm = (iso) => new Date(iso).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });

function clockSetup() {
  const r = repoInfo();
  const url = r ? `https://github.com/${encodeURIComponent(r.owner)}/${encodeURIComponent(r.repo)}/settings/environments` : '';
  return `<p class="lead">El radar revisa las tiendas y te avisa al móvil en cuanto aparece una rebaja. Ahora depende del programador de GitHub, que se salta o retrasa muchas revisiones.</p>
    <div class="panel">
      <b>⏱️ Activa el reloj de 15 minutos</b> <span class="muted">· 30 segundos, una sola vez</span>
      <ol>
        <li>Abre ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener"><b>GitHub → Environments</b></a>` : '<b>GitHub → Settings → Environments</b>'} y toca <b>reloj</b>.</li>
        <li>Marca <b>Wait timer</b>, escribe <b>15</b> y pulsa <b>Save protection rules</b>.</li>
        <li>Vuelve aquí y pulsa <b>Revisar</b>: eso pone el reloj en marcha.</li>
      </ol>
    </div>`;
}

function cadencePanel(st) {
  const hist = (st.history || []).filter((h) => h && h.at);
  const now = Date.now();
  const clockOn = hist.some((h) => h.by === 'reloj' && now - new Date(h.at).getTime() < 40 * 60000);
  const recent = hist.filter((h) => now - new Date(h.at).getTime() < 3 * 3600000);
  let gap = 0;   // hueco más largo entre revisiones en las últimas 3 horas
  for (let i = 0; i + 1 < recent.length; i += 1) gap = Math.max(gap, new Date(recent[i].at) - new Date(recent[i + 1].at));
  if (recent.length) gap = Math.max(gap, now - new Date(recent[0].at));
  const gapMin = Math.round(gap / 60000);
  const lead = clockOn
    ? '<p class="lead">⏱️ <b>Reloj puntual activo:</b> el radar revisa las tiendas cada 15 minutos y te avisa al móvil en cuanto aparece una rebaja.</p>'
    : clockSetup();
  if (!hist.length) return lead;
  const chips = hist.slice(0, 10).map((h) => {
    const [icon, label] = TRIGGER[h.by] || ['•', h.by];
    return `<span class="pill ${h.by === 'reloj' ? 'ok' : 'info'}" title="${esc(label)}">${icon} ${esc(hhmm(h.at))}</span>`;
  }).join('');
  return `${lead}
    <div class="panel">
      <b>Últimas revisiones</b>${recent.length > 1 ? ` <span class="muted">· hueco máximo en 3 h: ${gapMin} min</span>` : ''}
      <div class="tags">${chips}</div>
      <p class="muted" style="margin:8px 0 0;font-size:12.5px">⏱️ reloj · 👆 botón «Revisar» · 🐢 respaldo de GitHub · 🛠️ cambios en la app</p>
    </div>`;
}

function connectionSummary(st) {
  const shops = (st.stores || []).filter((s) => s.status !== 'skipped');
  if (!shops.length) return '';
  const ok = shops.filter((s) => s.status === 'ok').length;
  const paused = shops.filter((s) => s.status === 'blocked');
  const err = shops.filter((s) => s.status === 'error');
  return `<div class="panel" style="margin-bottom:10px">
    <b>${ok === shops.length ? '✅' : '📡'} ${ok} de ${shops.length} tiendas conectadas</b>
    ${paused.length ? `<p class="muted" style="margin:6px 0 0">⏸️ En pausa: ${paused.map((s) => esc(s.name)).join(', ')}. Algunas tiendas limitan el acceso automático cuando reciben muchas peticiones; el radar espera (1 h, 2 h, 4 h…) y lo vuelve a intentar solo, sin saltarse sus protecciones.</p>` : ''}
    ${err.length ? `<p class="muted" style="margin:6px 0 0">⚠️ Con errores: ${err.map((s) => esc(s.name)).join(', ')} (suele ser una caída temporal de la tienda).</p>` : ''}
  </div>`;
}

function sizesPanel(st) {
  const cfgSizes = st.mis_tallas || [];
  return `<div class="panel">
    <b>👗 Tu talla en la app</b>
    <p class="muted" style="margin:6px 0 0">Para el filtro «Mi talla» de este móvil. Varias separadas por comas: <code>S, M</code> · <code>36, 38</code>.</p>
    <div class="field">
      <input id="my-sizes" type="text" placeholder="p. ej. S, M, 38" value="${esc((S.sizes || []).join(', '))}" autocomplete="off" autocapitalize="characters" spellcheck="false">
      <button class="btn" data-save-sizes>Guardar</button>
    </div>
    <p class="muted" style="margin:10px 0 0;font-size:12.5px">${cfgSizes.length
    ? `Los avisos al móvil ya filtran por: <b>${cfgSizes.map(esc).join(', ')}</b>.`
    : 'Los avisos al móvil llegan para cualquier talla. Para filtrarlos pon <code>mis_tallas</code> en la configuración (botón «Cambiar preferencias»).'}</p>
  </div>`;
}

function viewAvisos() {
  const D = S.data;
  const st = D.status || {};
  const u = umbral();
  const links = repoLinks();
  const rows = (st.stores || []).map((s) => {
    const map = { ok: ['ok', 'OK'], skipped: ['info', 'Sin configurar'], blocked: ['warn', 'En pausa'], error: ['no', 'Error'] };
    const [cls, l] = map[s.status] || ['info', s.status];
    const detail = s.status === 'ok' ? `${s.items ?? 0} rebajadas · ${s.events || 0} novedades · ${ago(s.at)}${s.message ? ` · ${s.message}` : ''}` : (s.message || '');
    return `<div class="status-row"><div>${esc(s.name)}<small>${esc(detail)}</small></div><span class="pill ${cls}">${l}</span></div>`;
  }).join('');
  return `<h2 class="section">Avisos</h2>
    ${cadencePanel(st)}
    <div class="panel">
      <b>Activar las notificaciones en el móvil</b>
      <ol>
        <li>Instala la app gratuita <b>ntfy</b> (<a href="https://apps.apple.com/app/ntfy/id1625396347" target="_blank" rel="noopener">iPhone</a> · <a href="https://play.google.com/store/apps/details?id=io.heckel.ntfy" target="_blank" rel="noopener">Android</a>).</li>
        <li>Pulsa <b>+</b> y suscríbete a tu tema privado (el valor de <code>NTFY_TOPIC</code> que guardaste en GitHub).</li>
        <li>Acepta las notificaciones. ¡Listo! Al tocar un aviso se abre la prenda en la tienda.</li>
      </ol>
    </div>
    <h3 class="sub">Te avisamos de</h3>
    <div class="panel">
      <div>🆕 Prendas que entran en rebajas u outlet desde <b>−${u.min} %</b> (⭐ <b>−${u.dest} %</b> en las destacadas).</div>
      <div style="margin-top:6px">🔥 Desde <b>−${u.chollo} %</b>: aviso prioritario.</div>
      ${u.drop ? `<div style="margin-top:6px">💸 Prendas ya rebajadas que bajan otro <b>${u.drop} %</b>.</div>` : ''}
      <div style="margin-top:6px">🔁 Prendas rebajadas que vuelven a tener stock${(st.mis_tallas || []).length ? ' en tu talla' : ''}.</div>
      <div style="margin-top:10px">Categorías: <span class="tags">${(st.categories || []).map((c) => `<span class="pill info">${esc(c)}</span>`).join('') || '—'}</span></div>
      <div style="margin-top:10px">Siempre con prioridad: <span class="tags">${(st.watchlist || []).map((w) => `<span class="pill accent">${esc(w)}</span>`).join('') || '—'}</span></div>
      ${links ? `<p style="margin:12px 0 0"><a class="btn ghost" href="${esc(links.config)}" target="_blank" rel="noopener">Cambiar preferencias</a></p>` : '<p class="muted" style="margin:12px 0 0">Se cambian en <code>config.toml</code>.</p>'}
    </div>
    <h3 class="sub" id="sizes-setup">Tu talla</h3>
    ${sizesPanel(st)}
    <h3 class="sub" id="runnow-setup">Botón «Revisar»</h3>
    ${runNowPanel(links)}
    <h3 class="sub">Historial de avisos</h3>
    <p class="muted" style="margin:-4px 0 10px">Todo lo que te hemos notificado (y lo que se quedó fuera por tus filtros de categoría o talla).</p>
    ${D.events.length ? `<div class="list">${D.events.slice(0, S.limit).map(eventCard).join('')}</div>
      ${D.events.length > S.limit ? `<p style="text-align:center"><button class="btn ghost" data-more>Ver más (${D.events.length - S.limit})</button></p>` : ''}`
      : empty('Aún no hay avisos', 'La primera pasada solo memoriza lo que ya está rebajado; a partir de ahí, cada rebaja nueva aparecerá aquí y en tu móvil.')}
    <h3 class="sub">Tiendas conectadas ${st.generated ? `· revisado ${esc(ago(st.generated))}` : ''}</h3>
    ${connectionSummary(st)}
    <div class="panel">${rows || '<span class="muted">Todavía no se ha ejecutado.</span>'}
      ${(st.notify_errors || []).length ? `<p class="note" style="margin-top:10px">${st.notify_errors.map(esc).join('<br>')}</p>` : ''}
      ${links ? `<p style="margin:12px 0 0"><a class="btn ghost" href="${esc(links.actions)}" target="_blank" rel="noopener">Ver ejecuciones</a></p>` : ''}
    </div>`;
}

// ── ficha de la prenda (se abre al tocarla) ────────────────────────────────
function stockNote(p) {
  const st = (S.data.status.stores || []).find((s) => s.id === p.store) || {};
  if (gone(p)) return `⚠️ No aparece en la última revisión (desde ${esc(ago(p.extra.unseen))}): se ha agotado o ya no está rebajada.`;
  if (st.status === 'blocked') return '⏸️ La tienda está en pausa: precio y stock son los de la última revisión.';
  const m = S.data.meta[p.store] || {};
  if (m.partial && p.last_seen && st.at && p.last_seen < st.at.slice(0, 10)) {
    return `🕒 Vista en su web por última vez el ${esc(new Date(p.last_seen).toLocaleDateString('es-ES', { day: 'numeric', month: 'long' }))}: de ${esc(m.name || p.store)} solo se leen las rebajas más nuevas, así que compruébalo en su web.`;
  }
  return st.at ? `🕒 Precio y stock comprobados ${esc(ago(st.at))}.` : '';
}

function sheetHTML(p) {
  const D = S.data;
  const m = D.meta[p.store] || {};
  const min = p.extra && p.extra.min;
  const when = newKey(p);
  let html = `<div class="sheet-media">${img(p.image, emojiOf(p), 'simg')}${p.pct ? `<span class="off big${isHot(p) ? ' hot' : ''}">−${p.pct} %</span>` : ''}</div>
    <p class="stitle">${esc(p.title)}</p>
    <div class="meta"><span class="price lg">${money(p.price, p.currency)}</span>${p.original ? `<s class="was">${money(p.original, p.currency)}</s>` : ''} ${stockPill(p)}</div>
    <div class="meta" style="margin-top:6px">${isDest(p.store) ? '⭐ ' : ''}${esc(shopName(p.store))}${p.category === 'ropa' && p.prenda ? ` · ${esc((PRENDA[p.prenda] || PRENDA.otras).label)}` : ''}${when ? ` · en outlet ${esc(ago(when))}` : ''}</div>`;
  const facts = [];
  if (p.original && p.price) facts.push(`Te ahorras <b>${money(p.original - p.price)}</b> sobre su precio original.`);
  if (dropped(p)) facts.push(`💸 Ha bajado de <b>${money(p.prev_price)}</b> a <b>${money(p.price)}</b>.`);
  if (min && p.price && p.price <= min) facts.push('📉 Es el <b>precio más bajo</b> que hemos visto.');
  else if (min && p.price > min) facts.push(`📈 La hemos visto más barata: <b>${money(min)}</b>.`);
  if (p.extra && p.extra.hasta) facts.push(`🗓️ Precio especial ${esc(p.extra.hasta.toLowerCase())}.`);
  if (facts.length) html += `<div class="panel facts-box">${facts.map((f) => `<div>${f}</div>`).join('')}</div>`;
  if (Array.isArray(p.sizes)) {
    html += `<h3 class="sub">Tallas con stock</h3>`;
    html += p.sizes.length ? `<div class="size-chips">${p.sizes.map((s) => `<span class="size${mySizes().length && sizeFits(s) ? ' mine' : ''}">${esc(s)}</span>`).join('')}</div>`
      : '<p class="muted">Ninguna ahora mismo.</p>';
  } else if (p.category === 'ropa') {
    html += '<p class="muted sheet-note">Esta tienda no publica las tallas en su catálogo: compruébalas en su web.</p>';
  }
  html += `<p class="muted sheet-note">${stockNote(p)}</p>`;
  html += `<div class="actions sheet-actions">
      <a class="btn" href="${esc(safeUrl(p.url))}" target="_blank" rel="noopener">Ver en ${esc(shopName(p.store))}</a>
      ${m.outlet_url ? `<a class="btn ghost" href="${esc(safeUrl(m.outlet_url))}" target="_blank" rel="noopener">Su outlet</a>` : ''}
    </div>`;
  if (m.note) html += `<p class="muted sheet-note">${esc(m.note)}</p>`;
  // prendas parecidas (mismo tipo) en otras tiendas
  const key = p.category === 'ropa' ? p.prenda : null;
  const similar = sortItems(D.products.filter((q) => q.id !== p.id && inStock(q) && q.category === p.category
    && (!key || q.prenda === key) && fitsMe(q)), 'descuento').slice(0, 4);
  if (similar.length) {
    html += `<h3 class="sub">${key && PRENDA[key] ? `Más ${esc(PRENDA[key].label.toLowerCase())}` : 'Más'} en outlet</h3>${grid(similar)}`;
  }
  return html;
}

function openSheet(id) {
  const p = S.data && S.data.byId.get(id);
  if (!p) return;
  closeSheet();
  const back = document.createElement('div');
  back.className = 'sheet-back';
  back.innerHTML = `<div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(p.title)}">
    <div class="grab" aria-hidden="true"></div>
    <button class="sheet-x" data-close aria-label="Cerrar">✕</button>
    ${sheetHTML(p)}</div>`;
  back.addEventListener('click', (ev) => {
    if (ev.target === back || ev.target.closest('[data-close]')) { closeSheet(); return; }
    const other = ev.target.closest('.sheet [data-open]');
    if (other) { ev.preventDefault(); ev.stopPropagation(); openSheet(other.dataset.open); }
  });
  document.body.appendChild(back);
  document.body.classList.add('locked');
  back.querySelector('.sheet-x').focus({ preventScroll: true });
}
function closeSheet() {
  document.querySelectorAll('.sheet-back').forEach((n) => n.remove());
  document.body.classList.remove('locked');
}
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape') closeSheet();
  if (ev.key === 'Enter' && ev.target.matches && ev.target.matches('[data-open]')) openSheet(ev.target.dataset.open);
});

// ── render y eventos ───────────────────────────────────────────────────────
const VIEWS = { novedades: viewNovedades, destacadas: viewDestacadas, buscar: viewBuscar, tiendas: viewTiendas, avisos: viewAvisos };

function render() {
  if (!S.data) return;
  document.querySelectorAll('.tabbar [data-tab]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === S.tab)));
  $('#view').innerHTML = (VIEWS[S.tab] || viewNovedades)();
}

const updateResults = debounce(() => { const r = $('#results'); if (r) r.innerHTML = resultsHTML(); }, 180);
const setPref = (k, v) => { S[k] = v; S.limit = PAGE; store.set(k, v); render(); };

document.addEventListener('click', (ev) => {
  const opener = ev.target.closest('[data-open]');
  const link = ev.target.closest('a');
  if (opener && (!link || link === opener) && !ev.target.closest('.sheet')) {
    ev.preventDefault();
    openSheet(opener.dataset.open);
    return;
  }
  const t = ev.target.closest('button');
  if (!t) return;
  if (t.dataset.tab) { S.tab = t.dataset.tab; S.limit = PAGE; store.set('tab', S.tab); render(); window.scrollTo(0, 0); return; }
  if (t.dataset.dest) { setPref('dest', t.dataset.dest); return; }
  if (t.dataset.expand) { S.expanded[t.dataset.expand] = true; render(); return; }
  if (t.dataset.seg) { setPref('seg', t.dataset.seg); return; }
  if (t.dataset.cat) { S.prenda = 'todas'; store.set('prenda', 'todas'); setPref('cat', t.dataset.cat); return; }
  if (t.dataset.goshop) {
    S.shop = t.dataset.goshop; store.set('shop', S.shop);
    S.cat = 'todo'; store.set('cat', 'todo'); S.seg = 'nuevas'; store.set('seg', 'nuevas');
    S.tab = 'novedades'; store.set('tab', 'novedades'); S.limit = PAGE; render(); window.scrollTo(0, 0); return;
  }
  if ('stock' in t.dataset) { setPref('stockOnly', !S.stockOnly); return; }
  if ('mysize' in t.dataset) { setPref('mySize', !S.mySize); return; }
  if ('big' in t.dataset) { setPref('big', !S.big); return; }
  if ('gosizes' in t.dataset) {
    S.tab = 'avisos'; store.set('tab', S.tab); render();
    setTimeout(() => { $('#sizes-setup')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); $('#my-sizes')?.focus(); }, 60);
    return;
  }
  if ('saveSizes' in t.dataset) {
    const v = ($('#my-sizes')?.value || '').split(/[,;]+/).map((s) => s.trim()).filter(Boolean).slice(0, 8);
    S.sizes = v; store.set('sizes', v); S.mySize = v.length > 0; store.set('mySize', S.mySize);
    toast(v.length ? `✅ Tu talla: ${v.join(', ')}` : 'Talla borrada'); render(); return;
  }
  if ('more' in t.dataset) { S.limit += PAGE; render(); return; }
  if ('dismissInstall' in t.dataset) { $('#install-hint').hidden = true; store.set('installHint', false); return; }
  if (t.id === 'refresh') load();
  if (t.id === 'runnow' || 'runnow' in t.dataset) runNow();
  if ('saveToken' in t.dataset) saveToken();
  if ('clearToken' in t.dataset) { store.set('ghToken', ''); toast('Token eliminado de este móvil'); render(); }
});
document.addEventListener('change', (ev) => {
  if (ev.target.matches('[data-shop]')) setPref('shop', ev.target.value);
  if (ev.target.matches('[data-prenda]')) setPref('prenda', ev.target.value);
  if (ev.target.matches('[data-sort]')) setPref('sort', ev.target.value);
});
document.addEventListener('input', (ev) => {
  if (ev.target.id === 'q') { S.query = ev.target.value; S.limit = PAGE; updateResults(); }
});
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && S.data) load(); });

// Sugerencia de instalación en iPhone (Safari, fuera de modo app)
const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const standalone = window.navigator.standalone || matchMedia('(display-mode: standalone)').matches;
if (isIOS && !standalone && store.get('installHint', true)) $('#install-hint').hidden = false;

if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
load();
