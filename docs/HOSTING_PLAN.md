# Hosting Plan — Signal Sports off the owner's machine

**Status: PROPOSAL under owner review. Version 3, 2026-10-13.** Nothing here is implemented.
No server was created, nothing was bought, no DNS record was touched, no provider was switched
and no remote issue was edited. **The recommendation is a proposal. The owner has not approved
it as a decision.**

v3 is a correction round on v2 (same date) after the owner's review. It closes assumptions,
contradictions and cost errors without restarting the study or widening the architecture.
**§20 lists every material fix.**

It covers milestone 13 (#261–#270). The proposed changes to those issues are in §17 and were not
applied. When the plan is implemented, the living contract becomes `docs/DEPLOYMENT.md` and this
file is retired.

**Evidence tags:**

| Tag | Meaning |
|---|---|
| **[M]** | measured read-only on the owner's PC, on the local corpus, or in public DNS, 2026-10-12/13 |
| **[C]** | checked in this repository's code or config |
| **[O]** | official provider page, checked 2026-10-13 (§19) |
| **[T]** | third-party page, lower confidence, never presented as official |
| **[E]** | engineering estimate |
| **[A]** | unverified; §18 says how to check it |

**Money:**
- Every price is in its **original currency, and that currency is what's owed.**
- Conversions use the **ECB reference rates of 12 Oct 2026** [O], for orientation only:
  **€1 = $1.1181 = ₪3.432**, so **$1 ≈ ₪3.0695**.
- Prices **exclude tax**. Tax appears as scenarios in §11.2, not as a bound.

---

## 0. Summary

- **The requirement is unchanged** (§1). Both the running system *and* development leave the
  weak PC, which stays an access station only.
- **First relief, about a day of work: stop Ollama.**
  - The code **already contains a Gemini provider** [C], so the first switch can be
    configuration only (`gemini-3.1-flash-lite`). It still has to pass a bounded smoke test and
    an accuracy check first (§10.4).
  - The Groq path needs the new provider from #261 (4–8 h [E]).
- **Topology: a conditional recommendation, not a decision.**
  - **Start with B.** A Hetzner **CX23** (€5.99/month with IPv4, excl. tax) runs prod on Docker
    Compose, and **GitHub Codespaces** is the dev environment. Codespaces costs $0 up to
    **60 running hours a month on GitHub Free** (90 on Pro).
  - **A** (one CX33 for prod and dev, €8.99) **wins when** dev *running* hours, which include
    agent runs and idle tails, regularly exceed **~79/month on GitHub Free (~109 on Pro)**. It
    also wins when long unattended agent runs and persistent processes matter more than isolation
    (§5.5).
  - **B is the reversible start.** Hetzner can rescale a CX23 to a CX33 **while keeping the
    disk**, which keeps a later downgrade possible [O]. B → A is therefore a rescale plus a dev-user
    setup, not a migration.
- **The domain `guynavon.net`:** phase one uses the Tailscale `ts.net` address and needs **no DNS
  change**. Attach `signal.guynavon.net` **after** the cutover, as a private name, and only if the
  owner approves a DNS change (§4).
- **The cheapest realistic option isn't $0.**
  - A GCP e2-micro costs **≈ $3.65/month** for its public IPv4 [O].
  - IPv6-only doesn't work: four of the five sources, plus GitHub, GHCR and B2, publish no IPv6
    address [M].
  - It also needs a 1 GB RAM load test before anyone relies on it (§6).
- **Runtime: Compose for prod.** k3s *would* fit a 4 GB prod-only VM: its 2 GB figure is a sizing
  minimum, and the measured upstream usage is ~1.6 GB. One runtime on the critical path is enough
  (§7).
- **Deploy:** CI builds the images. The owner deploys **from the PC** with a separate
  forced-command SSH identity. **No dev environment holds a prod credential** (§9).
- **Data:**
  - Full backups are encrypted to an offline key and uploaded with a **write-only** key [O].
  - Dev gets a separate, **sanitized** snapshot that keeps IDs and relations, encrypted to a
    separate dev key.
  - **Dev can never decrypt a full backup** (§12).
- **Decisions needed to start** (§18):
  - the LLM path for T1, and its key
  - your GitHub plan and payment-method state, plus a Codespaces budget
  - B or A
  - the backup target, and who holds the offline key

---

## 1. The requirement (unchanged) and what v3 does not assume

1. **Offload the weak PC, including development.** The PC is an Intel i5-6500, 4C/4T, 16 GB [M].
   It stays an access station: the VS Code UI, a browser, SSH and light tasks.
2. The live system runs without the PC.
3. Development, tests and runs happen remotely.
4. Cost is low and predictable.
5. The corpus, the ratings and every other piece of data that can't be re-fetched are preserved
   (§12.1).
6. Dev and prod are separated in practice.
7. Nothing waits for the pilot (#253) or for product readiness.

**v3 does not assume:**

- **how many hours you develop.** Costs are shown for 20, 60, 80 and 120 *running* hours, and
  the recommendation is conditional (§5).
- that owning `guynavon.net` means exposing anything publicly
- which registrar, DNS provider or existing services the domain has
- that a free tier stays free, or that a usage scenario is a spending cap

---

## 2. Findings from the project itself

F1–F16 come from v2 and were re-checked; corrections are in bold. F17–F22 are new.

| # | Finding | Tag |
|---|---|---|
| F1 | **The running system** is the API (`uvicorn app.main:app`) plus **one** worker (`python -m app.worker`). Each 5-minute cycle runs ingestion, clustering, notification planning and dispatch, results sync, and retention (disabled). The frontend is a static build | [C] |
| F2 | **Tests and tools.** Backend tests are hermetic: a temp DB, the LLM off, Telegram secrets emptied, the insecure bypass off. **Corpus-dependent tools** all open the DB through `SessionLocal`, so they need a real copy with the original article IDs and profile rows:<br>• the N05 gate (`scripts/feed_ground_truth.py gate`)<br>• `rate_census.py`<br>• `corpus_rerun_diff.py`<br>• `feed_milestone_quality.py`<br>• the `apply_*` scripts, which write | [C] |
| F3 | CI: the frontend checks take ~11 s and backend pytest 148 s | [M] |
| F4 | **Live footprint:**<br>• worker working set 147 MB<br>• DB 37 MB + 4 MB WAL, ~13 KB per article, **≈ +0.7 GB a year** with retention off<br>• cycle duration median 3 s, p95 37 s, max 71 s (with Ollama)<br>• 35–46 LLM calls a day, ~1,300 tokens each | [M] |
| F5 | On the PC: VS Code (UI and server, 16 processes) 2.7 GB; Claude Code 486 MB | [M] |
| F6 | `scripts/worker.ps1` and many docstrings are Windows-specific. The code is cross-platform | [C] |
| F7 | No Dockerfile, no deploy directory and no lock file (`requirements.txt` has lower bounds only, #198). CI runs tests only | [C] |
| F8 | SQLite WAL, `busy_timeout=30000`, `timeout=30`. Two writer processes share one file, and WAL needs a local filesystem | [C] |
| F9 | **Writers:**<br>• the API: sessions, feedback, profile changes, calibration, manual ingestion and backfills<br>• the worker: cycles<br>• the `apply_*` scripts<br>The lease serializes cycles **on one DB file only**. Results sync has no lease (#197) | [C] |
| F10 | API and worker both run `init_db()` at startup: `create_all`, then additive `ALTER TABLE ADD COLUMN` under `BEGIN IMMEDIATE`, forward-only. **Additive migrations let old code *start* on a newer DB. They don't make a rollback safe, because data written under new semantics can still mislead old code** (§12.5) | [C] |
| F11 | SIGTERM stops the worker after the current cycle. A killed cycle leaves the lease held for up to 30 min (`SCHEDULER_STALE_AFTER_SECONDS=1800`). `SCHEDULER_MAX_RUN_SECONDS=900` caps a cycle | [C] |
| F12 | The dispatcher sends whenever `TELEGRAM_NOTIFICATIONS_ENABLED` is true and a token and chat id are set, **including from a copy of the DB** | [C] |
| F13 | The corpus guard protects `<backend>/data/signal_sports.db`, by path only | [C] |
| F14 | **Only on the PC:** the corpus DB, `backend/data/backups/` (277 MB), `backend/.env` and its backups (secrets), the worker logs and the Claude Code memory. **`calib.py`, the #237 fit/held-out tool, is now preserved outside the temp folder** (§12.6) | [M] |
| F15 | **PII and secrets in the DB:**<br>• `users.email` and `users.password_hash` (Argon2)<br>• `auth_sessions`: token hashes and user agents<br>The Telegram token and chat id live in env, not in the DB. `profiles`, `feedback_events` and `calibration_responses` reference users **by id**. A dev copy must therefore keep the user rows and scrub their fields. **v2's "auth tables stripped" would have broken those relations** | [C] |
| F16 | Preliminary: all five sources returned fresh content to a fetcher in a non-Israeli datacenter, which was not the target host | [M]-prelim |
| F17 | **LLM providers in the code:** `disabled`, `fake`, `gemini` and `ollama`.<br>• The Gemini provider uses JSON mode (`response_mime_type="application/json"`) without a schema, `temperature=0`, `max_output_tokens=500`, and one retry on a 429.<br>• Its default model, `gemini-2.5-flash-lite`, is now restricted to past users [O], so `CLASSIFICATION_MODEL` must be set.<br>• There is **no Groq or OpenAI-compatible provider yet** (#261) | [C] |
| F18 | **No app-side LLM budget:** nothing caps the calls or tokens per cycle or per day | [C] |
| F19 | **Live clustering doesn't use Ollama.** The cycle uses `LexicalFrequencyValidator`; the Ollama-backed `LocalModelValidator` appears only in offline evaluation scripts | [C] |
| F20 | **Auth:**<br>• Login is rate-limited (HTTP 429).<br>• The admin is bootstrapped from `AUTH_ADMIN_EMAIL` and `AUTH_ADMIN_PASSWORD`.<br>• **`/signup` is open, with no flag to close it.** v2's `AUTH_SIGNUP_ENABLED=false` doesn't exist; #265 proposes it | [C] |
| F21 | **IPv6 (AAAA records):**<br>• none for `rss.walla.co.il`, `www.israelhayom.co.il`, `www.sport5.co.il`, `api.one.co.il`, `github.com`, `ghcr.io` or `api.backblazeb2.com`<br>• present for `www.ynet.co.il`, `api.groq.com`, `generativelanguage.googleapis.com` and `api.telegram.org` | [M] |
| F22 | Backup compression, measured on a 35.2 MB copy: gzip 3.78 MB, xz 2.09 MB | [M] |

---

## 3. Screening

| Option | Verdict | Reason |
|---|---|---|
| Keep running on the PC | ✗ | Contradicts requirement 1 |
| **LLM off the PC only (T1)** | ✓ as the first step | Removes the heaviest load. It doesn't meet the full requirement |
| Red Hat Developer Sandbox | ✗ | A 30-day trial, and pods are deleted after 12 hours [O] |
| Managed OpenShift | ✗ | Enterprise pricing |
| **Hetzner CX23 / CX33 (x86)** | ✓ | The lowest stable price found [O] |
| Hetzner CAX (Arm) | ✗ | Dearer than x86 since 15 Jun 2026 [O], and a rescale can't change architecture [O] |
| **GCP e2-micro** | ✓ conditional | ≈ $3.65/month for the IPv4 [O] and 1 GB RAM. Needs a load test (§6.1) |
| Oracle A1 Always Free | variant | $0 including a public IPv4 [O], with reclamation and capacity risks (§6.2) |
| Trials and credits | ✗ | They expire |
| Lightsail, Fly.io, Render, Railway, Northflank | ✗ | Less RAM per dollar, or sleeping services [O]/[T] |
| Static frontend plus a backend elsewhere | ✗ | Cross-site cookie problems [E], and nothing gets cheaper |
| Managed Postgres | ✗ | An engine change with no reason behind it (#198) |
| **GitHub Codespaces (dev)** | ✓ | §5.3 |
| A Hetzner dev VM by the hour | not pursued | A server is billed while it exists, even powered off [O]. It needs a snapshot and a delete every session |
| Gitpod/Ona, Coder, DevPod | not evaluated | — |

**Market claim, stated carefully:** **among the options checked**, no stable VPS with at least
2 GB RAM was found below the CX23's price. v2's "no VPS under $5" was broader than the
evidence.

---

## 4. Access and the domain (`guynavon.net`)

### 4.1 Reachable vs authorized

These are two separate questions:

- **Reachability:** can a device get to the address at all?
- **Authorization:** may that device use the app?

The app always has its own login (USER_PLATFORM). The network layer decides who can even see
that login page. A name that resolves publicly is not permission to use the app, and owning a
domain is not a reason to expose anything.

### 4.2 Facts that constrain the choice

- **The domain:** `guynavon.net` is owned (owner-stated).
  - Its registrar, DNS provider, existing records and services are **unknown** [A].
  - Renewal is an existing cost, outside this plan.
  - **There is no authorization to change DNS records or nameservers.**
- **Tailscale certificates and Funnel:**
  - Tailscale issues HTTPS certificates **only for `<machine>.<tailnet>.ts.net`**. Custom domains
    are not supported, and the names are published in Certificate Transparency logs [O].
  - **Tailscale Funnel**, which exposes a service publicly, works only on `ts.net` names and ports
    443, 8443 and 10000. It is beta, its bandwidth limits are non-configurable, and it has **no
    visitor authentication** [O].
- **Cloudflare:**
  - A Tunnel's public hostname needs the zone on Cloudflare with a **full setup**, meaning
    Cloudflare's nameservers. The partial (CNAME) setup is for Business and Enterprise plans only
    [O].
  - Zero Trust (Access) is free for up to 50 users [O].
  - The CDN terms let Cloudflare limit free-plan use that mainly serves video or large files [O].
    This app serves HTML, JS and JSON.
- **The app today:** `/signup` is open (F20), so a publicly reachable app would let anyone create
  an account until #265 closes it.

### 4.3 The four paths

| | 1. Tailscale address only | 2. Custom domain, private | 3. Public domain + access layer | 4. Public app, own auth |
|---|---|---|---|---|
| URL | `https://signal.<tailnet>.ts.net` | `https://signal.guynavon.net` | `https://signal.guynavon.net` | `https://signal.guynavon.net` |
| DNS | none (MagicDNS) | an A record at the current DNS provider → the node's tailnet IP (100.x), plus ACME TXT records | (a) Cloudflare Tunnel: **move the nameservers to Cloudflare**; (b) self-hosted: an A record → the VM's public IPv4 | an A record → the public IPv4 |
| TLS | automatic, by Tailscale (`ts.net` only) | ACME **DNS-01**, because HTTP-01 can't reach a private address. The server needs a DNS-API token | (a) Cloudflare's edge certificate; (b) ACME HTTP-01 | ACME HTTP-01 |
| Who can reach it | tailnet devices (ACLs) | tailnet devices. The name resolves for anyone, but 100.x is unreachable off the tailnet | anyone reaches the access layer; only allowed identities get past it | anyone reaches the app's login and `/signup` |
| Phone | the Tailscale app connected | the Tailscale app connected | any browser, no VPN, plus the access-layer login | any browser |
| Extra cost | $0 | $0 | $0 on free Zero Trust [O]; (b) $0 plus upkeep | $0 plus upkeep |
| Complexity | lowest; already documented (`MOBILE_REMOTE_ACCESS.md`) | medium: the token's scope, renewals, and a public record that reveals the name and a 100.x address | high: (a) moving every DNS record of the domain; (b) ports 80/443 open plus an auth proxy to maintain | high: a public attack surface, a CSRF and cookie review for a public origin, signup closed first, a patch cadence |
| DNS change needed | **no** | yes | yes (a: nameservers) | yes |
| Status | **phase one** | after the cutover, if approved | only if VPN-free phone access becomes a need | future only |

### 4.4 Recommendation: attach the domain *after* the cutover

**At the cutover, use path 1.** Attach `signal.guynavon.net` as **path 2** after the observation
period (T4), and only when the owner has:

1. named the DNS provider
2. confirmed it has an API the ACME client supports, with a token as narrow as the provider allows
   (ideally limited to the `_acme-challenge` records)
3. approved the two records

Why after:

- The cutover then depends on no DNS change, no new credential and no certificate path to debug.
- Changing the hostname later means updating `CSRF_ALLOWED_ORIGINS` and the cookie settings,
  and logging in again, because cookies are host-scoped [C].

**`dev.signal.guynavon.net` isn't needed.**

- In B, the dev servers are reached through Codespaces port forwarding, which is private by
  default and behind a GitHub login [A: phone use untested].
- In A, VS Code forwards the dev ports to the PC over SSH.
- A dev hostname would only add a second certificate and a second cookie origin.

### 4.5 Private-access settings (every path)

- **Tailscale node:** tag it `tag:prod`. Key expiry is disabled by default for tagged devices [O].
- **Serve:** Tailscale Serve points at the local web listener only. Whether `--bg` survives a
  reboot is unverified [A].
- **Never use Funnel.**
- **Firewall and recovery:**
  - A Hetzner Cloud Firewall with no inbound rules. That Tailscale still connects is
    unverified [A].
  - Recovery goes through the Hetzner console plus an emergency SSH key.
- **Cookies and CSRF:**
  - Prod sets `CSRF_ALLOWED_ORIGINS` to the prod origin, and `AUTH_COOKIE_SECURE=true`.
  - If dev is ever served on the same hostname (A), it uses a different `AUTH_COOKIE_NAME`.

---

## 5. A vs B, re-compared

### 5.1 The two topologies

- **A — one VM.**
  - Host: a Hetzner **CX33** (4 vCPU, 8 GB [T]) at €8.49 + €0.50 IPv4 = **€8.99/month** [O].
  - Prod runs in Compose. A `dev` Linux user is opened with VS Code Remote-SSH over Tailscale,
    and Claude Code runs on the VM as `dev`.
  - To keep the downgrade option, **create a CX23 and rescale it up, keeping its 40 GB disk** [O].
    40 GB is ample (§8).
- **B — two places.**
  - Prod host: a Hetzner **CX23** (2 vCPU, 4 GB [T]) at €5.49 + €0.50 = **€5.99/month** [O], prod
    only.
  - Dev: a GitHub codespace (2-core, 8 GB RAM, 32 GB [O]), defined by
    `.devcontainer/devcontainer.json` on the default image plus features.

### 5.2 Working experience

| | A: one VM | B: CX23 + Codespaces |
|---|---|---|
| Persistent environment | Always on. Files, processes and tmux sessions last until you stop them | **Files persist** across stop and start; **processes stop** with the codespace. A **rebuild** keeps only `/workspaces`. An inactive codespace is **deleted** after the retention period: default 30 days, maximum 30 [O] |
| Claude Code login and memory | In `~/.claude` and `~/.claude.json` on the VM [O]. Set up once | **Resume** (start a stopped codespace): the home directory is intact, so login and memory are as you left them [O].<br>**Rebuild:** both are lost unless relocated under `/workspaces`, with `autoMemoryDirectory` and `CLAUDE_CONFIG_DIR` [O]. Whether `~/.claude.json` follows `CLAUDE_CONFIG_DIR` is unverified [A].<br>**New codespace:** log in again and copy the memory once (`gh codespace cp`, or a private dotfiles repo) |
| Long processes | Survive a disconnect (tmux) | Run only while the codespace runs. The idle timeout is 30 min by default, 240 at most [O]. Terminal output counts as activity [O], but community reports are inconsistent when no client is connected [T], so **test unattended runs before relying on them** |
| An agent working while you're away | Free: the VM has a flat price | Every running hour counts. An unattended 3-hour agent run uses 3 running hours, plus the idle tail after it ends |
| Quota blocking | None | Once the free quota (or the budget) is used up, you **can't create or resume** codespaces until the next cycle or a higher budget. Work in progress can still be exported to a branch [O]. What happens to an already-running codespace is undocumented [A] |
| Isolation | Same kernel and host as prod. User separation, no sudo, no docker group and slices (§9.2). **An agent with a shell on the prod host is the main residual risk** | Separate machines. The codespace holds no prod credential and isn't on the tailnet |
| Setup and upkeep | Dev user, slice limits, a disk limit, VS Code Server, and toolchain updates on the prod host: **6–10 h** setup [E], ~1–2 h/month [E] | The devcontainer: **2–4 h** [E]. GitHub maintains the dev VM, and the prod host stays minimal: ~0.5–1 h/month [E] |
| Switching later | A → B: write the devcontainer, then rescale down to a CX23. That works **only if the disk was kept at 40 GB** [O] | B → A: rescale the CX23 to a CX33, keeping the disk (likely a power-off [A]), then add the dev user: 6–10 h [E] |
| Monthly cost | €8.99, flat | €5.99 + Codespaces by running hours (§5.4) |

### 5.3 Codespaces facts behind the comparison

All [O] unless tagged otherwise.

- **Free quota, per month, for codespaces billed to the personal account:**
  - **GitHub Free:** 120 core-hours plus 15 GB-month of storage
  - **GitHub Pro:** 180 core-hours plus 20 GB-month
  - On a 2-core machine that is **60 h (Free) or 90 h (Pro)**; on a 4-core, 30 h or 45 h.
  - Codespaces billed to an organization don't use the personal quota.
- **Over the quota:** $0.18/h on a 2-core, $0.36/h on a 4-core, and $0.07 per GB-month.
- **Compute bills running time, not your attention.** A codespace is billed until it stops,
  including the idle time before the timeout. So:

  **running hours = attended hours + unattended agent hours + one idle tail per session +
  start-up**

  Each session's idle tail is 30 min by default, unless you stop the codespace by hand.
- **Storage counts every existing codespace, running or stopped:**
  - what it counts: the repo, data, extensions, prebuilds and **custom** dev-container images
  - what it doesn't: containers based on the **default image**, even with dev-container features
    added
  - so: use the default image plus features, with no prebuilds at first. Check on the billing page
    that the image isn't counted [A].
- **Lifecycle:**
  - Stop and start keep the saved changes.
  - A rebuild keeps only `/workspaces`.
  - Deleting a codespace loses everything that wasn't pushed.
  - Retention deletes a codespace that stays inactive for the retention period.
- **Spending controls:**
  - **With no payment method on file,** usage is blocked when the quota runs out. That is a real
    $0 ceiling.
  - **With a payment method,** the control is a **Codespaces budget with "Stop usage when budget
    limit is reached".** Once the budget or quota is used up, you can no longer create or resume
    codespaces billed to the account. Without the stop option, a budget only sends alerts.
  - **What to set:** a budget on the Codespaces product, for the amount you accept above the quota
    (for example $0, or $5 ≈ 27 paid 2-core hours), with stop usage on and alerts at 75%, 90% and
    100%.
  - **What it guarantees:** no create and no resume once the limit is reached.
  - **What it doesn't promise (undocumented, [A]):**
    - that a running codespace stops at that moment
    - a cent-exact cap, given reporting delays
    - anything about the storage of existing codespaces, which keeps accruing until you delete
      them

### 5.4 Cost by running hours, and the break-even

2-core codespace, excl. tax. B = €5.99 (≈ $6.70) + compute.

| Running hours a month | 20 | 60 | 80 | 120 |
|---|---|---|---|---|
| Codespaces compute, GitHub Free | $0 | $0 | $3.60 | $10.80 |
| Codespaces compute, GitHub Pro | $0 | $0 | $0 | $5.40 |
| **B total, Free** | ≈ $6.70 (₪20.6) | ≈ $6.70 | ≈ $10.30 (₪31.6) | ≈ $17.50 (₪53.7) |
| **B total, Pro** | ≈ $6.70 | ≈ $6.70 | ≈ $6.70 | ≈ $12.10 (₪37.1) |
| **A** (hours change capacity, not cost) | ≈ $10.05 (₪30.9) | ≈ $10.05 | ≈ $10.05 | ≈ $10.05 |

**From human hours to running hours** (examples [E]):

| Month | Attended | Unattended agent | Idle tails (30 min) | **Running** |
|---|---|---|---|---|
| Light | 12 sessions × 1.5 h = 18 h | 4 h | 6 h | **28 h** |
| Regular | 20 × 2 h = 40 h | 10 h | 10 h | **60 h** |
| Heavy | 25 × 3 h = 75 h | 25 h | 12.5 h | **112.5 h** |

Stopping the codespace by hand at the end of each session removes the idle-tail column.

**Two different thresholds:**

1. **Free-quota exhaustion: 60 h (Free) or 90 h (Pro).** Past it, B either costs $0.18 an hour
   or is blocked.
2. **A/B break-even: 78.6 h (Free) or 108.6 h (Pro).** A costs €3.00 ≈ $3.354 more, which buys
   18.6 paid 2-core hours.
   - With equal tax on both, the break-even doesn't move. If only Hetzner adds 18% VAT, it moves
     to ~82 h or ~112 h.
   - A **4-core** codespace halves the free hours (30 or 45 h) and moves the break-even to ~39 h
     or ~54 h. From F5, the 2-core with 8 GB is expected to be enough [E].

**Storage:** one codespace on the default image, with `.venv`, `node_modules`, caches,
extensions and a DB snapshot, comes to about 2–4 GB [E], which is inside 15 GB-month. Past the
quota it is cheap: 25 GB-month on Free costs 10 × $0.07 = $0.70.

### 5.5 When each wins

**B wins when:**
- most months stay under ~60 running hours (or under ~79, if small charges are acceptable)
- agent runs are mostly attended or short
- keeping agents off the prod host matters

It is also the better **first** step whenever the hours are unknown, because moving to A later
is a rescale, not a migration.

**A wins when:**
- running hours regularly exceed ~79 (Free) or ~109 (Pro), **or**
- long unattended agent runs, overnight dev processes and one persistent home for Claude Code
  are a normal part of the work, **or**
- you prefer a fixed price to watching a quota

…and in every case you accept the shared-host risk and the hardening work in §9.2.

**Below 60 h, cost doesn't decide it.** B is €3.00/month cheaper there, and the choice rests on
experience and isolation.

**Proposal (not a decision):**
1. Start with B.
2. Read the running hours on GitHub's usage page for one or two months.
3. Rescale to A if the A conditions appear.

---

## 6. Other hosts, corrected

### 6.1 C1 — GCP e2-micro (Always Free) plus Codespaces

- **Free:** one e2-micro (2 shared vCPUs, 0.25 sustained, 1 GB RAM) in us-west1, us-central1 or
  us-east1; 30 GB of standard disk; 1 GB/month of egress from North America [O].
- **Not free: the public IPv4.** An in-use external IPv4 on a standard VM costs $0.005/h, which is
  **≈ $3.65/month** [O]. v2's "$0" was wrong.
- **Cloud NAT costs more, not less:** $0.0014/h per VM, $0.045 per GiB processed, plus the NAT's
  own IPv4 at $0.005/h [O]. That adds up to at least $4.67/month.
- **IPv6-only can't work** (F21). Walla, Israel Hayom, Sport5 and the ONE API have no AAAA record,
  and neither do GitHub, GHCR and B2. Only Ynet, Groq, Gemini and Telegram do.
  - Reaching the rest would need NAT64 (Cloud NAT pricing again) or a proxy on another host.
  - **Tailscale doesn't help.** Its traffic still leaves the VM as egress, and an exit node would
    be another machine: the PC, which contradicts the requirement, or a paid host.
- **Egress counts everything the VM sends:** backup uploads, the UI over Tailscale, LLM and
  Telegram calls.
  - Nightly gzip backups alone grow from ~0.1 GB/month now to ~2.4 GB/month after a year (§12.2).
  - So the free 1 GB runs out within months. List-price egress then applies: small, and not
    re-checked [A].
- **The 1 GB RAM is an estimate** (§8: 0.65–1.0 GB), so **C1 is conditional on a load test.** Run
  API, worker, web and Tailscale for 48 h on real cycles. It passes only with:
  - no OOM kill
  - no sustained swap-in
  - a cycle p95 of 120 s or less
- **Billing:** a Cloud Billing account with a card is required, and budget alerts don't cap
  spending [O].
- **Cost:** ≈ $3.65 + egress (≈ $0 at first) = **≈ $3.70/month ≈ ₪11.4**, plus Codespaces as in B.

### 6.2 C2 — Oracle A1 Always Free

- **Resources:** 2 OCPU / 12 GB, 200 GB of block storage and 10 TB of egress [O]. **Public IPs
  are free, including reserved ones** [O].
- **Risks:**
  - Idle instances are reclaimed when CPU, network and memory all stay under 20% at p95 over
    7 days [O].
  - "Out of host capacity" is documented [O].
  - Whether pay-as-you-go accounts are exempt from reclamation is unverified [A].
- **Verdict:** $0, but **not realistic as prod's only home.** A reclaimed host looks exactly like
  the silent outages this milestone is meant to end. It could be a later experiment.

---

## 7. Runtime: Compose vs k3s (corrected)

| Aspect | Compose | k3s, single node |
|---|---|---|
| Memory and CPU | Docker plus containerd: ≈ 0.05–0.1 GB [E] | **Sizing minimum** for a server: 2 cores, 2 GB RAM [O]. That is a recommendation, not measured use.<br>**Upstream profiling:** a server with a workload uses **≈ 1.6 GB p95** and ~6% of a core (Intel, SQLite datastore, v1.26.5); an agent ≈ 275 MB [O].<br>**On a 4 GB prod-only VM** that leaves ≈ 2.4 GB for an app that needs about 1 GB (§8): **feasible** [E] |
| Restarts | `restart: unless-stopped`, plus Docker enabled at boot | the kubelet restarts pods; the k3s unit starts at boot |
| Deploy and rollback | Pin a digest, `docker compose up -d`; roll back to the previous digest | `kubectl set image` / `rollout undo` |
| Volumes | A **bind mount** survives `docker compose down -v` | local-path PVCs default to reclaim `Delete` |
| Moving parts | One network, one listener | Traefik, CoreDNS, Services, Ingress |
| Setup and upkeep | ~1–2 h, rare upgrades [E] | ~3–6 h, plus k3s upgrades [E] |
| Fit with the owner's OpenShift habit | lower | high |

**Proposed: Compose for prod**, for simplicity, urgency and upkeep. The reason is not that k3s
doesn't fit; it does.

- **One runtime on the critical path.** k3s doesn't run beside Compose in prod.
- k3s/OpenShift familiarity (#264) becomes a later, optional track, for example manifests
  validated in CI or a dev-only k3s. It never blocks the cutover.
- **On a single node, k3s adds no resilience** against losing the VM.

**Service design (kept from v2):**
- API and worker run as two services on one host bind mount.
- **A single worker** is enforced four ways:
  1. one worker service, never scaled
  2. the lease
  3. the rule that the PC never runs a worker after the cutover
  4. the dev guards
- The worker's `stop_grace_period` is `300s` (F11).

---

## 8. Resources

All [E], except the worker's figure (F4, [M]).

| Scenario | RAM | Fits |
|---|---|---|
| Live system only: OS, Docker, Tailscale, API, worker, web | **0.65–1.0 GB** | 1 GB tight (C1), 4 GB easily (B) |
| + a dev server (VS Code Server, Claude Code, dev API, Vite) | 2.0–3.5 GB | same-VM dev (A) only |
| + a test run and a build | 2.4–4.5 GB | |
| Realistic parallel peak, with an active agent | **3.2–5.2 GB** | 8 GB (A) |

**Disk:**
- The live system needs ~3–5 GB: images 0.6–1.0, the DB 0.04 (+0.7 a year), rotated logs, and
  local backups.
- Same-VM dev adds 3–5 GB.
- **A 40 GB disk is ample for A**, which is what makes "create a CX23, rescale with the disk
  kept" practical.

**Architecture:** x86, with single-arch amd64 images, to match CI, Codespaces [A: x86_64] and the
PC. Images are built in CI, never on the host.

---

## 9. Security and deploy

### 9.1 One deploy workflow, for A and B

| Identity | Where its key lives | What it can do |
|---|---|---|
| CI (GitHub Actions) | GitHub | Build, test, and push images to GHCR (`packages: write`). Nothing on the host |
| `deploy` (a host user) | **only the owner's PC**, as a separate key | Run one forced command: `deploy <sha>`, `rollback` or `status` |
| `admin` (a host user, with sudo) | the owner's PC, plus an offline emergency key | Provisioning, restores, break-glass |
| `dev` (A only) | the VM | Develop. No sudo, no docker group, no deploy |
| A codespace (B) | GitHub | Develop. **No prod credential**, not on the tailnet |

**The flow:**

1. Dev pushes a branch and opens a PR, and CI runs the tests.
2. The owner merges.
3. CI builds the image for the merge commit, labels it with the git sha, and pushes it to GHCR.
4. **The owner runs `ssh deploy@<prod> deploy <sha>` from the PC.**
5. The forced command (`restrict,command="/usr/local/sbin/signal-deploy"` in `authorized_keys`
   [A: standard OpenSSH options]):
   1. validates the sha and resolves its digest
   2. takes a backup
   3. pulls the image and runs `docker compose up -d`, with the worker's
      `stop_grace_period: 300s`
   4. waits for `/health`, the worker heartbeat and the next successful cycle (`cycle-ok`, §13)
   5. records the digest and the change's rollback class (§12.5)

**This replaces v2's "deploy over SSH from the codespace"**, which contradicted "no prod
credentials in dev".

- Agents in any dev environment can push branches. They can't merge to a protected `main`
  [A: verify the branch protection] and they can't deploy.
- **Deferred:** a GitHub Actions deploy job. It would need a prod credential and a tailnet key
  stored in GitHub, behind environment protection.

### 9.2 Hardening a shared host (A)

| Area | Setting |
|---|---|
| Users | `dev` (uid 1001) has no sudo and is **not in `docker`**, which is root-equivalent. It has no access to `/srv/signal/prod` or `/etc/signal` |
| Service identity | Containers run as a non-root service uid and gid (for example `user: "10001:10001"`), which no login user shares |
| Data ownership | `/srv/signal/prod/data` and `.../backups` are owned by `10001:10001` with mode `0700`. **Root-only isn't enough:** a non-root container couldn't write its own DB. The service uid owns the data, and `dev` gets no group access |
| Secrets | `/etc/signal/prod.env` is `root:root 0600`, read by `docker compose` running as root under the deploy command. Never in an image, in git or in the dev home |
| Docker socket | `root:docker 0660`. No container mounts it and there is no TCP API. If dev needs containers, it uses rootless Docker or Podman as `dev`, with its own socket and storage |
| Memory and CPU for everything dev runs | SSH sessions, the VS Code Server they start, Claude Code, tmux servers and `systemd-run --user` jobs all land in `user-1001.slice` [A: confirm once with `systemd-cgls`].<br>A drop-in at `/etc/systemd/system/user-1001.slice.d/limits.conf` sets `MemoryHigh=4G`, `MemoryMax=5G`, `MemorySwapMax=1G`, `CPUQuota=300%`, `TasksMax=4096` and `IOWeight=50` [E: tune] |
| Prod priority | Containers run under `system.slice`, outside dev's limits. Compose sets `mem_limit` and `cpus` per service, plus `oom_score_adj: -500` for the API and worker, so the kernel kills dev processes first |
| Disk | `/home/dev` on its own fixed-size filesystem (for example a 15 GB ext4 image), or ext4 user quotas, so dev can't fill the disk prod writes to. Docker log rotation and a journald size cap |
| What remains | One kernel and one VM: a kernel exploit, a host failure or a provider outage hits both. Dev can reach prod's local HTTP port, where the app's login still applies |

### 9.3 What the dev environment can reach

- **B:**
  - The codespace's `GITHUB_TOKEN` can push to the repo [A]. Branch protection on `main` (PR plus
    green CI, no force-push) is what limits it.
  - Its Codespaces secrets are only two: a capped LLM key for evaluations (§10.3) and the
    dev-snapshot key (§12.3).
- **A:** the same two secrets, as files in `/home/dev` with mode 0600.
- **Both:** `DEPLOY_ENV=dev` guards are proposed in #265: refuse Telegram, and refuse a DB path
  under the prod data dir. **They don't exist yet** [C].

---

## 10. LLM

### 10.1 What the code supports today

- The **Gemini** provider exists (F17). So the first attempt at T1 is a config change:
  - `CLASSIFICATION_PROVIDER=gemini`
  - `CLASSIFICATION_MODEL=gemini-3.1-flash-lite`
  - `CLASSIFICATION_API_KEY`
- **Groq** needs the #261 provider.
- Stopping Ollama doesn't affect live clustering (F19).

### 10.2 Candidates, re-checked 2026-10-13

| Candidate | Exact model | Status | JSON | Price per 1M tokens, in / out | Free tier | Hard cap | In code |
|---|---|---|---|---|---|---|---|
| **Gemini** | `gemini-3.1-flash-lite` | **stable**, updated May 2026 [O] | structured outputs supported [O]; the provider sends JSON mode without a schema [C] | $0.25 / $1.50 [O] | yes; limits shown per project, not published [O] | prepay at least $5, then **hard spend caps** at the tier and project level [O] | **yes**, once the model is set |
| **Groq** | `openai/gpt-oss-20b` | production [O] | strict JSON Schema [O] | $0.075 / $0.30 [O] | per **organization** and model: 30 RPM, 1K RPD, 8K TPM, 200K TPD [O] | spend controls undocumented [A] | no (#261) |
| Groq | `openai/gpt-oss-120b` | production [O] | strict [O] | $0.15 / $0.60 [O] | same | same | no (#261) |

**Excluded:**
- Groq `qwen/qwen3.8-27b` is a preview, "evaluation only" [O].
- Cloudflare Workers AI has no JSON mode for gpt-oss [O].
- OpenAI `gpt-5-nano` ($0.05 / $0.40 [O]) and Anthropic Haiku 5.5 ($0.10 / $0.50 [O]) are
  paid-only fallbacks and aren't evaluated by default.

**Data handling:**
- Gemini's free tier uses content to improve Google's products [O]. The inputs here are public
  headlines.
- Groq doesn't retain data by default, apart from up to 30 days for abuse monitoring [O].

**Thinking:** Gemini 3.1 Flash-Lite supports thinking, but its default level isn't documented
[O]. Under the provider's `max_output_tokens=500`, thinking tokens could cut the JSON off [E].
Stage 0 checks exactly that.

### 10.3 Separating dev from prod

Credentials, quotas and spend are different things, and a key separates only the first.

| Layer | What it separates | Supported way |
|---|---|---|
| Credentials | who can call, and revoking one side | a separate key per environment |
| Quota | who can starve whom | **Groq:** limits are per organization, so **another key in the same org shares the quota** [O]. A **project** for dev with custom per-model limits below the org's caps dev's share [O].<br>**Gemini:** a paid project with a hard spend cap [O] |
| Spend | dollars | Gemini: hard caps [O]. Groq: undocumented [A] |
| Local app limits | what our own code may send | Dev runs with `CLASSIFICATION_PROVIDER=disabled` unless it is evaluating. Evaluation scripts get a `--max-calls` bound (new, small). The dev worker stays off (F18) |

**Not proposed:** creating extra accounts, organizations or free projects to multiply free-tier
quotas.

### 10.4 A staged, bounded evaluation (#262)

| Stage | Sample | Bound | Passes when |
|---|---|---|---|
| **0 — smoke** | 30 census #2 headlines | ≤ 30 calls, ~1 h | • all 30 pass `parse_and_validate_llm_json`, with no truncation<br>• p95 latency ≤ 5 s<br>• tokens, including thinking/reasoning, are recorded |
| **1 — accuracy** | census #2's eligible rows (~225); or census #3 (#241) once rated, which was never used for the #237 fit | ≤ 225 calls | Compared with the stored Ollama facts on the same rows and with the owner's ratings:<br>• validation failures ≤ 2%<br>• **no new wrong push** for Guy or Deni<br>• feed+ recall and shown precision each no more than 3 pp below the Ollama baseline on the same rows<br>Big disagreements are re-rated before they count: on borderline rows, owner ratings repeat only about half the time (`qa/CENSUS_2026-10.md`) |
| **2 — a second candidate** | as stage 1 | ≤ 225 calls | Runs only if stage 1 fails or is borderline |
| **3 — live watch** | production | 48 h | • LLM-error fallbacks under 5% of LLM-eligible articles per day<br>• no 429 fallback streak longer than 1 h<br>• daily cost within 2× the estimate |

**Overall bound:** ~500 calls and ~$2 at most [E]. Stop at the first candidate that passes.

**Order:**
1. Gemini, which needs no code
2. Groq `gpt-oss-20b`, which needs #261
3. `gpt-oss-120b`, only if the 20b fails on accuracy

### 10.5 Cost scenarios: usage estimates, not caps [E]

Prod makes ~45 calls a day: ≈ 1.75M input and 0.1–0.5M output tokens a month.

| | Gemini 3.1 Flash-Lite | Groq 20b | Groq 120b |
|---|---|---|---|
| Prod, paid | $0.59–1.19 | $0.16–0.28 | $0.32–0.56 |
| Prod, free tier | $0 within its limits | $0 (~72K of 200K tokens/day) | $0 |
| A heavy dev month (1–10× the live volume) | +$0.6–12 | +$0.2–3 | +$0.3–6 |

A scenario becomes a cap only through a mechanism:
- Gemini's hard spend caps
- a Groq dev project's rate limits, which bound volume, not dollars
- the evaluation scripts' `--max-calls`

---

## 11. Costs

### 11.1 Line items

Original currency, excl. tax.

| Item | Price | Source |
|---|---|---|
| Hetzner CX23 | €5.49/month cap, €0.0088/h | [O] price list, effective 15 Jun 2026. Specs 2 vCPU / 4 GB / 40 GB / 20 TB [T] |
| Hetzner CX33 | €8.49/month, €0.0136/h | [O]. Specs 4 vCPU / 8 GB / 80 GB / 20 TB [T] |
| Hetzner Primary IPv4 | €0.50/month | [O] |
| Hetzner backups (optional) | 20% of the server price: €1.10 (CX23), €1.70 (CX33) | [O] |
| Hetzner snapshots | €0.0143/GB-month | [T] |
| Hetzner availability per location | — | [A]: the order flow |
| GitHub Codespaces | §5.3 | [O] |
| GitHub Actions and GHCR | free for a public repo and public packages | [O] |
| GCP e2-micro, 30 GB disk, 1 GB egress | $0 | [O] |
| GCP external IPv4 | $0.005/h ≈ $3.65/month | [O] |
| Oracle A1 plus a public IP | $0 | [O] |
| Tailscale Personal | $0 | [O] |
| healthchecks.io Hobbyist | $0, 20 checks | [O] |
| Backblaze B2 | first 10 GB free; $6.95/TB-month; free egress up to 3× the storage | [O] |
| Cloudflare R2 | 10 GB-month free; $0.015/GB-month; free egress | [O] |
| LLM | §10.2 | [O] |
| The domain `guynavon.net` | renewal is an existing cost | owner; outside this plan |

### 11.2 Tax and exchange rate

- **Prices are pre-tax.** Hetzner's exclude VAT [O]. GitHub, GCP and the LLM providers price in
  USD before tax.
- **Check before buying.** Whether, and which, tax applies to an Israeli private customer is
  unverified [A]. Read the **tax-inclusive total in the order or checkout flow before buying.**
  Waiting for an invoice isn't needed.
- **Scenarios, not bounds:**

  | Scenario | When | A (Hetzner) | B (Hetzner) |
  |---|---|---|---|
  | 0% | no tax collected | €8.99 | €5.99 |
  | 18% | Israeli VAT, collected or self-assessed | €10.61 | €7.07 |
  | 19% | German VAT, if Hetzner treats the account as EU | €10.70 | €7.13 |

- **FX:** the ECB rates of 12 Oct 2026 [O]. A card charge converts at the issuer's rate on the
  charge date, plus any fees, so shekel amounts are orientation only.

### 11.3 A, B and the cheapest realistic option

Per month, excl. tax.

| | A: one CX33 | B: CX23 + Codespaces | C1: GCP e2-micro + Codespaces (conditional) |
|---|---|---|---|
| **Base:** dev ≤ 60 running h, LLM on a free tier | **€8.99 ≈ $10.05 ≈ ₪30.9** | **€5.99 ≈ $6.70 ≈ ₪20.6** | **≈ $3.70 ≈ ₪11.4** |
| **Heavy dev month:** 120 running h; paid LLM (Groq 20b, up to ~$3, a scenario) | €8.99 + ~$3 ≈ $13.1 ≈ ₪40 | €5.99 + $10.80 + ~$3 ≈ $20.5 ≈ ₪63 (Pro: ≈ $15.1 ≈ ₪46) | ≈ $3.70 + $10.80 + ~$3 ≈ $17.5 ≈ ₪54 |
| **Conditional costs** | • tax (0–19%)<br>• Hetzner backups +€1.70<br>• object storage past 10 GB | • tax<br>• Hetzner backups +€1.10<br>• Codespaces storage past 15 GB-month at $0.07/GB<br>• a budget set above $0 | • egress past 1 GB at list price [A]<br>• no hard cap on the billing account<br>• failing the load test, which means B |

---

## 12. Data: backups, dev snapshots, restore

### 12.1 What can't be re-fetched

| Data | Tables | Recoverable without a backup? |
|---|---|---|
| Articles older than the sources' RSS windows (1–2 days), with their stored classification | `articles` | **No.** Recent ones would be re-fetched, but re-classified, possibly differently |
| Census and N05 rating files | `docs/qa/*.json` (git) | Yes, from git. **But they point at article ids that exist only in the DB** |
| Feedback | `feedback_events` | **No** |
| Calibration answers | `calibration_responses` | **No** |
| Live profiles, including reviewed `apply_*` changes and UI edits | `profiles` | Partly: the `apply_*` scripts are in git and can be re-run in order; UI edits can't |
| Accounts | `users` | By hand, but with new ids, which breaks the relations |
| Notification state: outbox, story members, watermarks | `notification_*` | **No.** An *older* copy can re-send or suppress pushes if Telegram is on |
| Source overrides (Sport5 on, ONE off) | `source_overrides` | By hand (`RSS_INGESTION.md`) |
| Clusters | `story_clusters`, `cluster_edges` | Only through a backfill, which the project treats as risky |
| Run history | `ingestion_runs`, `scheduler_cycles` | **No.** The acceptance metrics need it |
| Results | `game_results`, `results_sync_state` | Mostly re-fetchable from the provider |
| Sessions, the lease, worker status | `auth_sessions`, `scheduler_lease`, `worker_status` | Disposable |

### 12.2 Full backups

- **How:**
  1. Every night on the host: `VACUUM INTO` (or the backup API).
  2. gzip.
  3. `age`-encrypt to the **backup public key**.
  4. Upload to B2 with a **write-only** application key limited to the backup bucket [O].
  5. Ping `backup-ok`.
- **Key custody:** the backup private key stays offline (a password manager plus paper), **never
  on prod and never in dev.**
- **Why B2:** its application keys can be write-only, limited to one bucket and a name prefix [O].
  R2 tokens can't be write-only [O], so a compromised host holding an R2 token could delete the
  backups. B2's versioning, lifecycle and Object Lock defaults are unverified [A].
- **Schedule:** nightly (RPO ≤ 24 h). An optional 6-hourly tier kept for 48 h gives RPO ≤ 6 h.
- **Retention and storage (corrected):**
  - Daily 14 + weekly 8 + monthly 6 = **28 objects**, +6 if the 6-hourly tier is on.
  - Each object is ~3.8 MB with gzip today [M] and grows by ~6 MB a month (from +0.7 GB/year raw,
    F4) [E].
  - Total: **≈ 0.1 GB now, ≈ 1.0 GB at 6 months, ≈ 2.1 GB at 12 months**, about half that with xz
    [M]. That stays inside B2's free 10 GB for more than a year [E].
  - v2's "about 30 objects of about 10 MB" was wrong on both counts.
- **Before the cutover:** the PC's final DB and `backend/data/backups/` become a one-time
  pre-cutover archive, encrypted and uploaded.
- **The restore drill:** decrypt on the PC, then test in a scratch directory on the host, **never
  in dev** (§12.4).

### 12.3 Dev snapshots: a separate, sanitized path

| | Full backup | Dev snapshot |
|---|---|---|
| Content | the whole DB | a sanitized copy |
| Encrypted to | the backup key (offline) | **the dev key**: a separate `age` key, held by dev |
| Where it goes | the B2 bucket `signal-backup`; the prod key can only write | the B2 bucket `signal-devsnap`; the prod key can only write, and the dev key can read and list that bucket only. In A, a dev-readable directory on the host, with no bucket |
| Who can decrypt it | the owner, offline | dev |

**Dev never receives a key that decrypts a full backup.**

**Sanitization** runs on prod, as the service user, on a copy:

1. `VACUUM INTO` a temp file.
2. On that copy:
   - `DELETE FROM auth_sessions`
   - `UPDATE users SET email = 'user-' || id || '@example.invalid', password_hash = NULL,
     last_login_at = NULL`
   - clear `scheduler_lease` and `worker_status`, prod's runtime state
3. **Keep everything else**, ids included: `profiles`, `feedback_events`, `calibration_responses`,
   `notification_*`, `source_overrides`, and every article and cluster row.
4. `VACUUM INTO` the final file, so deleted values don't survive in free pages. Delete the temp
   file.
5. **Verify before upload:**
   - `PRAGMA integrity_check` returns ok, and `PRAGMA foreign_key_check` returns nothing
   - per-table counts match the source, except the cleared tables
   - no email outside `@example.invalid`, and no non-null `password_hash`
   - none of the real emails appears anywhere in the file's bytes
6. Encrypt to the dev key, upload, ping. Weekly, keeping the last 4.

**In dev:**

- **Login:** a dev admin from `AUTH_ADMIN_EMAIL` and `AUTH_ADMIN_PASSWORD` (F20), with an
  `@example.invalid` address. How that admin views the owner's profile in the console is to be
  settled in #270 [A].
- **These must work on the snapshot** (acceptance for #270), with every rated article id
  resolving:
  - `scripts/feed_ground_truth.py gate`
  - `rate_census.py review`
  - `corpus_rerun_diff.py`
- **Telegram stays off:** no token in any dev env (F12), plus the proposed `DEPLOY_ENV=dev` guard
  (#265).
- **Before prod is hosted** (T2 starts early), a one-time snapshot can be made on the PC with the
  same steps and copied into the codespace with `gh codespace cp`. It is a light task.

### 12.4 Restore procedure

1. **Rehearse on a copy first.**
   - **Decrypt on the PC,** where the offline key is used. The private key never goes to the host
     or to dev.
   - Run `integrity_check`, `foreign_key_check` and the row counts on the PC; these are light
     `sqlite3` commands.
   - Copy the decrypted file over the admin path into a scratch directory on the host. Start a
     second API container against it on another port, with `SCHEDULER_ENABLED=false`,
     `TELEGRAM_NOTIFICATIONS_ENABLED=false` and results sync off, and open the feed.
2. **Stop and block every writer.**
   - `docker compose stop worker api`; the worker finishes its cycle within the grace period.
   - Make sure no `apply_*` or maintenance container is running.
   - Pause the backup and snapshot timers.
   - Confirm that no process holds the DB files (`fuser`/`lsof` on the data dir).
3. **Swap the files as a set.** Move `signal_sports.db`, `-wal` and `-shm` **together** into
   `data/pre-restore-<timestamp>/`. Never delete them first.
4. **Put the restored file in place**, as `signal_sports.db`, owned by the service uid, mode 0600.
   **Make sure no old `-wal` or `-shm` is left beside it:** SQLite would try to apply a stale WAL
   to the wrong database.
5. **Start with side effects off.**
   1. Turn Telegram off before starting. The restored outbox and watermarks date from the restore
      point and could re-send or suppress pushes.
   2. Start the API, then the worker, and watch one cycle.
   3. Review the notification outbox.
   4. Only then restore the previous Telegram setting.
6. **Record the loss window:** everything written after the restore point (feedback, calibration,
   profile edits, `apply_*` runs). Re-apply what can be re-applied, for example by re-running the
   `apply_*` scripts in order.
7. **The undo path:** the quarantined set can be moved back, as a set.

RTO ≈ 1–2 h [E]; the RPO follows the schedule.

### 12.5 Rollback classes

Each PR states its class.

| Class | Example | Rollback |
|---|---|---|
| **1 — code only** | a scorer tweak, UI | Redeploy the previous digest |
| **2 — additive schema** | a new nullable column | The previous digest: old code ignores the column, and the new data in it stays |
| **3 — data semantics** | new values in an existing column; a changed `profile_v2` JSON shape; an `apply_*` or backfill that rewrites rows | **A code rollback alone leaves data the old code may misread.** Restore the pre-deploy backup and accept the loss window, or roll forward with a fix. A written plan is needed before the deploy |

### 12.6 `calib.py`

- **Preserved on 2026-10-13, outside the temp folder:**
  `%USERPROFILE%\Documents\signal-sports-preserved\2026-10-13\calib.py` on the PC (5,560 bytes), together
  with `census2_dis.py`, `SHA256SUMS.txt` and `SOURCES.txt` [M].
- **Checked:**
  - **no secrets**
  - it reads `docs/qa/census2_ratings.json`, `docs/qa/census2_sample.json`, and
    `data/signal_sports.db` opened read-only (`mode=ro`)
  - it uses `SEED_PROFILES` and `score_article_v2` [C]
  - **it was not run.**
- **Proposed integration (not done):**
  - move it to `backend/scripts/census_calibration_fit.py`
  - accept `--db` (default: the canonical path, read-only), `--ratings` and `--sample`
  - add a smoke test on a tiny fixture
  - link to it from `PREFERENCE_MODEL_V2.md` (census calibration, #237) and
    `qa/CENSUS_2026-10.md`

---

## 13. Monitoring and alerting

Four signals, kept separate:

| Check (healthchecks.io) | Pinged when | Period / grace | Catches | Safe at night? |
|---|---|---|---|---|
| `cycle-ok` | a cycle completes. `/fail` when a cycle errors [A: the endpoint's behaviour] | 5 min / 15 min | a dead worker, a down host, failing cycles | yes: cycles run all night |
| `sources-ok` | the cycle fetched ≥ 1 item, new or not, from at least one enabled source. `/fail` when every source failed | 5 min / 55 min | blocked or unreachable sources, DNS or egress failures | yes: feeds always list their latest items, even when nothing is new |
| `data-fresh` | at least one new article was stored | 1 h / 7 h | ingestion that runs but stores nothing | yes, thanks to the long grace |
| `backup-ok` | an off-host upload succeeded | 24 h / 6 h | failing backups | — |

- **Alive vs completed:** a worker that is alive but stuck stops pinging `cycle-ok`, since cycles
  are capped at 900 s (F11). Silence therefore covers both cases, and `/fail` tells "erroring"
  apart from "gone".
- **Natural quiet vs failure:** `sources-ok` doesn't depend on new articles, and `data-fresh` waits
  8 h, so a quiet night raises no alarm.
- **Detection time:** `cycle-ok` alerts **≤ 20 min** after the last good cycle. An explicit failure
  alerts at once.
- **Pings never fail a cycle:** they are outbound only, with a short timeout.
- **Alert channels:** email, plus optionally healthchecks' Telegram integration. That is a
  different bot from the app's pilot.

---

## 14. Sequence: four separate clocks

| Stage | Result | Work [E] | Elapsed | Needs | Done when |
|---|---|---|---|---|---|
| **T1 — Ollama off** | prod classifies through a hosted LLM; Ollama is stopped. **The first relief** | Gemini path: **1–3 h** (config plus stages 0–1). Groq path: + #261, 4–8 h | 1–5 days | one API key (owner) | 48 h on the hosted LLM pass stage 3 (§10.4), and no Ollama process is left |
| **T2 — remote dev** | edit, run and test without the PC | B: devcontainer, **3–6 h**. A: VM and dev user, 6–10 h | 1–3 days | B: nothing. A: the VM (just provisioned; prod hardening can wait) | one real change goes end to end (edit → tests → PR → CI) with no local stack |
| **T3 — prod cutover** | the live system runs on the host | images and lock 8–14, guards 3–5, monitoring 2–4, backups and drill 4–8, provisioning 3–5, source probe 1–2, cutover 3–5: **24–43 h** | 1–3 weeks | T1 recommended; the owner's decisions (§18) | the prerequisites below are green and the cutover steps are done |
| **T4 — observation** | proof of no PC dependency | ~15 min a day | **7 days** | T3 | §15 |

**Remote dev doesn't wait for prod hardening.** T1 and T2 can run in parallel, and T2 in B needs
no host at all. **No tens of hours are required before the first relief.**

**T3 prerequisites:**

- **A source probe from the host:** fetch-only, compared with the PC's worker for the same hour.
  HTTP 200 alone doesn't count.
- the four checks of §13, live
- a backup plus one restore drill on a copy
- the dev guards (#265)
- the lock file

**Cutover order:**

1. Stop the PC's worker.
2. Take a final PC backup (the pre-cutover archive).
3. Copy it to the host and start the host's worker.
4. Verify.
5. **The PC never runs a worker again.**

---

## 15. Acceptance criteria (hosting)

These are separate from the product pilot (#253) and run over T4: seven consecutive days.

- [ ] **No dependency on the PC.** No Signal process runs on it, and Ollama is gone. The PC may be
      switched on as an access station; that doesn't fail the test.
- [ ] **Cycles complete:**
  - ≥ 95% of the expected cycles (288 a day) complete each day
  - **and** no gap between completed cycles exceeds **30 min**, apart from one planned deploy
    window of ≤ 15 min a day
  - **and** an unplanned stop is **alerted within 20 min**, proven once by a deliberate stop
- [ ] **Cycle duration:** p95 ≤ 120 s each day, and no cycle reaches the 900 s cap. The PC
      baseline, with Ollama, was a p95 of 37 s [M].
- [ ] **Sources:**
  - `sources-ok` never alerts for a host-side reason
  - each enabled source has at least one successful fetch in every 3-hour window between 07:00 and
    24:00 Israel time
  - a source-side outage, verified from elsewhere, is logged but doesn't fail hosting
- [ ] **Freshness:** `data-fresh` doesn't alert, except during a verified natural quiet.
- [ ] **LLM:** LLM-error fallbacks stay under 5% of LLM-eligible articles a day.
- [ ] **Backups:** 7 of 7 nightly uploads, and one restore drill on a copy passes.
- [ ] **Phone access:** the feed and results open from the phone every day.
- [ ] **Dev stays safe:**
  - dev and tests never write to the live DB and never send real messages, and a test proves the
    guard refuses
  - in A, a pytest run plus a build during prod keeps prod's cycle p95 ≤ 120 s, with no prod OOM
    kill
- [ ] **Cost is known up front:** the tax-inclusive prices are recorded from the order flow or the
      billing console **before** buying, and the first week's usage in the consoles matches the
      plan within ±20%. No waiting for an invoice.
- [ ] **Promote and roll back were done once each,** on a class-1 change (§12.5).

---

## 16. Recommendation and a day in the life

**Proposed (not approved):**
1. **T1 now:** Gemini through the existing provider, with Groq as the fallback.
2. **Start B:** a CX23 plus Codespaces, on Compose and the `ts.net` address.
3. **Measure the running hours.**
4. **Rescale to A only if the A conditions of §5.5 appear.**
5. **The domain comes after T4.**

**B, a day:**

- **Morning:** on the phone, with Tailscale on, open `https://signal.<tailnet>.ts.net`. The PC
  isn't involved.
- **Evening:**
  1. On the PC, VS Code → "Codespaces: Connect" **resumes** yesterday's codespace. Files, the
     venv, the Claude Code login and its memory are as they were.
  2. Work with Claude Code: pytest takes 2–5 min, and Vite and uvicorn preview through a private
     forwarded port, which also opens on the phone after a GitHub login.
  3. **Stop the codespace by hand** when done, which saves the 30-minute idle tail. If an agent
     has to keep going, raise the timeout (up to 240 min) and accept that the codespace may still
     stop.
- **Shipping:** push → PR → CI → merge → `ssh deploy@<prod> deploy <sha>` from the PC. The next
  `cycle-ok` confirms it.
- **Monthly:** glance at the Codespaces usage page. The budget blocks create and resume at the
  limit.

**A, a day:**

- **Morning:** the same phone check.
- **Evening:**
  1. On the PC, VS Code → Remote-SSH as `dev@<prod>` over Tailscale.
  2. Yesterday's tmux sessions are still running, and Claude Code's memory lives on the VM.
  3. Leaving an agent running overnight costs nothing extra. The dev slice caps its memory and
     CPU, and prod keeps priority.
- **Shipping:** the same PR → CI → `ssh deploy@...` from the PC. The `dev` user can't deploy.
- **Monthly:** one `apt upgrade` covers both prod and the dev toolchain. Glance at the slice
  limits and the disk.
- **Felt risk:** a host problem takes prod and dev down together.

---

## 17. Proposed changes to issues #261–#270

These are proposals. **No remote issue was changed.**

| Issue | Proposal |
|---|---|
| #261 provider | **Keep and amend.**<br>• The Groq provider uses strict `json_schema`, `reasoning_effort=low` and per-call usage.<br>• Note that the existing Gemini provider covers T1's first attempt: set `CLASSIFICATION_MODEL`, and check thinking against `max_output_tokens` |
| #262 evaluate + switch | **Amend.** The staged evaluation of §10.4 replaces the 2×3 matrix:<br>• the order Gemini → Groq 20b → 120b<br>• the pass criteria<br>• the bounds |
| #263 containerize | **Amend:**<br>• Compose, amd64<br>• a bind mount<br>• the stop grace period<br>• the lock file<br>• deploy by digest through the forced-command `deploy` identity from the PC<br>• **remove k8s** from scope |
| #264 k8s/OpenShift | **Defer**, out of milestone 13 |
| #265 hosted safety | **Amend:**<br>• `DEPLOY_ENV=dev` guards<br>• a distinct cookie name per environment<br>• **a flag that closes `/signup`** (it doesn't exist yet, F20)<br>• every `ALLOW_*` refused in prod |
| #266 backups | **Amend:**<br>• a B2 write-only key<br>• `age` to an offline key<br>• nightly, with an optional 6-hourly tier<br>• retention 14/8/6<br>• the restore procedure of §12.4 and a drill<br>• `backup-ok`<br>• the separate dev-snapshot path (§12.3) |
| #267 host decision | **Rewrite.** The decision covers:<br>• the topology (start with B, or A)<br>• the GitHub plan and budget<br>• the LLM path<br>• the backup target and key custody<br>• the domain's timing |
| #268 provision | **Amend:**<br>• create a CX23, and rescale it keeping the disk if A<br>• firewall<br>• a tagged node<br>• Serve<br>• the A hardening of §9.2 |
| #269 cutover | **Amend:**<br>• acceptance per §15: 7 days, with thresholds<br>• the prerequisites and order of §14 |
| #270 QA without a local stack | **Amend:**<br>• sanitization keeps the ids (§12.3)<br>• the dev key<br>• the tools that must work on the snapshot<br>• no dev worker by default |

**New issues proposed:**

1. healthchecks pings: `cycle-ok`, `sources-ok`, `data-fresh`, `backup-ok`
2. the source probe from the host
3. the remote dev environment: a devcontainer, or a dev user with slices
4. a dependency lock, carved out of #198
5. Linux equivalents of the Windows-only scripts
6. integrating `calib.py` (§12.6)
7. `--max-calls` on the LLM evaluation scripts

---

## 18. Decisions to start, and what is still unverified

**The minimal set of decisions for T1 and T2.** The rest can wait.

1. **T1:** try the existing Gemini provider first, with Groq (#261) as the fallback, and **create
   the one API key** that path needs.
2. **GitHub:** confirm your plan (Free or Pro) and whether a payment method is on file. Then
   either choose a Codespaces budget amount, with stop usage on, or keep no payment method for a
   hard $0.
3. **Topology:** B as the reversible start (proposed), or A now.
4. **Backups:** B2 (proposed) or R2, and who keeps the offline `age` key.

**Not needed now:**
- the domain (default: after the cutover)
- the Hetzner location (any EU location)
- re-enabling Telegram (#251) and ONE (#258)

**Still unverified:**

| Item | How to check |
|---|---|
| Hetzner availability per location; the tax-inclusive price for an Israeli private customer; whether a rescale needs a power-off | the order flow and the console, before buying |
| GitHub: your plan and payment-method state; whether included usage counts against a budget; what happens to a running codespace at the limit | the billing settings, and a small test |
| Codespaces: an unattended agent run with no client connected | a timed test in T2 |
| Claude Code in a codespace: the login flow; whether `~/.claude.json` follows `CLAUDE_CONFIG_DIR` | the first T2 session, and one rebuild |
| Gemini 3.1 Flash-Lite in the existing provider: default thinking vs the 500-token cap; free limits | stage 0 |
| Groq: spend limits; projects and custom limits on the free tier | the console |
| VAT or sales tax on Hetzner and GitHub | the checkout flow |
| `guynavon.net`: registrar, DNS provider, API support, existing records | the owner |
| B2: the card requirement; versioning, lifecycle and Object Lock defaults. R2: bucket locks | at signup, and in the docs |
| GCP: the egress price past 1 GB; e2-micro under real load | the pricing page; the load test |
| API and worker memory on Linux | measure in T3 |
| Source access from the real host | the probe (T3) |
| `tailscale serve --bg` across a reboot; the firewall with no inbound rules | test on the host |
| Dev processes staying in `user-1001.slice` (A) | `systemd-cgls` |
| Branch protection on `main` | the repository settings |
| The behaviour of healthchecks.io's `/fail` endpoint | its docs |

---

## 19. Sources (all checked 2026-10-13)

- **Hetzner:**
  - [price adjustment, 15 June 2026](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)
  - [IPv4 pricing](https://docs.hetzner.com/general/infrastructure-and-availability/ipv4-pricing/)
  - [billing FAQ](https://docs.hetzner.com/cloud/billing/faq/)
  - [Cloud servers FAQ: rescaling, keeping the disk, same architecture](https://docs.hetzner.com/cloud/servers/faq/)
  - specs and snapshot prices: [costgoat](https://costgoat.com/pricing/hetzner) (third-party)
- **GitHub:**
  - [Codespaces billing](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces)
  - [budgets and alerts](https://docs.github.com/en/billing/concepts/budgets-and-alerts)
  - [codespace lifecycle](https://docs.github.com/en/codespaces/about-codespaces/understanding-the-codespace-lifecycle)
  - [timeout](https://docs.github.com/en/codespaces/setting-your-user-preferences/setting-your-timeout-period-for-github-codespaces)
  - [automatic deletion](https://docs.github.com/en/codespaces/setting-your-user-preferences/configuring-automatic-deletion-of-your-codespaces)
  - [machine types](https://docs.github.com/en/codespaces/customizing-your-codespace/changing-the-machine-type-for-your-codespace)
  - [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
  - [Packages billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages)
- **Claude Code:**
  - [settings](https://docs.claude.com/en/docs/claude-code/settings): `~/.claude`, `~/.claude.json`, `CLAUDE_CONFIG_DIR`
  - [memory](https://docs.claude.com/en/docs/claude-code/memory): `~/.claude/projects/<project>/memory/`, `autoMemoryDirectory`
- **Google Cloud:**
  - [Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features)
  - [E2 shared-core](https://docs.cloud.google.com/compute/docs/general-purpose-machines)
  - [IP address pricing](https://cloud.google.com/vpc/network-pricing#ipaddress)
  - [Cloud NAT pricing](https://cloud.google.com/nat/pricing)
- **Oracle:**
  - [Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
  - [VCN FAQ](https://www.oracle.com/cloud/networking/virtual-cloud-network/faq/): public IPs
- **k3s:**
  - [requirements](https://docs.k3s.io/installation/requirements)
  - [resource profiling](https://docs.k3s.io/reference/resource-profiling)
- **Tailscale:**
  - [pricing](https://tailscale.com/pricing)
  - [key expiry](https://tailscale.com/kb/1028/key-expiry)
  - [HTTPS certificates](https://tailscale.com/kb/1153/enabling-https)
  - [Funnel](https://tailscale.com/kb/1223/funnel)
- **Cloudflare:**
  - [R2 pricing](https://developers.cloudflare.com/r2/pricing/)
  - [R2 API tokens](https://developers.cloudflare.com/r2/api/tokens/)
  - [partial (CNAME) setup](https://developers.cloudflare.com/dns/zone-setups/partial-setup/)
  - [Zero Trust plans](https://www.cloudflare.com/plans/zero-trust-services/)
  - [service-specific terms](https://www.cloudflare.com/service-specific-terms-application-services/)
  - [Workers AI JSON mode](https://developers.cloudflare.com/workers-ai/features/json-mode/)
- **Backblaze:**
  - [B2 pricing](https://www.backblaze.com/cloud-storage/pricing)
  - [application keys](https://www.backblaze.com/docs/cloud-storage-application-keys)
- **Groq:**
  - [models and prices](https://console.groq.com/docs/models)
  - [rate limits](https://console.groq.com/docs/rate-limits)
  - [projects](https://console.groq.com/docs/projects)
  - [structured outputs](https://console.groq.com/docs/structured-outputs)
  - [your data](https://console.groq.com/docs/your-data)
- **Google Gemini API:**
  - [gemini-3.1-flash-lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite)
  - [structured output](https://ai.google.dev/gemini-api/docs/structured-output)
  - [pricing](https://ai.google.dev/gemini-api/docs/pricing)
  - [billing and spend caps](https://ai.google.dev/gemini-api/docs/billing)
- **Others:**
  - OpenAI [pricing](https://developers.openai.com/api/docs/pricing)
  - Anthropic [pricing](https://claude.com/pricing)
  - healthchecks.io [pricing](https://healthchecks.io/pricing/)
  - [ECB reference rates, 12 Oct 2026](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)
- **Measured [M]:**
  - AAAA lookups (F21) from the owner's PC, 2026-10-13
  - backup compression (F22) on a read-only copy

---

## 20. Changes from v2

### Material fixes

1. **The requirement is unchanged, but dev hours are no longer assumed.** Costs are shown for
   20, 60, 80 and 120 running hours, and the recommendation is conditional (§5.5).
2. **The domain is new (§4).** `guynavon.net` with four access paths. No DNS change in phase one:
   Tailscale certificates don't cover the domain, and a Cloudflare Tunnel needs a nameserver move.
3. **A vs B is re-compared on experience as well as cost.** B is the reversible start, because a
   rescale can keep the disk [O, new].
4. **The Codespaces math is fixed:**
   - running hours vs human hours, including idle tails
   - the **break-even (78.6 h Free / 108.6 h Pro)** kept separate from **quota exhaustion
     (60 / 90 h)**
   - the storage rules: the default image is free, custom images and prebuilds are billed
   - what survives a resume, a rebuild and a new codespace
   - what a budget blocks, and what it doesn't promise
5. **GCP costs ≈ $3.65/month for the IPv4, not $0.** IPv6-only isn't viable (no AAAA for four
   sources, GitHub, GHCR and B2 [M]). NAT costs more. The e2-micro is conditional on a load test.
6. **The k3s figure is corrected.** 2 GB is a sizing minimum, not usage: the measured upstream p95
   is ~1.6 GB with a workload, so k3s is feasible on 4 GB. Compose is still preferred, and only one
   runtime is on the critical path.
7. **One deploy workflow.** CI builds, and the owner deploys from the PC with a separate
   forced-command identity. **No prod credential in any dev environment**, which fixes v2's
   "deploy from the codespace".
8. **The A hardening is concrete:**
   - uids and data ownership for non-root containers
   - no Docker socket
   - user-slice limits that cover VS Code Server, Claude Code, SSH and tmux
   - disk limits
9. **The LLM section is corrected:**
   - keys in the same Groq org don't separate quota, so dev uses project limits, a provider split
     or local bounds
   - no extra accounts
   - **the Gemini provider already exists**, so T1 can be config-only
   - a staged evaluation with pass criteria replaces the 2×3 matrix
10. **Restore is corrected:** all writers stopped, a WAL-safe swap, Telegram off on restore, and a
    drill on a copy. **Rollback classes** (code-only, additive, data-semantic) replace "old code
    ignores new columns".
11. **The dev snapshot is corrected:** sanitization keeps ids (emails and hashes scrubbed, sessions
    deleted), verified with the gate and the census tools. Full backups and dev snapshots have
    separate keys and buckets, and **dev can't decrypt full backups**.
12. **Non-recoverable data is now listed** (§12.1). The backup count and storage are corrected: 28
    objects, ~0.1 GB now and ~2.1 GB at 12 months, not "30 × 10 MB".
13. **`calib.py` is preserved** outside the temp folder with hashes. Its repo integration is
    proposed, not done.
14. **Cost precision:**
    - the original currency is binding
    - tax appears as scenarios (0, 18 and 19%)
    - the tax-inclusive price is read in the order flow
    - the LLM "≤ $5" is now labelled a scenario
    - "no VPS under $5" became "not found among the options checked"
    - third-party specs are tagged [T]
15. **The sequence is split into T1–T4.** Remote dev doesn't wait for prod hardening, and the first
    relief takes about a day of work.
16. **Acceptance is redefined:**
    - completion % plus a maximum continuous gap and a detection time, plus cycle-duration bounds
    - worker alive vs cycle completed vs source failure vs natural quiet
    - no waiting for an invoice
    - the PC may stay on as an access station
17. **Two code facts v2 got wrong or missed:**
    - `/signup` is open, and `AUTH_SIGNUP_ENABLED` doesn't exist (F20)
    - live clustering doesn't use Ollama (F19)

### Change log

- **2026-10-13 (v3):** the correction round above. Planning and documentation only.
- **2026-10-13 (v2):** rewritten after the owner's clarified requirements. Dev in scope; three
  architectures; Compose over k3s; x86 over Arm; new must-haves; "PC off for 7 days".
- **2026-10-13 (v1):** first draft for review.
