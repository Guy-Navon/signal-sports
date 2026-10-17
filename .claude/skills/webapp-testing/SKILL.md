---
name: webapp-testing
description: Use when a Signal Sports frontend change must be seen or checked in a real browser - rendered layout, RTL, focus, overflow, console errors, screenshots. Start with the existing hermetic harness (npm run capture:orbit in frontend/); ad-hoc Playwright scripts are scratchpad-only exploration and never a committed or competing test suite.
license: Complete terms in LICENSE.txt
---

# Web Application Testing

## Signal Sports adaptation (read first; overrides the upstream text below where they differ)

Local adaptation of anthropics/skills `webapp-testing` (Apache-2.0). **Modification notice:** this
file was changed for Signal Sports on 2026-10-17 (new frontmatter description and this adaptation
section); the rest of the directory is unmodified. Provenance in [UPSTREAM.md](UPSTREAM.md).

**Reuse before you build — in this order:**
1. **`npm run capture:orbit`** (in `frontend/`) — the existing hermetic harness
   (`frontend/scripts/capture-orbit-production.mjs`). It starts its own Vite on a free port in
   local-data mode, proves it is talking to that instance, drives headless Chrome over CDP and
   asserts what the browser paints: RTL, horizontal overflow at desktop and mobile viewports, focus
   transitions under both motion preferences, dock occlusion, typography, filter latency, queue
   paging. It writes review PNGs to a temp directory. If your change touches something it checks,
   run it. If a new *guarantee* deserves automation, extend this harness (and its `.test.mjs`) as
   a normal product change through `signal-pr-open` — don't start a second suite.
2. **Manual verification steps** per `signal-pr-finish` (route, data mode `local` vs `backend`, what
   to look for) when automation cannot reach the state — auth screens, Guy's phone, live data.
3. **Ad-hoc Playwright** (the upstream workflow below) only for one-off investigation. Scripts and
   screenshots live in the session scratchpad, never in the repo. Playwright is **not** a repo
   dependency: if you need it, install it into a throwaway venv inside the scratchpad
   (`python -m venv <scratch>\pw`, then `<scratch>\pw\Scripts\pip install playwright` and
   `<scratch>\pw\Scripts\python -m playwright install chromium`) and say that you did. Never add
   Playwright, jsdom or a component-testing stack to `frontend/package.json` or
   `backend/requirements*` — the repo deliberately has none (docs/FRONTEND_DESIGN_SYSTEM.md §10).

**Signal specifics for any browser check**
- Default to local-data mode (`npm run dev`). Backend mode needs the API on 127.0.0.1:8000 pointed
  at a copy or snapshot, never the live corpus — and don't click feedback buttons against real
  data (it contaminates later QA; see `signal-real-data-qa`, "Learning interference").
- Check 1440×1000, 390×844 and 320×640; `<html dir="rtl" lang="he">`; no horizontal overflow;
  Hebrew headlines with embedded English names and numbers; very long headlines; loading, empty
  and error states (`web-design-guidelines` has the full UI checklist).
- Prove you are looking at the right app: the harness once "passed" against a foreign server that
  owned a fixed port. Use an ephemeral port and confirm page identity before asserting anything.
- `scripts/with_server.py` on Windows: it starts servers with `shell=True`, so `terminate()` may
  stop the shell but leave the Node/Vite child running. Afterwards, check the port and stop only
  processes you started. Replace the `/tmp/...` and `/mnt/user-data/...` example paths with
  scratchpad paths.
- Never point a browser at the hosted site or use real credentials.
- **Read a bundled script before running it.** This overrides the upstream advice below to treat
  scripts as black boxes and run `--help` without reading the source. `with_server.py` is short,
  and running unread code is not acceptable in this repo.

---

*Upstream text follows (lightly edited; see UPSTREAM.md).*

To test local web applications, write native Python Playwright scripts.

**Helper Scripts Available**:
- `scripts/with_server.py` - Manages server lifecycle (supports multiple servers)

**Always run scripts with `--help` first** to see usage. DO NOT read the source until you try running the script first and find that a customized solution is abslutely necessary. These scripts can be very large and thus pollute your context window. They exist to be called directly as black-box scripts rather than ingested into your context window.

## Decision Tree: Choosing Your Approach

```
User task → Is it static HTML?
    ├─ Yes → Read HTML file directly to identify selectors
    │         ├─ Success → Write Playwright script using selectors
    │         └─ Fails/Incomplete → Treat as dynamic (below)
    │
    └─ No (dynamic webapp) → Is the server already running?
        ├─ No → Run: python scripts/with_server.py --help
        │        Then use the helper + write simplified Playwright script
        │
        └─ Yes → Reconnaissance-then-action:
            1. Navigate and wait for networkidle
            2. Take screenshot or inspect DOM
            3. Identify selectors from rendered state
            4. Execute actions with discovered selectors
```

## Example: Using with_server.py

To start a server, run `--help` first, then use the helper:

**Single server:**
```bash
python scripts/with_server.py --server "npm run dev" --port 5173 -- python your_automation.py
```

**Multiple servers (e.g., backend + frontend):**
```bash
python scripts/with_server.py \
  --server "cd backend && python server.py" --port 3000 \
  --server "cd frontend && npm run dev" --port 5173 \
  -- python your_automation.py
```

To create an automation script, include only Playwright logic (servers are managed automatically):
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True) # Always launch chromium in headless mode
    page = browser.new_page()
    page.goto('http://localhost:5173') # Server already running and ready
    page.wait_for_load_state('networkidle') # CRITICAL: Wait for JS to execute
    # ... your automation logic
    browser.close()
```

## Reconnaissance-Then-Action Pattern

1. **Inspect rendered DOM**:
   ```python
   page.screenshot(path='/tmp/inspect.png', full_page=True)
   content = page.content()
   page.locator('button').all()
   ```

2. **Identify selectors** from inspection results

3. **Execute actions** using discovered selectors

## Common Pitfall

❌ **Don't** inspect the DOM before waiting for `networkidle` on dynamic apps
✅ **Do** wait for `page.wait_for_load_state('networkidle')` before inspection

## Best Practices

- **Use bundled scripts as black boxes** - To accomplish a task, consider whether one of the scripts available in `scripts/` can help. These scripts handle common, complex workflows reliably without cluttering the context window. Use `--help` to see usage, then invoke directly. 
- Use `sync_playwright()` for synchronous scripts
- Always close the browser when done
- Use descriptive selectors: `text=`, `role=`, CSS selectors, or IDs
- Add appropriate waits: `page.wait_for_selector()` or `page.wait_for_timeout()`

## Reference Files

- **examples/** - Examples showing common patterns:
  - `element_discovery.py` - Discovering buttons, links, and inputs on a page
  - `static_html_automation.py` - Using file:// URLs for local HTML
  - `console_logging.py` - Capturing console logs during automation