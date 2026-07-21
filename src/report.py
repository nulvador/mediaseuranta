"""HTML-raportin generointi: itsenäinen tiedosto, data upotettuna, suodatus selaimessa.

Ulkoasu: Suomi Golf -brändi (British Racing Green -paletti, Montserrat).
"""
import datetime
import json

from . import config

PRIO_EMOJI = {"korkea": "🔴", "keskitaso": "🟡", "matala": "🟢"}


def generate_report(articles: list[dict], healths: list[dict], run_summary: dict) -> str:
    today = datetime.date.today().strftime("%d.%m.%Y")
    previous_run_at = run_summary.get("previous_run_at")
    for a in articles:
        a["prio_emoji"] = PRIO_EMOJI.get(a.get("priority") or "", "")
        a["is_new"] = bool(previous_run_at) and (a.get("fetched_at") or "") > previous_run_at

    new_since_last = sum(1 for a in articles if a["is_new"])
    prev_line = ""
    if previous_run_at:
        try:
            prev_dt = datetime.datetime.fromisoformat(previous_run_at)
            prev_line = f" · edellinen ajo {prev_dt.strftime('%d.%m. klo %H:%M')}"
        except ValueError:
            pass

    data_json = json.dumps(articles, ensure_ascii=False).replace("</", "<\\/")
    health_json = json.dumps(healths, ensure_ascii=False).replace("</", "<\\/")
    themes_json = json.dumps(config.THEMES, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="fi"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Golfkatsaus {today}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
:root {{
  /* Suomi Golf — British Racing Green -paletti */
  --sg-racing-green: #003F20;
  --sg-dark-green:   #051A05;
  --sg-light-green:  #EBF4F0;
  --sg-grey-700:     #575B59;
  --sg-grey-200:     #E6E8EA;
  --sg-white:        #FFFFFF;
  --sg-green:        #00D2A0;   /* energinen aksentti */
  --prio-korkea:     #FF4B5D;
  --prio-keskitaso:  #FF883E;
  --prio-matala:     #00D2A0;
}}
* {{ box-sizing:border-box; }}
body {{ font-family:'Montserrat',-apple-system,sans-serif; margin:0;
       background:var(--sg-light-green); color:var(--sg-grey-700); }}

/* ── Hero ── */
header {{ background:var(--sg-racing-green); color:var(--sg-white);
  padding:36px 24px 88px; }}
.hero {{ max-width:1360px; margin:0 auto; }}
h1 {{ font-weight:900; text-transform:uppercase; letter-spacing:-.02em;
  font-size:clamp(1.5rem, 3.5vw, 2.4rem); margin:0 0 6px; color:var(--sg-white); }}
h1 .date {{ color:var(--sg-green); }}
.hero .rule {{ width:64px; height:5px; background:var(--sg-green); margin:14px 0; border:0; }}
.sub {{ color:var(--sg-light-green); font-size:.82rem; line-height:1.6; max-width:900px; opacity:.9; }}

/* ── Työkalupalkki ── */
.toolbar {{ max-width:1360px; margin:-56px auto 20px; padding:0 24px; }}
.toolbar-inner {{ background:var(--sg-white); border-radius:18px;
  box-shadow:0 8px 28px rgba(5,26,5,.14); padding:16px 18px; }}
.tabs {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }}
.tabs button {{ font-family:inherit; font-weight:700; text-transform:uppercase;
  letter-spacing:.02em; font-size:.78rem; border:2px solid var(--sg-racing-green);
  background:var(--sg-white); color:var(--sg-racing-green);
  padding:9px 20px; border-radius:999px; cursor:pointer; transition:all .15s; }}
.tabs button:hover {{ background:var(--sg-light-green); }}
.tabs button.active {{ background:var(--sg-racing-green); color:var(--sg-white); }}
.filters {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; }}
.filters select, .filters input[type=search] {{ font-family:inherit; padding:8px 12px;
  border:1.5px solid var(--sg-grey-200); border-radius:10px; font-size:.82rem;
  background:var(--sg-white); color:var(--sg-grey-700); }}
