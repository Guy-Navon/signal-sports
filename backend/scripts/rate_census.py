"""Rate the fresh cohort as a CENSUS, fast — docs/tasks/RATING_SURFACE.md.

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts/rate_census.py build --out ../docs/qa/census_sample.json
    .venv\\Scripts\\python.exe scripts/rate_census.py serve --sample ../docs/qa/census_sample.json \\
                                                          --ratings ../docs/qa/census_ratings.json
    then open http://127.0.0.1:8765 and press 1-5 (u = undo, q = quit)

``build``
    Reads every RSS article published on/after ``--since`` (default 2026-08-01),
    scores it for ``--profile`` (default guy) exactly as feed_ground_truth does,
    and writes a census "sample": one stratum, weight 1.0, seeded shuffle. The
    engine's decision travels in the file for ``score`` — never for the rater.

``serve``
    A tiny local page over the census file. NO database access at all: the page
    is served from the sample JSON, and the only thing written is the ratings
    JSON, after every keypress. Re-running resumes; rated items are never
    re-asked. The browser receives title / subtitle / source / date and nothing
    else — the allow-list is ``census_rating.rater_view``.

Then score it with the existing tooling, unchanged:
    .venv\\Scripts\\python.exe scripts/feed_ground_truth.py score \\
        --ratings ../docs/qa/census_ratings.json --sample ../docs/qa/census_sample.json --live

Read-only against the corpus: no write transaction, no /api/dev/*, no
ALLOW_CORPUS_DB_RESET, no network.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from app.qa import census_rating as cr  # noqa: E402

DEFAULT_PORT = 8765


# ── build ─────────────────────────────────────────────────────────────────────

def cmd_build(args) -> None:
    # Imported here so `serve` never loads the app, the .env, or the DB engine.
    try:
        from dotenv import load_dotenv

        load_dotenv(_BACKEND / ".env", override=False)
    except ImportError:  # pragma: no cover
        pass
    from app.db.database import SessionLocal
    from app.repositories import article_repository, profile_repository
    from app.services.feed_service import active_engine, build_feed

    with SessionLocal() as session:
        articles = article_repository.get_rss_articles(session)
        feeds = {}
        for user_id in args.profile:
            profile = profile_repository.get_by_id(session, user_id)
            if profile is None:
                raise SystemExit(f"Profile '{user_id}' is missing from the corpus DB.")
            feeds[user_id] = build_feed(articles, profile, include_hidden=True, session=session)

    doc = cr.build_census(
        feeds,
        since=args.since,
        seed=args.seed,
        corpus_articles=len(articles),
        meta_extra={"engine": active_engine()},
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8", newline="")
    for user_id, block in doc["profiles"].items():
        n = block["strata"][cr.STRATUM]["population"]
        print(f"{user_id}: {n} fresh articles (since {args.since}) -> census, weight 1.0")
    print(f"wrote {out}")


# ── serve ─────────────────────────────────────────────────────────────────────

PAGE = """<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<title>Census rating — __PROFILE__</title>
<style>
  :root{color-scheme:light}
  body{margin:0;font-family:system-ui,"Segoe UI",Arial,sans-serif;background:#f6f5f2;color:#111;
       display:flex;flex-direction:column;min-height:100vh}
  header{display:flex;justify-content:space-between;padding:12px 24px;font-size:14px;color:#666;
         direction:ltr;font-variant-numeric:tabular-nums}
  main{flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 8vw 6vh}
  .src{font-size:15px;color:#777;margin-bottom:14px}
  h1{font-size:clamp(26px,3.4vw,44px);line-height:1.3;margin:0 0 18px;font-weight:700}
  .sub{font-size:clamp(17px,1.8vw,24px);line-height:1.5;color:#333;max-width:60ch}
  footer{padding:14px 24px 22px;border-top:1px solid #e3e1dc;display:flex;gap:10px;flex-wrap:wrap;
         justify-content:center;direction:ltr}
  .k{display:flex;align-items:center;gap:8px;padding:8px 14px;border-radius:8px;background:#fff;
     border:1px solid #ddd;font-size:15px;color:#333}
  .k b{display:inline-block;min-width:22px;text-align:center;padding:2px 6px;border-radius:5px;
       background:#222;color:#fff;font-family:ui-monospace,monospace}
  .k.u b,.k.q b{background:#888}
  .flash{position:fixed;inset:auto 0 40% 0;text-align:center;font-size:48px;font-weight:800;
         opacity:0;transition:opacity .25s;pointer-events:none;color:#1a7f37}
  .flash.on{opacity:.85;transition:none}
  .done{text-align:center;font-size:28px;color:#1a7f37}
</style></head><body>
<header><span id="prog">…</span><span id="rate">—</span></header>
<main id="main"><div class="src" id="src"></div><h1 id="title"></h1><div class="sub" id="sub"></div></main>
<div class="flash" id="flash"></div>
<footer>
  <span class="k"><b>5</b> push</span><span class="k"><b>4</b> high</span><span class="k"><b>3</b> feed</span>
  <span class="k"><b>2</b> low</span><span class="k"><b>1</b> hide</span>
  <span class="k u"><b>u</b> undo</span><span class="k q"><b>q</b> quit (all saved)</span>
</footer>
<script>
const KEYS={"5":"push","4":"high","3":"feed","2":"low","1":"hide"};
let items=[], i=0, total=0, ratedAtStart=0, busy=false;
const t0=Date.now(); let n=0;
const $=id=>document.getElementById(id);
function fmt(d){ if(!d) return ""; const x=new Date(d); return isNaN(x)?d:x.toLocaleString("he-IL",{dateStyle:"short",timeStyle:"short"}); }
function render(){
  const done=ratedAtStart+i;
  $("prog").textContent=`${done} / ${total}`;
  const secs=(Date.now()-t0)/1000; $("rate").textContent=n?`${(secs/n).toFixed(1)} s/article`:"—";
  if(i>=items.length){ $("main").innerHTML=`<div class="done">✓ הכל דורג ונשמר (${done}/${total}).<br><small>אפשר לסגור. הרץ score --live.</small></div>`; return; }
  const it=items[i];
  $("src").textContent=`${it.source||""} · ${fmt(it.published_at)}`;
  $("title").textContent=it.title||"";
  $("sub").textContent=it.subtitle||"";
}
function flash(txt){ const f=$("flash"); f.textContent=txt; f.classList.add("on"); setTimeout(()=>f.classList.remove("on"),60); }
async function post(url,body){ const r=await fetch(url,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body||{})}); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function rate(k){
  if(busy||i>=items.length) return; busy=true;
  try{ await post("/api/rate",{id:items[i].id,rating:KEYS[k]}); i++; n++; flash(KEYS[k]); render(); }
  catch(e){ alert("save failed: "+e.message); } finally{ busy=false; }
}
async function undo(){
  if(busy) return; busy=true;
  try{
    const r=await post("/api/undo");
    if(r.id){
      if(i>0 && items[i-1].id===r.id){ i--; }        // rated this session: step back
      else { items.splice(i,0,r.item); }              // rated in an earlier session: show it next
      ratedAtStart=r.rated_total-i; flash("undo"); render();
    }
  }
  catch(e){ alert("undo failed: "+e.message); } finally{ busy=false; }
}
document.addEventListener("keydown",e=>{
  if(e.repeat) return;
  if(KEYS[e.key]) rate(e.key);
  else if(e.key==="u"||e.key==="U"||e.key==="Backspace") undo();
  else if(e.key==="q"||e.key==="Q") $("main").innerHTML=`<div class="done">נשמר. אפשר לסגור את הטאב.</div>`;
});
fetch("/api/state").then(r=>r.json()).then(s=>{ items=s.pending; total=s.total; ratedAtStart=s.rated; render(); });
</script></body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    server: "_RatingServer"

    def log_message(self, *_):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, code: int = 200) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        srv = self.server
        if self.path in ("/", "/index.html"):
            html = PAGE.replace("__PROFILE__", srv.store.profile)
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        if self.path == "/api/state":
            with srv.lock:
                pending = [cr.rater_view(it) for it in srv.store.pending(srv.items)]
                return self._json({"total": len(srv.items), "rated": len(srv.store.ratings), "pending": pending})
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        srv = self.server
        try:
            if self.path == "/api/rate":
                body = self._read_json()
                with srv.lock:
                    if body.get("id") not in srv.by_id:
                        return self._json({"error": "unknown id"}, 400)
                    srv.store.rate(body["id"], body["rating"])
                    return self._json({"ok": True, "rated_total": len(srv.store.ratings)})
            if self.path == "/api/undo":
                with srv.lock:
                    undone = srv.store.undo()
                    item = cr.rater_view(srv.by_id[undone]) if undone else None
                    return self._json({"id": undone, "item": item, "rated_total": len(srv.store.ratings)})
        except ValueError as exc:
            return self._json({"error": str(exc)}, 400)
        self._send(404, b"not found", "text/plain")


class _RatingServer(ThreadingHTTPServer):
    # http.server defaults this to True; on Windows that lets a SECOND instance
    # bind the same port silently, and two servers on one ratings file is the one
    # failure this tool must not have. A stale server must make the new one fail.
    allow_reuse_address = False

    def __init__(self, addr, items: list[dict], store: cr.RatingsStore):
        super().__init__(addr, _Handler)
        self.items = items
        self.by_id = {it["id"]: it for it in items}
        self.store = store
        self.lock = threading.Lock()


def cmd_serve(args) -> None:
    sample = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    if args.profile not in sample["profiles"]:
        raise SystemExit(f"Sample has no profile {args.profile!r}: {list(sample['profiles'])}")
    items = sample["profiles"][args.profile]["items"]
    store = cr.RatingsStore(Path(args.ratings), seed=sample["meta"]["seed"], profile=args.profile)
    pending = store.pending(items)
    print(f"{args.profile}: {len(items)} in census, {len(store.ratings)} already rated, {len(pending)} to go", flush=True)
    print(f"ratings -> {store.path}  (saved after every keypress; Ctrl+C is safe)", flush=True)

    try:
        srv = _RatingServer(("127.0.0.1", args.port), items, store)
    except OSError as exc:
        raise SystemExit(
            f"port {args.port} is taken - a rating server is probably still running "
            f"from an earlier session. Use it, or stop it, or pass --port. ({exc})"
        )
    url = f"http://127.0.0.1:{args.port}/"
    print(f"open {url}   keys: 5 push / 4 high / 3 feed / 2 low / 1 hide / u undo / q quit", flush=True)
    if not args.no_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        print(f"\n{len(store.ratings)} rated, saved at {store.path}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="census sample over the fresh cohort")
    p_build.add_argument("--out", required=True)
    p_build.add_argument("--since", default=cr.DEFAULT_SINCE, help="YYYY-MM-DD cutoff (inclusive)")
    p_build.add_argument("--seed", type=int, default=cr.DEFAULT_SEED)
    p_build.add_argument("--profile", action="append", default=None,
                         help="repeatable; default guy only")
    p_build.set_defaults(func=cmd_build)

    p_serve = sub.add_parser("serve", help="local rating page over a census sample")
    p_serve.add_argument("--sample", required=True)
    p_serve.add_argument("--ratings", required=True)
    p_serve.add_argument("--profile", default="guy")
    p_serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    p_serve.add_argument("--no-browser", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    if args.cmd == "build" and not args.profile:
        args.profile = ["guy"]
    args.func(args)


if __name__ == "__main__":
    main()
