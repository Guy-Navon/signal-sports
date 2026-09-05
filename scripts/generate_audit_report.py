"""Generate the standalone audit artifact and tracked-code inventory.

Run from any directory: python scripts/generate_audit_report.py
Reads repository files only; never imports the application or opens its database.
The JSON is the editable report source. Outputs are committed review artifacts.
"""
from __future__ import annotations

import ast
import csv
import html
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "audits"
STEM = "2026-09-05"
LABELS = {"high": "גבוהה", "medium": "בינונית", "low": "נמוכה", "fixed": "תוקן", "next": "להמשך"}


def inventory():
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    ).decode("utf-8").split("\0")
    rows = []
    for name in sorted(set(names)):
        path = ROOT / name
        if not path.is_file() or path.suffix not in {".py", ".js", ".jsx", ".ts", ".mjs", ".cjs"}:
            continue
        source = path.read_text(encoding="utf-8-sig")
        syntax = "static inventory; lint/build scope configured separately"
        functions = ""
        broad_exceptions = ""
        if path.suffix == ".py":
            tree = ast.parse(source, filename=name)
            syntax = "Python AST parsed"
            functions = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree))
            broad_exceptions = sum(
                isinstance(n, ast.ExceptHandler)
                and (n.type is None or isinstance(n.type, ast.Name) and n.type.id == "Exception")
                for n in ast.walk(tree)
            )
        rows.append((name, len(source.splitlines()), syntax, functions, broad_exceptions))
    with (OUT / f"{STEM}-inventory.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["path", "lines", "scan", "python_functions", "broad_exception_handlers"])
        writer.writerows(rows)
    return rows


def markdown(data, rows):
    lines = [f"# {data['title']}", "", f"תאריך: {data['date']} · ברנצ: `{data['branch']}`", "",
             f"[פתיחת הדוח האינטראקטיבי]({STEM}.html) · [מקור JSON]({STEM}.json) · [מפת הקוד]({STEM}-inventory.csv) · [ראיות דפדפן]({STEM}-browser.json)", "",
             data["summary"], "", "## היקף ואמינות המסקנות", "", data["scope"], "",
             f"במיפוי הנוכחי: {len(rows)} קובצי קוד, {sum(r[1] for r in rows):,} שורות, כולל בדיקות ונתוני דמו.", ""]
    lines.extend(f"- {item}" for item in data["boundaries"])
    lines += ["", "## בדיקות", "", "| בדיקה | תוצאה |", "| --- | --- |"]
    lines.extend(f"| {item['name']} | {item['result']} |" for item in data["checks"])
    lines += ["", "פקודות לשחזור (הפעל כל פקודה מהתיקייה המצוינת):", ""]
    lines.extend(f"- **{item['name']}**: `{item['command']}`" for item in data["checks"])
    lines += ["", "## ממצאים ותיקונים", ""]
    for item in data["findings"]:
        lines += [f"### {item['id']} — {item['title']}", "",
                  f"**{LABELS[item['status']]} · חומרה {LABELS[item['severity']]}**", "",
                  f"**לפני / המצב שנותר:** {item['before']}", "",
                  f"**תיקון / הצעד המומלץ:** {item['after']}", "",
                  f"**ראיות וגבולות:** {item['evidence']}", "",
                  "קבצים: " + " · ".join(f"[{p}](../../{p})" for p in item["files"]), ""]
    lines += ["## תלויות שהוסרו", "", ", ".join(f"`{name}`" for name in data["removed_dependencies"]), "",
              "## איך מתקדמים", ""]
    for step in data["roadmap"]:
        lines += [f"### {step['step']}", "", step["action"], "", f"**תנאי סיום:** {step['done']}", ""]
    lines += ["## תחזוקת הדוח", "", "מקור התוכן הוא קובץ ה־JSON. ליצירה חוזרת:", "",
              "```powershell", "python scripts/generate_audit_report.py", "```", "",
              "הדוח הוא קובץ HTML עצמאי: אין צורך בשרת, בתוספים או בחיבור חיצוני. אפשר לחפש, לסנן, לפתוח פרטים ולהדפיס ל־PDF. ה־CSV הוא מיפוי סטטי, לא כיסוי שורות ולא אישור שכל קובץ נסקר ידנית.", ""]
    (OUT / f"{STEM}.md").write_text("\n".join(lines), encoding="utf-8", newline="")


def webpage(data, rows):
    e = html.escape
    cards = []
    for item in data["findings"]:
        links = " · ".join(f'<a href="../../{e(p)}"><bdi>{e(p)}</bdi></a>' for p in item["files"])
        cards.append(f'''<article data-status="{item['status']}" data-severity="{item['severity']}">
          <div class="tags"><span>{item['id']}</span><span class="{item['severity']}">חומרה {LABELS[item['severity']]}</span><span class="{item['status']}">{LABELS[item['status']]}</span></div>
          <h3>{e(item['title'])}</h3><p>{e(item['before'])}</p>
          <details><summary>התיקון, הראיות והקבצים</summary>
          <h4>מה השתנה / איך לטפל</h4><p>{e(item['after'])}</p>
          <h4>מה נבדק ומה זה מוכיח</h4><p>{e(item['evidence'])}</p>
          <div class="files">{links}</div></details></article>''')
    checks = "".join(f'<tr><th scope="row">{e(c["name"])}</th><td>{e(c["result"])}</td></tr>' for c in data["checks"])
    roadmap = "".join(f'<article><h3>{e(s["step"])}</h3><p>{e(s["action"])}</p><p class="done"><strong>תנאי סיום:</strong> {e(s["done"])}</p></article>' for s in data["roadmap"])
    boundaries = "".join(f'<li>{e(b)}</li>' for b in data["boundaries"])
    fixed = sum(f["status"] == "fixed" for f in data["findings"])
    page = '''<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Signal Sports · ביקורת קוד</title>
<style>
:root{color-scheme:dark;--bg:#0a1219;--panel:#111f2b;--text:#edf3f5;--muted:#a8b9c5;--line:#2a3e4b;--mint:#9be7cb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.8 system-ui,"Segoe UI",Arial,sans-serif}
main{max-width:1160px;margin:auto;padding:40px 24px 80px}a{color:var(--mint);text-underline-offset:4px;overflow-wrap:anywhere}
.eyebrow{font-size:12px;letter-spacing:3px;color:var(--mint)}h1{font-size:clamp(32px,5vw,58px);line-height:1.2;max-width:850px;margin:18px 0}
h2{font-size:26px;margin:40px 0 18px}h3{font-size:20px;line-height:1.45;margin:18px 0 10px}h4{margin:16px 0 4px}
p{margin:8px 0 16px}.lead{max-width:900px;font-size:19px;color:var(--muted)}.branch{direction:ltr;display:inline-block;font:14px ui-monospace,monospace;background:var(--panel);padding:7px 14px;border:1px solid var(--line);border-radius:30px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:30px 0}.stat{border-top:2px solid var(--mint);background:var(--panel);padding:18px}.stat b{display:block;font-size:32px}.stat span{color:var(--muted)}
.toolbar{display:flex;gap:12px;flex-wrap:wrap;align-items:end;background:var(--bg);padding:15px 0}.toolbar label{display:flex;flex-direction:column;font-size:13px;gap:5px}.toolbar label:first-child{flex:1;min-width:200px}
input,select,button{font:inherit;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 13px}button{cursor:pointer}button:hover{border-color:var(--mint)}:focus-visible{outline:2px solid var(--mint);outline-offset:3px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.grid article{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:24px;align-self:start}article[hidden]{display:none}
.tags{display:flex;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--muted)}.tags span{border:1px solid var(--line);padding:2px 9px;border-radius:20px}.tags .high{color:#ffb8a9}.tags .fixed{color:var(--mint)}.tags .next{color:#ffe0a1}
details{border-top:1px solid var(--line);padding-top:12px}summary{cursor:pointer;color:var(--mint)}.files{font-size:12px;margin-top:20px;line-height:2.2}.note{padding:20px;border-right:3px solid var(--mint);background:var(--panel)}
table{width:100%;border-collapse:collapse;background:var(--panel)}td,th{text-align:right;padding:14px;border-bottom:1px solid var(--line);vertical-align:top}th{font-weight:600;width:32%}.muted,footer{color:var(--muted)}.done{color:var(--mint)}footer{margin-top:40px;font-size:13px}
@media(max-width:700px){main{padding:24px 16px}.grid{grid-template-columns:1fr}.stats{gap:8px}.stat{padding:12px}.stat b{font-size:26px}td,th{padding:10px}}
@media print{:root{--bg:white;--panel:white;--text:#111;--muted:#444;--line:#ccc;--mint:#145d48;color-scheme:light}.toolbar,button{display:none}main{max-width:none;padding:0}.grid{display:block}.grid article{break-inside:avoid;margin-bottom:14px}a{color:#145d48}.stats{margin:15px 0}h1{font-size:32px}article[hidden]{display:block}}
</style><main>
<header><div class="eyebrow">SIGNAL SPORTS / ENGINEERING REVIEW</div><h1>פחות תקלות נסתרות.<br>יותר אמון במערכת.</h1>
<p class="lead">__SUMMARY__</p><span class="branch">fix/repository-audit · 2026-09-05</span>
<p class="muted">תיקונים בברנצ נפרד · ללא merge ל־main · ללא שינוי בקורפוס החי</p></header>
<div class="stats"><div class="stat"><b>__FIXED__</b><span>קבוצות ממצאים שתוקנו</span></div><div class="stat"><b>__FILES__</b><span>קובצי קוד במיפוי</span></div><div class="stat"><b>16</b><span>תלויות מיותרות הוסרו</span></div></div>
<nav><a href="#findings">הממצאים</a> · <a href="#checks">הבדיקות</a> · <a href="#roadmap">איך מתקדמים</a> · <a href="2026-09-05.md">Markdown</a> · <a href="2026-09-05.json">JSON</a> · <a href="2026-09-05-inventory.csv">מפת הקוד</a> · <a href="2026-09-05-browser.json">ראיות דפדפן</a></nav>
<h2>מה בדקנו, ומה אין להסיק</h2><div class="note"><p>__SCOPE__</p><ul>__BOUNDARIES__</ul></div>
<h2 id="findings">ממצאים, החלטות ותיקונים</h2>
<div class="toolbar"><label>חיפוש<input id="search" type="search" placeholder="למשל: משוב, מסד, Telegram"></label>
<label>מצב<select id="status"><option value="">הכול</option><option value="fixed">תוקן</option><option value="next">להמשך</option></select></label>
<label>חומרה<select id="severity"><option value="">הכול</option><option value="high">גבוהה</option><option value="medium">בינונית</option><option value="low">נמוכה</option></select></label>
<button id="expand">פתיחת כל הפרטים</button><button id="print">הדפסה / PDF</button></div>
<p id="count" role="status" class="muted"></p><div class="grid" id="cards">__CARDS__</div>
<h2 id="checks">ראיות בדיקה</h2><table><thead><tr><th>בדיקה</th><th>תוצאה</th></tr></thead><tbody>__CHECKS__</tbody></table>
<p class="muted">פקודות מלאות לשחזור בגרסת Markdown. build עבר אך עדיין מציג אזהרת bundle מעל 500KB; פירוט בממצא N02.</p>
<h2 id="roadmap">איך הייתי מקדם את הפרויקט</h2><p class="lead">השלב הבא הוא להוכיח שהפיד מועיל למשתמשים שונים, לסגור את אמינות המשוב, ואז להרחיב. לא להתחיל בשכתוב מלא של מנוע שכבר מחזיק חוזים ובדיקות.</p><div class="grid">__ROADMAP__</div>
<footer>נוצר ממקור JSON באמצעות scripts/generate_audit_report.py. הדוח עצמאי ואינו טוען ספריות, גופנים או נתונים משירות חיצוני. רשימת הקוד כוללת בדיקות וקובצי דמו; אינה מדד לכיסוי שורות.</footer>
</main><script>
const cards=[...document.querySelectorAll('#cards article')];
function filter(){const q=document.querySelector('#search').value.toLocaleLowerCase();const s=document.querySelector('#status').value;const v=document.querySelector('#severity').value;let n=0;for(const c of cards){c.hidden=!!((s&&c.dataset.status!==s)||(v&&c.dataset.severity!==v)||(q&&!c.textContent.toLocaleLowerCase().includes(q)));if(!c.hidden)n++}document.querySelector('#count').textContent=`מוצגים ${n} מתוך ${cards.length} ממצאים`}
for(const id of ['search','status','severity'])document.getElementById(id).addEventListener('input',filter);
document.querySelector('#expand').addEventListener('click',()=>{const items=cards.filter(c=>!c.hidden).map(c=>c.querySelector('details'));const open=items.some(d=>!d.open);items.forEach(d=>d.open=open);document.querySelector('#expand').textContent=open?'סגירת כל הפרטים':'פתיחת כל הפרטים'});
document.querySelector('#print').addEventListener('click',()=>window.print());
let printState=[];window.addEventListener('beforeprint',()=>{printState=cards.map(c=>c.querySelector('details').open);cards.forEach(c=>c.querySelector('details').open=true)});window.addEventListener('afterprint',()=>cards.forEach((c,i)=>c.querySelector('details').open=printState[i]));filter();
</script></html>'''
    for key, value in {"SUMMARY": e(data["summary"]), "FIXED": str(fixed), "FILES": str(len(rows)),
                       "SCOPE": e(data["scope"]), "BOUNDARIES": boundaries, "CARDS": "".join(cards),
                       "CHECKS": checks, "ROADMAP": roadmap}.items():
        page = page.replace(f"__{key}__", value)
    # newline="" keeps the LF above verbatim. Without it Python translates
    # to CRLF on Windows, which .gitattributes then normalises back — so a
    # plain regenerate would always dirty the tree.
    (OUT / f"{STEM}.html").write_text(page, encoding="utf-8", newline="")


def main():
    data = json.loads((OUT / f"{STEM}.json").read_text(encoding="utf-8"))
    rows = inventory()
    markdown(data, rows)
    webpage(data, rows)
    print(f"Generated HTML, Markdown and CSV: {len(rows)} code files, {sum(r[1] for r in rows):,} lines")


if __name__ == "__main__":
    main()