.filters input[type=search] {{ flex:1; min-width:180px; }}
.filters select:focus, .filters input:focus {{ outline:2px solid var(--sg-green); border-color:transparent; }}
.only-new {{ display:flex; align-items:center; gap:6px; font-size:.8rem; font-weight:600;
  color:var(--sg-racing-green); accent-color:var(--sg-racing-green); }}

/* ── Ruudukko ── */
main {{ max-width:1360px; margin:0 auto; padding:0 24px 40px; }}
.count {{ font-size:.8rem; font-weight:600; color:var(--sg-grey-700); margin:4px 2px 14px; }}
#list {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:18px; }}

/* ── Kortti ── */
.card {{ background:var(--sg-white); border-radius:16px; overflow:hidden;
  display:flex; flex-direction:column; box-shadow:0 2px 10px rgba(5,26,5,.07);
  border-top:5px solid var(--sg-grey-200); transition:transform .15s, box-shadow .15s; }}
.card:hover {{ transform:translateY(-3px); box-shadow:0 10px 24px rgba(5,26,5,.14); }}
.card.korkea    {{ border-top-color:var(--prio-korkea); }}
.card.keskitaso {{ border-top-color:var(--prio-keskitaso); }}
.card.matala    {{ border-top-color:var(--prio-matala); }}
.card.is-new    {{ box-shadow:0 0 0 2.5px var(--sg-green), 0 2px 10px rgba(5,26,5,.07); }}
.thumb {{ position:relative; width:100%; height:118px; overflow:hidden;
  background:var(--sg-racing-green); }}
