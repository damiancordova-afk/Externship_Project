"""HTML template for the Campus Recruiting Directory. __DATA__ is replaced with
the JSON payload by build_directory.py. Data is rendered via textContent in JS,
so candidate values never inject markup."""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Campus Recruiting Directory — Valon</title>
  <style>
    :root {
      --white:#FFFFFF; --n-100:#F8F6F3; --n-200:#ECE4DD; --n-300:#DCD2C6;
      --n-400:#AF9F8A; --n-500:#827057; --n-600:#5C543C; --n-700:#4A402C;
      --n-800:#31231B; --n-900:#20190F; --n-950:#231810;
      --gold-400:#EBB03C; --gold-500:#E19614; --gold-600:#BE7E10;
      --ink:#231810;
      --text-body:rgba(35,24,16,0.80); --text-secondary:rgba(35,24,16,0.60);
      --text-label:rgba(35,24,16,0.40); --border-soft:rgba(35,24,16,0.10);
      --border-hover:rgba(35,24,16,0.20); --divider:rgba(35,24,16,0.08);
      --row-hover:rgba(35,24,16,0.05);
      --radius-input:8px; --radius-card:12px;
      --shadow-menu:0 4px 12px rgba(35,24,16,0.10); --ease:150ms ease;
      --font-sans:"KMR Melange Grotesk",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
      --font-mono:"Geist Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    }
    * { box-sizing:border-box; }
    html,body { margin:0; padding:0; background:var(--n-100); color:var(--ink);
      font-family:var(--font-sans); font-size:16px; line-height:1.4;
      -webkit-font-smoothing:antialiased; }
    :focus-visible { outline:2px solid var(--ink); outline-offset:2px; }
    :focus:not(:focus-visible) { outline:none; }
    a { color:inherit; }

    .page { max-width:960px; margin:0 auto; padding:0 24px 96px; }

    /* Header */
    .header { height:44px; padding:12px 0; display:flex; align-items:center;
      justify-content:space-between; box-sizing:content-box; }
    .header__left { display:flex; align-items:center; gap:16px; min-width:0; }
    .wordmark { display:flex; align-items:center; gap:8px; letter-spacing:-0.5px; }
    .wordmark__mark { width:28px; height:28px; display:grid; place-items:center; }
    .wordmark__mark svg { width:100%; height:100%; display:block; }
    .wordmark__name { font-size:18px; letter-spacing:-0.6px; }
    .header__divider { width:1px; height:20px; background:var(--border-soft); }
    .header__label { font-size:14px; color:var(--text-secondary); letter-spacing:-0.2px; white-space:nowrap; }
    .icon-btn { width:40px; height:40px; border-radius:50%; border:none;
      background:var(--n-100); color:var(--ink); display:grid; place-items:center;
      cursor:pointer; transition:background var(--ease); flex-shrink:0; }
    .icon-btn:hover { background:var(--n-200); }
    .icon-btn svg { width:20px; height:20px; }

    /* Intro */
    .intro { padding:48px 0 32px; }
    .intro h1 { margin:0 0 8px; font-weight:400; font-size:32px; letter-spacing:-0.8px; }
    .intro p { margin:0; font-size:16px; color:var(--text-body); max-width:64ch; }

    /* Controls */
    .controls { display:flex; flex-direction:column; gap:16px; margin-bottom:24px; }
    .search { position:relative; }
    .search__icon { position:absolute; left:16px; top:50%; transform:translateY(-50%);
      width:20px; height:20px; color:var(--text-secondary); pointer-events:none; }
    .search input { width:100%; height:48px; border-radius:var(--radius-input);
      border:1px solid var(--border-soft); background:var(--white);
      padding:12px 16px 12px 48px; font-family:var(--font-sans); font-size:16px;
      color:var(--ink); transition:border-color var(--ease); }
    .search input::placeholder { color:var(--text-secondary); }
    .search input:hover { border-color:var(--border-hover); }
    .search input:focus-visible { border-color:transparent; }
    .filters { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
    .filters__label { font-size:12px; text-transform:uppercase; letter-spacing:0.6px;
      color:var(--text-label); margin-right:8px; }
    .pill { border:1px solid var(--border-soft); border-radius:var(--radius-input);
      background:var(--white); padding:6px 12px; font-family:var(--font-sans);
      font-size:14px; color:var(--text-body); cursor:pointer;
      transition:border-color var(--ease),background var(--ease),color var(--ease);
      min-height:32px; }
    .pill:hover { border-color:var(--border-hover); }
    .pill[aria-pressed="true"] { background:var(--ink); border-color:var(--ink); color:var(--white); }

    .result-count { margin:0 0 16px; font-size:13px; color:var(--text-secondary); }

    /* Table */
    .table { background:var(--white); border:1px solid var(--border-soft);
      border-radius:var(--radius-card); overflow:hidden; }
    .table__head { display:grid; grid-template-columns:1fr auto 40px; align-items:center;
      gap:16px; padding:16px 24px; border-bottom:1px solid var(--divider); }
    .col-head { font-size:12px; text-transform:uppercase; letter-spacing:0.6px; color:var(--text-label); }
    .col-head--hires { text-align:right; }
    .row { display:grid; grid-template-columns:1fr auto 40px; align-items:center; gap:16px;
      width:100%; padding:16px 24px; border:none; border-bottom:1px solid var(--divider);
      background:transparent; text-align:left; font-family:var(--font-sans); cursor:pointer;
      transition:background var(--ease); }
    .row:last-child { border-bottom:none; }
    .row:hover { background:var(--row-hover); }
    .row:focus-visible { outline:2px solid var(--ink); outline-offset:-2px; }
    .row__name-wrap { display:flex; align-items:center; gap:12px; min-width:0; flex-wrap:wrap; }
    .row__name { font-size:16px; letter-spacing:-0.2px; }
    .row__hires { font-size:14px; color:var(--text-secondary); text-align:right;
      white-space:nowrap; font-variant-numeric:tabular-nums; }
    .row__chevron { color:var(--text-secondary); display:grid; place-items:center;
      transition:transform var(--ease),color var(--ease); }
    .row:hover .row__chevron { color:var(--ink); transform:translateX(2px); }
    .row__chevron svg { width:20px; height:20px; }

    /* Criteria tags */
    .tag { display:inline-flex; align-items:center; gap:6px; font-size:12px;
      letter-spacing:0.2px; padding:3px 10px 3px 8px; border-radius:999px;
      white-space:nowrap; background:var(--n-100); border:1px solid var(--border-soft);
      color:var(--text-body); }
    .tag::before { content:""; width:6px; height:6px; border-radius:50%; background:currentColor; flex-shrink:0; }
    .tag--ranked::before { background:var(--gold-500); }
    .tag--ny::before { background:var(--n-500); }
    .tag--sf::before { background:var(--ink); }
    .tag--hired::before { background:#3F7D5B; }
    .tag--fair::before { background:#2F6FB0; }
    .tag--extra::before { background:var(--n-400); }

    /* Row: stack name + next-fair line in the first column */
    .row__main { display:flex; flex-direction:column; gap:6px; min-width:0; }
    .row__sub { display:inline-flex; align-items:center; gap:6px; font-size:13px;
      color:var(--text-secondary); }
    .row__sub svg { width:14px; height:14px; flex-shrink:0; color:#2F6FB0; }
    .row__sub b { font-weight:400; color:var(--text-body); font-variant-numeric:tabular-nums; }
    .row__sub .row__sub-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

    /* Modal: upcoming career-fair block */
    .fairs { margin:8px 0 24px; }
    .fairs__title { font-size:12px; text-transform:uppercase; letter-spacing:0.6px;
      color:var(--text-label); margin:0 0 12px; }
    .fair { display:flex; gap:14px; padding:12px 0; border-bottom:1px solid var(--divider); }
    .fair:last-child { border-bottom:none; }
    .fair__date { flex-shrink:0; width:64px; text-align:center; line-height:1.1; }
    .fair__date-m { font-size:11px; text-transform:uppercase; letter-spacing:0.6px; color:#2F6FB0; }
    .fair__date-d { font-size:22px; font-variant-numeric:tabular-nums; }
    .fair__date-y { font-size:11px; color:var(--text-label); }
    .fair__body { min-width:0; }
    .fair__name { font-size:15px; margin-bottom:2px; }
    .fair__loc { font-size:13px; color:var(--text-secondary); }
    .fair__src { font-size:13px; }
    .fair__src a { color:#2F6FB0; }
    /* Recently-passed block: muted so it reads as history, not upcoming */
    .fairs--past { opacity:0.7; }
    .fairs--past .fair__date-m { color:var(--text-label); }

    .empty { padding:64px 24px; text-align:center; color:var(--text-secondary); font-size:15px; }

    /* Modal */
    .overlay { position:fixed; inset:0; background:rgba(35,24,16,0.45); display:none;
      align-items:center; justify-content:center; padding:24px; z-index:50; }
    .overlay.open { display:flex; }
    .modal { background:var(--white); border-radius:var(--radius-card);
      box-shadow:var(--shadow-menu); width:100%; max-width:560px; max-height:82vh;
      display:flex; flex-direction:column; }
    .modal__top { display:flex; align-items:flex-start; justify-content:space-between;
      gap:16px; padding:32px 32px 16px; }
    .modal__title { margin:0 0 8px; font-weight:400; font-size:24px; letter-spacing:-0.6px; }
    .modal__meta { display:flex; align-items:center; gap:8px; flex-wrap:wrap;
      font-size:14px; color:var(--text-secondary); }
    .modal__body { overflow-y:auto; padding:8px 32px 32px; }
    .hire { padding:16px 0; border-bottom:1px solid var(--divider); }
    .hire:last-child { border-bottom:none; }
    .hire__name { font-size:16px; margin-bottom:8px; }
    .contacts { display:flex; flex-wrap:wrap; gap:8px; }
    .contact { display:inline-flex; align-items:center; gap:6px; font-size:13px;
      padding:6px 12px; border-radius:var(--radius-input); border:1px solid var(--border-soft);
      background:var(--white); color:var(--text-body); text-decoration:none;
      transition:border-color var(--ease),background var(--ease); max-width:100%; }
    .contact:hover { border-color:var(--border-hover); background:var(--n-100); }
    .contact__label { color:var(--text-label); text-transform:uppercase; font-size:11px; letter-spacing:0.4px; }
    .contact__value { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:220px; }
    .contact--mono { font-family:var(--font-mono); }
    .hire__none { font-size:13px; color:var(--text-secondary); font-style:italic; }
    .modal__emptystate { padding:32px 0; text-align:center; color:var(--text-secondary); font-size:14px; }

    .footnote { margin-top:24px; font-size:12px; color:var(--text-label); }

    @media (max-width:480px) {
      .page { padding:0 16px 64px; }
      .header__label { display:none; }
      .table { background:transparent; border:none; border-radius:0; overflow:visible; }
      .table__head { display:none; }
      .row { grid-template-columns:1fr; gap:8px; padding:16px; background:var(--white);
        border:1px solid var(--border-soft); border-radius:var(--radius-card);
        margin-bottom:16px; min-height:44px; }
      .row__hires { text-align:left; }
      .row__chevron { display:none; }
      .modal__top, .modal__body { padding-left:20px; padding-right:20px; }
    }
    .sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px;
      overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
  </style>
</head>
<body>
  <div class="page">
    <header class="header">
      <div class="header__left">
        <div class="wordmark">
          <span class="wordmark__mark" aria-hidden="true">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="335 2 65 64" fill="none">
              <path d="M370.01 22.5377L378.288 2.55489H370.349L367.228 12.699L364.106 2.55489H356.168L364.446 22.5377H370.01Z" fill="#E19614"/>
              <path d="M364.446 45.1552L356.168 65.1381H364.106L367.228 54.994L370.349 65.1381H378.288L370.01 45.1552H364.446Z" fill="#E19614"/>
              <path d="M355.919 31.0645L335.936 22.7864V30.7252L346.08 33.8465L335.936 36.9677V44.9067L355.919 36.6285V31.0645Z" fill="#E19614"/>
              <path d="M398.519 22.7864L378.536 31.0645V36.6285L398.519 44.9067V36.9677L388.375 33.8465L398.519 30.7252V22.7864Z" fill="#E19614"/>
              <path d="M357.276 39.8741L337.282 48.1636L342.891 53.7728L352.277 48.7971L347.301 58.1832L352.911 63.7924L361.2 43.7984L357.276 39.8741Z" fill="#E19614"/>
              <path d="M377.18 27.8189L397.174 19.5295L391.564 13.9202L382.178 18.8961L387.154 9.50978L381.545 3.90057L373.255 23.8947L377.18 27.8189Z" fill="#E19614"/>
              <path d="M373.255 43.7984L381.545 63.7924L387.154 58.1832L382.178 48.7971L391.564 53.7728L397.174 48.1636L377.18 39.8741L373.255 43.7984Z" fill="#E19614"/>
              <path d="M361.2 23.8947L352.911 3.90057L347.301 9.50978L352.277 18.8961L342.891 13.9202L337.282 19.5295L357.276 27.8189L361.2 23.8947Z" fill="#E19614"/>
            </svg>
          </span>
          <span class="wordmark__name">Valon</span>
        </div>
        <span class="header__divider" aria-hidden="true"></span>
        <span class="header__label">Campus Recruiting</span>
      </div>
    </header>

    <section class="intro">
      <h1>Campus Recruiting Directory</h1>
      <p>Every school Valon has hired from, plus top-100 national universities and
         4-year colleges in New York and San Francisco, with upcoming career fairs.
         Click a school to see who we hired there and how to reach them.</p>
    </section>

    <div class="controls">
      <div class="search">
        <svg class="search__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>
        </svg>
        <input id="search" type="search" placeholder="Search by school name..."
          autocomplete="off" aria-label="Search by school name" />
      </div>
      <div class="filters" role="group" aria-label="Filter schools">
        <span class="filters__label">Show</span>
        <button class="pill" type="button" data-filter="fair" aria-pressed="false">Upcoming career fair</button>
        <button class="pill" type="button" data-filter="hired" aria-pressed="false">Has hires</button>
        <button class="pill" type="button" data-filter="ranked" aria-pressed="false">Top 100</button>
        <button class="pill" type="button" data-filter="ny" aria-pressed="false">New York</button>
        <button class="pill" type="button" data-filter="sf" aria-pressed="false">San Francisco</button>
      </div>
    </div>

    <p class="result-count" id="resultCount" aria-live="polite"></p>

    <div class="table" role="table" aria-label="Campus recruiting directory">
      <div class="table__head" role="row">
        <span class="col-head" role="columnheader">School</span>
        <span class="col-head col-head--hires" role="columnheader">Hires</span>
        <span class="col-head" role="columnheader" aria-hidden="true"></span>
      </div>
      <div id="rows"></div>
      <div class="empty" id="empty" hidden>No schools match your search.</div>
    </div>

    <p class="footnote">Ranking source: __RANKING_SOURCE__</p>
  </div>

  <div class="overlay" id="overlay" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
    <div class="modal">
      <div class="modal__top">
        <div>
          <h2 class="modal__title" id="modalTitle">School</h2>
          <div class="modal__meta" id="modalMeta"></div>
        </div>
        <button class="icon-btn" type="button" id="modalClose" aria-label="Close">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"
            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18"/>
          </svg>
        </button>
      </div>
      <div class="modal__body" id="modalBody"></div>
    </div>
  </div>

  <script>
    const DATA = __DATA__;
    const SCHOOLS = DATA.schools;
    const CRIT = { ranked:"Top 100", ny:"New York", sf:"San Francisco",
                   hired:"Has hires", fair:"Career fair", extra:"Also tracked" };

    // Recompute "upcoming" against today's date on every load, so a fair that
    // has passed drops off without needing the page to be rebuilt.
    const TODAY_ISO = new Date().toISOString().slice(0, 10);
    function upcomingFairs(s) {
      return (s.fairs || []).filter(f => f.date >= TODAY_ISO)
                            .sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : 0);
    }
    // Single most-recently-passed fair (max 1), recomputed live against today.
    function recentPastFair(s) {
      const past = (s.fairs || []).filter(f => f.date < TODAY_ISO)
                                  .sort((a, b) => a.date < b.date ? 1 : a.date > b.date ? -1 : 0);
      return past[0] || null;
    }
    function fmtDate(iso) {
      const [y, m, d] = iso.split("-").map(Number);
      return new Date(y, m - 1, d).toLocaleDateString("en-US",
        { month: "short", day: "numeric", year: "numeric" });
    }

    const rowsEl = document.getElementById("rows");
    const emptyEl = document.getElementById("empty");
    const countEl = document.getElementById("resultCount");

    let query = "";
    const active = new Set();

    function matches(s) {
      const q = query.trim().toLowerCase();
      if (q && !s.name.toLowerCase().includes(q)) return false;
      for (const f of active) {
        // "fair" is recomputed live against today, not the static build-time tag.
        if (f === "fair") { if (!upcomingFairs(s).length) return false; }
        else if (!s.criteria.includes(f)) return false;
      }
      return true;
    }

    function tag(kind) {
      const el = document.createElement("span");
      el.className = "tag tag--" + kind;
      el.textContent = CRIT[kind];
      return el;
    }
    function chevron() {
      const s = document.createElementNS("http://www.w3.org/2000/svg","svg");
      s.setAttribute("viewBox","0 0 24 24"); s.setAttribute("fill","none");
      s.setAttribute("stroke","currentColor"); s.setAttribute("stroke-width","1.5");
      s.setAttribute("stroke-linecap","round"); s.setAttribute("stroke-linejoin","round");
      const p = document.createElementNS("http://www.w3.org/2000/svg","path");
      p.setAttribute("d","m9 6 6 6-6 6"); s.appendChild(p);
      const wrap = document.createElement("span"); wrap.className="row__chevron";
      wrap.appendChild(s); return wrap;
    }
    function calIcon() {
      const s = document.createElementNS("http://www.w3.org/2000/svg","svg");
      s.setAttribute("viewBox","0 0 24 24"); s.setAttribute("fill","none");
      s.setAttribute("stroke","currentColor"); s.setAttribute("stroke-width","1.5");
      s.setAttribute("stroke-linecap","round"); s.setAttribute("stroke-linejoin","round");
      for (const d of ["M8 2v4","M16 2v4","M3 9h18"]) {
        const p = document.createElementNS("http://www.w3.org/2000/svg","path");
        p.setAttribute("d", d); s.appendChild(p);
      }
      const r = document.createElementNS("http://www.w3.org/2000/svg","rect");
      r.setAttribute("x","3"); r.setAttribute("y","4"); r.setAttribute("width","18");
      r.setAttribute("height","18"); r.setAttribute("rx","2"); s.appendChild(r);
      return s;
    }

    function render() {
      const list = SCHOOLS.filter(matches);
      rowsEl.textContent = "";
      list.forEach(s => {
        const btn = document.createElement("button");
        btn.type = "button"; btn.className = "row"; btn.setAttribute("role","row");
        btn.setAttribute("aria-label", `${s.name}, ${s.count} hires`);

        const main = document.createElement("span");
        main.className = "row__main";

        const nameWrap = document.createElement("span");
        nameWrap.className = "row__name-wrap";
        const nm = document.createElement("span");
        nm.className = "row__name"; nm.textContent = s.name;
        nameWrap.appendChild(nm);
        if (s.criteria.includes("ranked")) nameWrap.appendChild(tag("ranked"));
        if (s.criteria.includes("ny")) nameWrap.appendChild(tag("ny"));
        if (s.criteria.includes("sf")) nameWrap.appendChild(tag("sf"));
        main.appendChild(nameWrap);

        const nextFair = upcomingFairs(s)[0];
        if (nextFair) {
          const sub = document.createElement("span");
          sub.className = "row__sub";
          sub.appendChild(calIcon());
          const dt = document.createElement("b"); dt.textContent = fmtDate(nextFair.date);
          const nmn = document.createElement("span");
          nmn.className = "row__sub-name"; nmn.textContent = " · " + nextFair.name;
          sub.appendChild(dt); sub.appendChild(nmn);
          main.appendChild(sub);
        }

        const hires = document.createElement("span");
        hires.className = "row__hires";
        hires.textContent = s.count === 0 ? "No hires yet"
                          : `${s.count} hire${s.count === 1 ? "" : "s"}`;

        btn.appendChild(main);
        btn.appendChild(hires);
        btn.appendChild(chevron());
        btn.addEventListener("click", () => openDetail(s));
        rowsEl.appendChild(btn);
      });
      emptyEl.hidden = list.length !== 0;
      countEl.textContent = `${list.length} of ${SCHOOLS.length} schools`;
    }

    // Modal
    const overlay = document.getElementById("overlay");
    const modalBody = document.getElementById("modalBody");
    const modalMeta = document.getElementById("modalMeta");
    let lastFocused = null;

    function contactChip(c) {
      const a = document.createElement("a");
      a.className = "contact" + (c.kind === "email" || c.kind === "phone" ? " contact--mono" : "");
      a.href = c.href;
      if (c.kind !== "email" && c.kind !== "phone") { a.target = "_blank"; a.rel = "noopener"; }
      const lab = document.createElement("span");
      lab.className = "contact__label"; lab.textContent = c.label;
      const val = document.createElement("span");
      val.className = "contact__value"; val.textContent = c.value;
      a.appendChild(lab); a.appendChild(val);
      return a;
    }

    function openDetail(s) {
      lastFocused = document.activeElement;
      document.getElementById("modalTitle").textContent = s.name;

      modalMeta.textContent = "";
      const hc = document.createElement("span");
      hc.textContent = s.count === 0 ? "No hires yet"
                     : `${s.count} hire${s.count === 1 ? "" : "s"}`;
      modalMeta.appendChild(hc);
      ["ranked","ny","sf","extra","hired"].forEach(k => {
        if (s.criteria.includes(k)) {
          const sep = document.createElement("span"); sep.textContent = "·"; sep.setAttribute("aria-hidden","true");
          modalMeta.appendChild(sep); modalMeta.appendChild(tag(k));
        }
      });

      modalBody.textContent = "";

      // Build a single .fair row element (shared by upcoming + passed).
      function fairRow(f) {
        const [y, m, d] = f.date.split("-").map(Number);
        const row = document.createElement("div"); row.className = "fair";
        const dbox = document.createElement("div"); dbox.className = "fair__date";
        const mm = document.createElement("div"); mm.className = "fair__date-m";
        mm.textContent = new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short" });
        const dd = document.createElement("div"); dd.className = "fair__date-d"; dd.textContent = d;
        const yy = document.createElement("div"); yy.className = "fair__date-y"; yy.textContent = y;
        dbox.appendChild(mm); dbox.appendChild(dd); dbox.appendChild(yy);
        const body = document.createElement("div"); body.className = "fair__body";
        const fn = document.createElement("div"); fn.className = "fair__name"; fn.textContent = f.name;
        body.appendChild(fn);
        if (f.location) {
          const lc = document.createElement("div"); lc.className = "fair__loc"; lc.textContent = f.location;
          body.appendChild(lc);
        }
        if (f.source) {
          const sc = document.createElement("div"); sc.className = "fair__src";
          const a = document.createElement("a"); a.href = f.source; a.target = "_blank";
          a.rel = "noopener"; a.textContent = "Source / register";
          sc.appendChild(a); body.appendChild(sc);
        }
        row.appendChild(dbox); row.appendChild(body);
        return row;
      }

      // Upcoming career fairs (recomputed against today).
      const fairs = upcomingFairs(s);
      if (fairs.length) {
        const wrap = document.createElement("div"); wrap.className = "fairs";
        const t = document.createElement("p"); t.className = "fairs__title";
        t.textContent = `Upcoming career fair${fairs.length === 1 ? "" : "s"} (${fairs.length})`;
        wrap.appendChild(t);
        fairs.forEach(f => wrap.appendChild(fairRow(f)));
        modalBody.appendChild(wrap);
      }

      // Recently passed — at most ONE (the most recent), recomputed live.
      const past = recentPastFair(s);
      if (past) {
        const wrap = document.createElement("div"); wrap.className = "fairs fairs--past";
        const t = document.createElement("p"); t.className = "fairs__title";
        t.textContent = "Recently passed";
        wrap.appendChild(t);
        wrap.appendChild(fairRow(past));
        modalBody.appendChild(wrap);
      }
      if (!s.hires.length) {
        const e = document.createElement("div");
        e.className = "modal__emptystate";
        const parts = [];
        if (s.criteria.includes("ranked")) parts.push("a top-100 national university");
        if (s.criteria.includes("ny")) parts.push("a New York State institution");
        if (s.criteria.includes("sf")) parts.push("a San Francisco institution");
        if (s.criteria.includes("extra")) parts.push("tracked for career-fair coverage");
        e.textContent = "No hires from this school yet — it's a target because it's "
          + (parts.join(" and ") || "in scope") + ".";
        modalBody.appendChild(e);
      } else {
        s.hires.forEach(h => {
          const row = document.createElement("div"); row.className = "hire";
          const nm = document.createElement("div"); nm.className = "hire__name";
          nm.textContent = h.name || "(name unavailable)";
          row.appendChild(nm);
          if (h.contacts.length) {
            const cc = document.createElement("div"); cc.className = "contacts";
            h.contacts.forEach(c => cc.appendChild(contactChip(c)));
            row.appendChild(cc);
          } else {
            const none = document.createElement("div");
            none.className = "hire__none"; none.textContent = "No contact info available";
            row.appendChild(none);
          }
          modalBody.appendChild(row);
        });
      }
      overlay.classList.add("open");
      document.getElementById("modalClose").focus();
    }
    function closeDetail() { overlay.classList.remove("open"); if (lastFocused) lastFocused.focus(); }

    document.getElementById("modalClose").addEventListener("click", closeDetail);
    overlay.addEventListener("click", e => { if (e.target === overlay) closeDetail(); });
    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && overlay.classList.contains("open")) closeDetail();
    });

    document.getElementById("search").addEventListener("input", e => { query = e.target.value; render(); });
    document.querySelectorAll(".pill").forEach(p => {
      p.addEventListener("click", () => {
        const f = p.dataset.filter;
        const on = p.getAttribute("aria-pressed") === "true";
        p.setAttribute("aria-pressed", String(!on));
        if (on) active.delete(f); else active.add(f);
        render();
      });
    });

    render();
  </script>
</body>
</html>
"""
