"""HTML-raportin generointi: itsenäinen tiedosto, data upotettuna, suodatus selaimessa."""
import datetime
import json

from . import config

PRIO_EMOJI = {"korkea": "🔴", "keskitaso": "🟡", "matala": "🟢"}


def generate_report(articles: list[dict], healths: list[dict], run_summary: dict) -> str:
    today = datetime.date.today().strftime("%d.%m.%Y")
    for a in articles:
        a["prio_emoji"] = PRIO_EMOJI.get(a.get("priority") or "", "")

    data_json = json.dumps(articles, ensure_ascii=False).replace("</", "<\\/")
    health_json = json.dumps(healths, ensure_ascii=False).replace("</", "<\\/")
    themes_json = json.dumps(config.THEMES, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="fi"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Golfkatsaus {today}</title>
<style>
:root {{ --green:#003F20; --green2:#1a5c38; --bg:#f4f6f4; }}
* {{ box-sizing:border-box; }}
body {{ font-family:-apple-system,'Segoe UI',sans-serif; max-width:960px; margin:0 auto;
       padding:24px 16px; background:var(--bg); color:#222; }}
h1 {{ color:var(--green); font-size:1.5rem; margin:0 0 4px; }}
.sub {{ color:#667; font-size:.85rem; margin-bottom:16px; }}
.tabs {{ display:flex; gap:8px; margin:16px 0 12px; flex-wrap:wrap; }}
.tabs button {{ border:1px solid var(--green); background:#fff; color:var(--green);
  padding:8px 18px; border-radius:20px; cursor:pointer; font-size:.9rem; font-weight:600; }}
.tabs button.active {{ background:var(--green); color:#fff; }}
.filters {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; align-items:center; }}
.filters select, .filters input {{ padding:7px 10px; border:1px solid #ccc; border-radius:8px;
  font-size:.85rem; background:#fff; }}
.filters input {{ flex:1; min-width:180px; }}
.card {{ background:#fff; border-left:5px solid #ccc; border-radius:10px;
  padding:12px 16px; margin-bottom:10px; }}
.card.korkea {{ border-left-color:#c1121f; }}
.card.keskitaso {{ border-left-color:#e0a800; }}
.card.matala {{ border-left-color:#2a9d8f; }}
.meta {{ font-size:.72rem; color:#888; margin-bottom:4px; }}
.card h3 {{ margin:0 0 2px; font-size:.95rem; }}
.card h3 a {{ color:var(--green); text-decoration:none; }}
.card h3 a:hover {{ text-decoration:underline; }}
.orig {{ font-size:.76rem; color:#999; font-style:italic; margin:0 0 4px; }}
.card p.sum {{ margin:4px 0 0; font-size:.86rem; color:#444; }}
.tag {{ display:inline-block; background:#e8f0ea; color:var(--green2); font-size:.7rem;
  padding:2px 8px; border-radius:10px; margin:6px 4px 0 0; }}
.count {{ color:#667; font-size:.8rem; margin:8px 0; }}
details {{ margin-top:32px; background:#fff; border-radius:10px; padding:12px 16px; }}
summary {{ cursor:pointer; color:var(--green); font-weight:600; }}
table {{ width:100%; border-collapse:collapse; font-size:.8rem; margin-top:10px; }}
th, td {{ text-align:left; padding:5px 8px; border-bottom:1px solid #eee; }}
.err {{ color:#c1121f; }}
footer {{ color:#aab; font-size:.72rem; text-align:center; margin-top:36px; }}
</style></head><body>

<h1>🏌️ Golfliiton mediakatsaus — {today}</h1>
<div class="sub">{run_summary.get('new_articles', 0)} uutta artikkelia tässä ajossa ·
{len(articles)} artikkelia raportissa (viim. {config.REPORT_DAYS} pv) ·
AI-käännökset ja -tiivistelmät ovat luonnoksia — tarkista faktat ennen jatkokäyttöä.</div>

<div class="tabs">
  <button data-tab="golfliitot" class="active">Golfliitot maailmalla</button>
  <button data-tab="golfmediat">Golfmediat &amp; muut</button>
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
</div>

<div class="count" id="count"></div>
<div id="list"></div>

<details>
  <summary>Lähteiden tila viimeisimmässä ajossa</summary>
  <table><thead><tr><th>Lähde</th><th>Tapa</th><th>Artikkeleita</th><th>Huomiot</th></tr></thead>
  <tbody id="health"></tbody></table>
</details>

<footer>Automaattinen mediamonitorointi · Suomen Golfliitto · generoitu {today}</footer>

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

function render() {{
  const q = $("search").value.toLowerCase();
  const prio = $("prio").value, theme = $("theme").value, country = $("country").value;
  let items = ARTICLES.filter(a => a.tab === tab
    && (!prio || a.priority === prio)
    && (!theme || (a.themes||[]).includes(theme))
    && (!country || a.country === country)
    && (!q || ((a.title_fi||"")+(a.title||"")+(a.summary_fi||"")).toLowerCase().includes(q)));
  items.sort((a,b) => (PRIO_ORDER[a.priority]??3)-(PRIO_ORDER[b.priority]??3)
    || (b.published||"").localeCompare(a.published||""));
  $("count").textContent = items.length + " artikkelia";
  $("list").innerHTML = items.map(a => `
    <div class="card ${{a.priority||""}}">
      <div class="meta">${{a.prio_emoji||""}} <strong>${{esc(a.source_name)}}</strong>
        · ${{esc(a.country)}} · ${{esc(a.published||"pvm ei tiedossa")}}
        ${{a.category ? " · " + esc(a.category) : ""}}</div>
      <h3><a href="${{esc(a.url||"#")}}" target="_blank" rel="noopener">${{esc(a.title_fi||a.title)}}</a></h3>
      ${{a.title_fi && a.title_fi !== a.title ? `<p class="orig">${{esc(a.title)}}</p>` : ""}}
      <p class="sum">${{esc(a.summary_fi||a.summary||"")}}</p>
      ${{(a.themes||[]).map(t => `<span class="tag">${{esc(t)}}</span>`).join("")}}
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
["prio","theme","country"].forEach(id => $(id).onchange = render);
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