.thumb svg {{ width:100%; height:100%; display:block; }}
.thumb .contour {{ fill:none; stroke:var(--sg-light-green); stroke-width:1.4; opacity:.20; }}
.thumb .contour.accent {{ stroke:var(--sg-green); opacity:.55; }}
.thumb .green-blob {{ fill:#0C5C33; opacity:.85; }}
.thumb .bunker {{ fill:var(--sg-grey-200); opacity:.35; }}
.thumb .stick {{ stroke:var(--sg-light-green); stroke-width:2; }}
.thumb .flag {{ fill:var(--sg-green); }}
.thumb .cat {{ position:absolute; left:14px; bottom:10px; color:var(--sg-light-green);
  font-size:.66rem; font-weight:900; text-transform:uppercase; letter-spacing:.09em; }}
.card-body {{ padding:14px 16px 16px; display:flex; flex-direction:column; flex:1; }}
.meta {{ font-size:.68rem; color:var(--sg-grey-700); opacity:.85; margin-bottom:6px;
  text-transform:uppercase; letter-spacing:.03em; font-weight:600; }}
.card h3 {{ margin:0 0 4px; font-size:.95rem; font-weight:700; line-height:1.35; }}
.card h3 a {{ color:var(--sg-racing-green); text-decoration:none; }}
.card h3 a:hover {{ text-decoration:underline; }}
.orig {{ font-size:.72rem; color:var(--sg-grey-700); opacity:.65; font-style:italic; margin:0 0 6px; }}
.card p.sum {{ margin:2px 0 10px; font-size:.82rem; line-height:1.5; flex:1; }}
.tag {{ display:inline-block; background:var(--sg-light-green); color:var(--sg-racing-green);
  font-size:.66rem; font-weight:700; padding:3px 10px; border-radius:999px; margin:0 5px 4px 0; }}
.new-badge {{ display:inline-block; background:var(--sg-green); color:var(--sg-dark-green);
  font-size:.62rem; font-weight:900; letter-spacing:.05em; padding:2px 8px;
  border-radius:999px; margin-left:6px; vertical-align:middle; }}

/* ── Lähdeterveys & footer ── */
details {{ margin-top:36px; background:var(--sg-white); border-radius:16px; padding:16px 20px; }}
summary {{ cursor:pointer; color:var(--sg-racing-green); font-weight:700;
  text-transform:uppercase; font-size:.8rem; letter-spacing:.03em; }}
table {{ width:100%; border-collapse:collapse; font-size:.78rem; margin-top:12px; }}
th {{ text-align:left; color:var(--sg-racing-green); }}
th, td {{ padding:6px 8px; border-bottom:1px solid var(--sg-grey-200); }}
.err {{ color:var(--prio-korkea); }}
footer {{ background:var(--sg-racing-green); color:var(--sg-light-green);
  text-align:center; font-size:.75rem; padding:26px 16px; margin-top:44px; }}
footer strong {{ color:var(--sg-white); text-transform:uppercase; letter-spacing:.04em; }}
footer .tag-line {{ color:var(--sg-green); font-weight:700; margin-top:4px; }}
</style></head><body>

<header><div class="hero">
  <h1>Golfliiton mediakatsaus <span class="date">{today}</span></h1>
  <hr class="rule">
  <div class="sub">{run_summary.get('new_articles', 0)} uutta artikkelia tässä ajossa ·
  {new_since_last} uutta edellisen ajon jälkeen{prev_line} ·
  {len(articles)} artikkelia raportissa (viim. {config.REPORT_DAYS} pv) ·
  AI-käännökset ja -tiivistelmät ovat luonnoksia — tarkista faktat ennen jatkokäyttöä.</div>
</div></header>

<div class="toolbar"><div class="toolbar-inner">
  <div class="tabs">
    <button data-tab="golfliitot" class="active">Golfliitot maailmalla</button>
    <button data-tab="urheilu_liitot">Suomalaiset lajiliitot</button>
  </div>
  <div class="filters">
    <select id="prio">
      <option value="">Kaikki prioriteetit</option>
      <option value="korkea">🔴 Korkea</option>
      <option value="keskitaso">🟡 Keskitaso</option>
      <option value="matala">🟢 Matala</option>
    </select>
    <select id="theme"><option value="">Kaikki teemat</option></select>
    <select id="country"><option value="">Kaikki maat</option></select>
    <input id="search" type="search" placeholder="Hae otsikoista ja tiivistelmistä…">
    <label class="only-new"><input type="checkbox" id="onlyNew"> Näytä vain uudet</label>
  </div>
</div></div>

<main>
  <div class="count" id="count"></div>
  <div id="list"></div>

  <details>
    <summary>Lähteiden tila viimeisimmässä ajossa</summary>
    <table><thead><tr><th>Lähde</th><th>Tapa</th><th>Artikkeleita</th><th>Huomiot</th></tr></thead>
    <tbody id="health"></tbody></table>
  </details>
</main>

<footer>
  <strong>Suomen Golfliitto ry</strong> · Hiomotie 3, 00380 Helsinki · golf.fi<br>
  Automaattinen mediamonitorointi · generoitu {today}
  <div class="tag-line">#muntapapelata</div>
</footer>

<script>
const ARTICLES = {data_json};
const HEALTH = {health_json};
const THEMES = {themes_json};
const PRIO_ORDER = {{korkea:0, keskitaso:1, matala:2}};
let tab = "golfliitot";

const $ = id => document.getElementById(id);
const esc = s => (s||"").replace(/[&<>"]/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]));

function initFilters() {{
  THEMES.forEach(t => $("theme").insertAdjacentHTML("beforeend",
    `<option value="${{esc(t)}}">${{esc(t)}}</option>`));
  [...new Set(ARTICLES.map(a => a.country).filter(Boolean))].sort().forEach(c =>
    $("country").insertAdjacentHTML("beforeend", `<option value="${{esc(c)}}">${{esc(c)}}</option>`));
}}

function thumb(a) {{
  // Topografinen golfkenttä-kuvitus (brändipatterni) — variantti valitaan
  // deterministisesti, jotta sama artikkeli saa aina saman kuvituksen.
  const seed = ((a.category||"").length * 7 + (a.source_id||"").length * 3
                + (a.title_fi||a.title||"").length) % 4;
  const shift = [0, -60, -120, -30][seed];
  const flip = seed % 2 ? -1 : 1;
  return `<div class="thumb">
    <svg viewBox="0 0 400 118" preserveAspectRatio="xMidYMid slice">
      <g transform="translate(${{200 + shift}},59) scale(${{flip}},1) translate(-200,-59)">
        <path class="contour" d="M-30,105 C60,70 130,125 210,95 S330,45 430,80"/>
        <path class="contour" d="M-30,88 C70,55 140,108 220,80 S335,32 430,62"/>
        <path class="contour accent" d="M-30,71 C80,42 150,90 230,66 S340,20 430,45"/>
        <path class="contour" d="M-30,54 C90,30 160,72 240,52 S345,8 430,28"/>
        <path class="contour" d="M-30,37 C100,18 170,54 250,38 S350,-4 430,12"/>
        <ellipse class="green-blob" cx="292" cy="62" rx="44" ry="20"/>
        <ellipse class="bunker" cx="242" cy="92" rx="13" ry="5.5"/>
        <ellipse class="bunker" cx="345" cy="84" rx="9" ry="4"/>
        <line class="stick" x1="292" y1="62" x2="292" y2="26"/>
        <path class="flag" d="M292,26 l17,5.5 -17,5.5 z"/>
      </g>
    </svg>
    <span class="cat">${{esc(a.category||"uutinen")}}</span>
  </div>`;
}}

function render() {{
  const q = $("search").value.toLowerCase();
  const prio = $("prio").value, theme = $("theme").value, country = $("country").value;
  const onlyNew = $("onlyNew").checked;
  let items = ARTICLES.filter(a => a.tab === tab
    && (!prio || a.priority === prio)
    && (!theme || (a.themes||[]).includes(theme))
    && (!country || a.country === country)
    && (!onlyNew || a.is_new)
    && (!q || ((a.title_fi||"")+(a.title||"")+(a.summary_fi||"")).toLowerCase().includes(q)));
  // Tärkein signaali ensin: prioriteetti (punainen → keltainen → vihreä),
  // saman prioriteetin sisällä uudet edellä ja tuoreimmat päälle.
  items.sort((a,b) => (PRIO_ORDER[a.priority]??3)-(PRIO_ORDER[b.priority]??3)
    || (b.is_new - a.is_new)
    || (b.published||"").localeCompare(a.published||""));
  const newCount = items.filter(a => a.is_new).length;
  $("count").textContent = items.length + " artikkelia"
    + (newCount ? ` · ${{newCount}} uutta edellisen ajon jälkeen` : "");
  $("list").innerHTML = items.map(a => `
    <div class="card ${{a.priority||""}} ${{a.is_new ? "is-new" : ""}}">
      ${{thumb(a)}}
      <div class="card-body">
        <div class="meta">${{a.prio_emoji||""}} ${{esc(a.source_name)}}
          · ${{esc(a.country)}} · ${{esc(a.published||"pvm ei tiedossa")}}
          ${{a.category ? " · " + esc(a.category) : ""}}
          ${{a.is_new ? '<span class="new-badge">UUSI</span>' : ""}}</div>
        <h3><a href="${{esc(a.url||"#")}}" target="_blank" rel="noopener">${{esc(a.title_fi||a.title)}}</a></h3>
        ${{a.title_fi && a.title_fi !== a.title ? `<p class="orig">${{esc(a.title)}}</p>` : ""}}
        <p class="sum">${{esc(a.summary_fi||a.summary||"")}}</p>
        <div>${{(a.themes||[]).map(t => `<span class="tag">${{esc(t)}}</span>`).join("")}}</div>
      </div>
    </div>`).join("") || "<p>Ei artikkeleita valituilla suodattimilla.</p>";
}}

function renderHealth() {{
  $("health").innerHTML = HEALTH.map(h => `
    <tr><td>${{esc(h.source_name)}}</td><td>${{esc(h.method||"—")}}</td>
    <td>${{h.count}}</td><td class="${{h.count ? "" : "err"}}">${{esc(h.error||"")}}</td></tr>`).join("");
}}

document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {{
  document.querySelectorAll(".tabs button").forEach(x => x.classList.remove("active"));
  b.classList.add("active"); tab = b.dataset.tab; render();
}});
["prio","theme","country","onlyNew"].forEach(id => $(id).onchange = render);
$("search").oninput = render;

initFilters(); render(); renderHealth();
</script>
</body></html>"""


def write_report(articles: list[dict], healths: list[dict], run_summary: dict) -> str:
    html = generate_report(articles, healths, run_summary)
    tmp = config.REPORT_PATH.with_suffix(".html.tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(config.REPORT_PATH)   # atominen kirjoitus
    return str(config.REPORT_PATH)
