# Hosting Plan — Signal Sports off the owner's machine

**Status: DECISION DOCUMENT, under owner review. Version 2, 2026-10-13.** Nothing here is
implemented. No server was created, nothing was bought, and no provider was switched.

This version replaces the first draft (same date) after the owner clarified the requirement:
**the urgency is getting the load off the PC, independent of product readiness, and the
development environment has to move too, not only the running system.**

It covers milestone 13 (#261–#270). Proposed changes to those issues are in §16; none were
applied. When the plan is implemented, the living contract becomes `docs/DEPLOYMENT.md` and
this file is retired.

**Evidence tags used throughout:**

| Tag | Meaning |
|---|---|
| **[M]** | measured read-only on the owner's PC or local corpus, 2026-10-12/13 |
| **[C]** | checked in this repository's code or config |
| **[O]** | official provider page, checked 2026-10-13 (§18) |
| **[T]** | third-party page, checked 2026-10-13: lower confidence |
| **[E]** | engineering estimate |
| **[A]** | assumption that still needs verification (how is noted) |

Money is shown in the original currency, plus shekels at the **ECB reference rate of
12 Oct 2026** [O]: **€1 = ₪3.432**, **$1 = ₪3.0695** (derived from €1 = $1.1181). Provider prices
**exclude VAT** unless stated (see §9.1).

---

## 0. TL;DR

- **Immediate relief (days, $0):** move the LLM off the PC (#261, #262). Ollama is the heaviest
  component: a 1.9 GB model [M] that saturates a 2015-era 4-core i5 [M] for about 11 s per
  call. This alone does **not** meet the requirement, because the API, the worker and Vite still
  run locally and the PC must stay on.
- **Recommended full solution: Alternative B.**
  - A small **x86** VM runs the live system with Docker Compose: Hetzner **CX23**, 2 vCPU,
    4 GB, **€5.99/month incl. IPv4 ≈ ₪20.6**.
  - Development moves to **GitHub Codespaces**. Its free quota is 60 hours/month on a 2-core,
    8 GB machine. Without a payment method on file, usage is **blocked** at the quota, so the
    dev spend has a real hard cap.
  - Dev and prod are on separate machines, which keeps AI tools in the dev environment away from
    the live DB and secrets.
- **Second choice: Alternative A.** One Hetzner **CX33** (4 vCPU, 8 GB, **€8.99 ≈ ₪30.9**) runs
  both the live system and a remote dev environment (VS Code Remote-SSH). It is cheaper than B
  if development regularly exceeds about 60 h/month, but the isolation is weaker.
- **Cheapest option that meets the requirements: Alternative C, at $0.**
  - A Google Cloud **e2-micro** (1 GB RAM, 0.25 vCPU sustained) runs the live system, with
    Codespaces for dev.
  - Trade-offs: very tight resources, a card on file with **no hard spending cap**, US latency,
    1 GB/month of egress.
  - Oracle Always Free (2 OCPU / 12 GB) is the $0 option with more room, but idle instances are
    reclaimed and capacity is often unavailable.
- **Runtime: Docker Compose, not k3s, for now.** k3s's official minimum is 2 cores and 2 GB RAM
  before any workload [O]: half of a 4 GB VM, for no resilience gain on a single node.
  Kubernetes/OpenShift manifests (#264) and the OpenShift Sandbox are deferred.
- **New must-haves before the cutover:**
  - external heartbeat monitoring (healthchecks.io, free)
  - a source-content check from the target host
  - locked dependencies
  - a worker stop grace period
  - dev-safety guards
  - encrypted backups to object storage that don't depend on the PC
- **What you decide** (§17): expected dev hours per month, B or A or C, whether to put a card on
  file, the LLM provider, and the backup target.

---

## 1. The requirement (clarified 2026-10-13) and why it is urgent

1. **The owner's PC must stop carrying the load.** It is an Intel i5-6500 (4 cores / 4 threads,
   2015) with 16 GB RAM [M]. Ollama (`qwen2.5:3b-instruct`, 1.9 GB on disk [M]) saturates the
   CPU on each call, and the product only works while the PC is on.
2. **This is urgent regardless of pilot readiness, user count or feed quality.**
3. **There are two separate needs:**
   - *the running system:* API, frontend, worker, corpus, results, notifications
   - *the development environment:* editing, running, tests, debugging, builds, QA tools
4. **The PC remains an access station:** editor UI, browser, SSH and light tasks. It does
   **not** run Ollama, the backend, the worker or containers.
5. **Priorities, in the owner's order:**
   1. offload the PC
   2. low and predictable monthly cost
   3. preserve the corpus and data
   4. a running system independent of the PC
   5. dev that cannot endanger prod
   6. reasonable setup and maintenance time
6. **Preferences:** OpenShift/Kubernetes experience counts, but it is not a hard requirement. The
   ~€6–7 figure in the first draft was an estimate, not a budget.

---

## 2. Findings from the project itself

| # | Question | Finding | Tag |
|---|---|---|---|
| F1 | Processes the running system needs | **API** (`uvicorn app.main:app`) and **worker** (`python -m app.worker`). Each cycle runs ingestion, then clustering, notification planning and dispatch, results sync, and retention (disabled), all inside the worker's cycle. The **frontend** is a static build; Vite is a dev tool only. Ollama is optional (the rules fallback works) | [C] |
| F2 | Processes development needs | Backend `pytest` (hermetic: temp DB, LLM off, Telegram secrets emptied; it never opens the real corpus). Frontend lint, typecheck, test and build. Optional `capture:orbit` browser harness, which needs Chrome or Chromium and supports Linux paths. **Corpus-dependent tools:** the N05 gate, `rate_census.py build/review`, `corpus_rerun_diff.py`, `llm_failure_probe.py`, the `apply_*` correction scripts (which write) | [C] |
| F3 | CI cost of the checks | GitHub Actions: frontend lint 1 s, typecheck 3 s, test 3 s, build 4 s; backend `pip install` 15 s, **pytest 148 s** | [M] |
| F4 | Live-system resources | Worker 147 MB working set; DB 37 MB + 4 MB WAL, ~13 KB per article, about +0.7 GB/year; frontend build 1.1 MB; cycle duration median **3 s**, p95 **37 s**, max 71 s (the long ones include Ollama calls); LLM 35–46 calls/day, ~1,300 tokens each | [M] |
| F5 | Dev-tool footprint, as a proxy for a remote dev host | VS Code: 16 processes, 2.7 GB total, including the UI. Claude Code: 2 processes, 486 MB. The API's footprint was not measured (not running) | [M] / [E] |
| F6 | Windows/PowerShell assumptions | `scripts/worker.ps1` (Windows-only) and many usage docstrings (`.venv/Scripts/python.exe`). **The code itself is cross-platform**, and the browser harness accepts `SIGNAL_CHROME_PATH` and `/usr/bin/chromium` | [C] |
| F7 | Images and CI | **No Dockerfile, no `.dockerignore`, no deploy directory.** CI runs only backend pytest (Python 3.13) and frontend lint/typecheck/test/build (Node 22). There are no image builds, no deploys and no lock file: `requirements.txt` has lower bounds only (#198) | [C] |
| F8 | SQLite access | One engine per process. `timeout=30`, WAL, `busy_timeout=30000`, `check_same_thread=False`. API and worker are two writer processes on one file. **WAL needs a local filesystem; never NFS** | [C] |
| F9 | Who writes to the DB | **API:** auth sessions, feedback, profile changes, calibration, manual ingestion, manual results sync, classify backfill, dev routes. **Worker:** cycles. **Scripts:** the `apply_*` corrections. **The lease** (`scheduler_lease`) serializes *cycles* across processes **on the same DB file only**. It does not stop a second worker from existing, and it cannot coordinate two copies. Results sync has **no lease of its own** (#197) | [C] |
| F10 | Migrations, seeding and rollback | API and worker **both** run `init_db()`: `create_all`, then additive `ALTER TABLE ADD COLUMN` serialized with `BEGIN IMMEDIATE`. Forward-only, with no down path. Older code ignores newer columns [E], so a code rollback is usually safe, while a data restore is a separate act. The API seeds only empty tables and creates credential-less demo users; the admin is bootstrapped from env | [C] |
| F11 | Worker shutdown and the lease | SIGTERM stops the loop **after the current cycle finishes**. A SIGKILL mid-cycle leaves the lease held until it goes stale: `SCHEDULER_STALE_AFTER_SECONDS=1800`, **30 minutes**. **Docker's default stop timeout is 10 s** [A, verify per runtime]. Without a longer grace period, each deploy can open an ingestion gap of up to 30 minutes | [C] |
| F12 | Side-effect switches | `SCHEDULER_ENABLED` (the worker refuses to start unless it is exactly `true`), `TELEGRAM_NOTIFICATIONS_ENABLED`, `RESULTS_SYNC_ENABLED`, `RETENTION_CLEANUP_ENABLED`, `CLUSTERING_ENABLED`, `FEED_FRESHNESS_ENABLED`. **The dispatcher sends whenever the flag is true and a token and chat id are set**, so on a **copy** of the DB, pending outbox rows would really be sent | [C] |
| F13 | Corpus guard | `corpus_protection.py` protects `<backend>/data/signal_sports.db` by **path**. In a container at `/app` that is `/app/data/signal_sports.db`. A dev copy with the same name in a dev checkout is also treated as "the corpus" (it blocks resets there), and a copy with another name is not protected | [C] |
| F14 | Essential data outside git | Only on the PC: the **corpus DB**; `backend/data/backups/` (277 MB); **`backend/.env` and two `.env` backups containing secrets** (Telegram token, API keys, admin password); `frontend/.env.local`; worker logs; **Claude Code memory** (`~/.claude/projects/...`). **`calib.py`**, the census fit/held-out tool behind #237, exists **only in an old Claude scratchpad under `%TEMP%`**. All rating and census files *are* in git (`docs/qa/`) | [M] / [C] |
| F15 | Limits on a safe dev copy | A dev copy holds real account rows (emails, Argon2 hashes) and the notification outbox and watermark. Dev therefore needs: no Telegram token, a refusal guard for Telegram, a separate DB path, and ideally a **sanitized snapshot** (auth tables stripped) | [C] / [E] |
| F16 | Sources from a datacenter | **Preliminary:** fetched 2026-10-13 from Anthropic's fetch infrastructure (a non-Israeli datacenter, not the target host). All five sources returned valid, fresh content: Walla RSS 30 items, Israel Hayom 100 (19 sport), Ynet 30, Sport5 8 article links, **ONE JSON API 10 articles**. ONE works even though it is disabled by an override | [M]-prelim |

---

## 3. Screening (broad), and why options were dropped

| Option | Kind | Verdict | Reason |
|---|---|---|---|
| Keep running on the PC (+ autostart) | — | ✗ | Contradicts requirement 1 |
| **Interim: LLM off the PC only** | partial | ✓ as a first step | Removes the heaviest load fast, but **does not meet the full requirement** (§4.4) |
| Red Hat **Developer Sandbox** (free OpenShift) | trial | ✗ for prod and for dev | 30-day trial, renewable by export/import; **pods deleted after 12 consecutive hours, not restarted** [O]. It can't host the 5-minute worker, and dev state doesn't survive the trial |
| Managed OpenShift (ROSA, ARO, Dedicated) | paid | ✗ | Enterprise pricing for a one-user project |
| **Hetzner CX23 / CX33 (x86)** | paid VPS | ✓ deep | Cheapest stable fit [O] |
| Hetzner CAX11 / CAX21 (ARM) | paid VPS | ✗ | Since 2026-06-15 they cost **more** than the x86 equivalents (€5.99 vs €5.49; €10.49 vs €8.49) [O], and add an architecture mismatch with CI and Codespaces |
| **Google Cloud e2-micro (Always Free)** | free tier | ✓ deep (prod only) | 1 GB RAM, 0.25 vCPU sustained [O]: enough for prod without Ollama, not for dev |
| **Oracle Cloud Always Free (A1)** | free tier | ✓ deep, as a variant | 2 OCPU / 12 GB [O], enough for prod and dev. The risks are idle reclamation and capacity |
| GCP Free Trial ($300 / 90 days), AWS credits, Azure 12-month | trial / credits | ✗ steady state | They expire. Useful at most for one-off tests |
| AWS Lightsail ($3.50 IPv6-only 512 MB; $5 for 0.5 GB with IPv4) | paid VPS | ✗ | Too little RAM per dollar [O] |
| Fly.io (~$3.85: 512 MB + 1 GB volume; no free tier for new orgs) | PaaS | ✗ | No cheaper than Hetzner, no dev story, public by default [T] |
| Render, Railway, Northflank free tiers | PaaS | ✗ | Sleeping services, missing volumes, or "testing" quotas [T]. Not evaluated in depth |
| Split: static frontend (Pages) + backend elsewhere | managed split | ✗ | A cross-site cookie between a public frontend and a tailnet API breaks on iOS Safari (third-party cookie blocking) [E]. It needs #196, CORS and SameSite changes, and nothing gets cheaper |
| PaaS + managed Postgres (Neon, Supabase free) | managed split | ✗ now | Moving SQLite to Postgres, including raw SQLite-specific SQL, is large risky work for no gain at 37 MB (#198 forbids an engine change without a reason) |
| **GitHub Codespaces (dev)** | free quota | ✓ deep | 120 core-hours/month + 15 GB-month free; **blocked at the quota without a payment method** [O] |
| Hetzner dev VM by the hour (snapshot + delete) | paid, hourly | ✓ alternative for B | A server is billed while it exists, **even powered off** [O], so the only way to save money is to snapshot and delete it, with some per-session setup |
| Gitpod/Ona, Coder, DevPod | dev envs | — | Not evaluated; no clear advantage over Codespaces at this size |

---

## 4. Deep comparison of the leading alternatives

### 4.1 Alternative A — one VM for the live system and remote development

- **Host:** Hetzner **CX33**: 4 vCPU x86, 8 GB, 80 GB, 20 TB traffic. €8.49 + €0.50 IPv4 =
  **€8.99/month ≈ ₪30.9** [O].
- **Live system:** a Compose project `signal-prod`, owned by root or a dedicated system user.
  The data lives on a **bind mount**, `/srv/signal/prod/data`.
- **Dev:** a separate Linux user `dev` with its own checkout (`/home/dev/signal-sports`), its own
  DB (`/home/dev/data/dev.db`, a sanitized snapshot), its own `.env` (`DEPLOY_ENV=dev`), and its
  own ports (API 8100, Vite 5174). Development runs **outside Docker**, in a venv plus npm. Open
  it with **VS Code Remote-SSH over Tailscale**; Claude Code runs on the VM.
- **Isolation that actually exists:**
  - file permissions: prod data and env are root-only, mode 600
  - the dev user is **not** in the `docker` group, which would be root-equivalent, and has
    **no passwordless sudo**
  - a systemd slice for `dev` (`MemoryMax≈5G`, `MemoryHigh`, `CPUWeight=50` against prod's
    default, `IOWeight`)
  - prod containers with `oom_score_adj` set low and memory reservations
  - a **separate filesystem or quota** for `/home`, so dev can't fill the disk prod writes to
- **What still fails together:**
  - the VM itself: a kernel, disk or host problem, or a provider outage
  - the Tailscale node
  - the kernel OOM killer under extreme pressure
  - a compromised account with root
  - *A folder is not a security boundary.* An AI agent running as `dev` can read anything `dev`
    can read, so the permissions must really hold.
- **Pros:**
  - fixed cost, whatever the dev hours
  - one place for code, memory and Claude Code
  - long-running dev processes survive a disconnect
  - closest to an "own server" workflow
- **Cons:**
  - the weakest prod/dev isolation of the three
  - needs 8 GB (§7)
  - more hardening work
  - a dev mistake with elevated rights can hit prod

### 4.2 Alternative B — small VM for the live system, Codespaces for development (recommended)

- **Host:** Hetzner **CX23**: 2 vCPU x86, 4 GB, 40 GB, 20 TB. €5.49 + €0.50 IPv4 =
  **€5.99/month ≈ ₪20.6** [O]. The live system only, same Compose layout as A.
- **Dev:** GitHub Codespaces, defined by a `devcontainer.json` in the repo (Python 3.13 +
  Node 22, `pip install` and `npm ci` on create).
  - The default machine is **2-core, 8 GB RAM, 32 GB** [O]. The free quota is
    120 core-hours, so **60 h/month on a 2-core** (30 h on a 4-core), plus 15 GB-month of
    storage [O].
  - Past the quota: $0.18/h (2-core), $0.36/h (4-core), and $0.07/GB-month [O].
    **With no payment method on file, usage is blocked**, which is a hard cap [O].
- **Isolation:** separate machines. Dev has no network path to prod and no prod secrets. It
  gets a **sanitized** snapshot through a read-only, dev-only object-storage token.
- **Pros:**
  - the lowest fixed cost of the paid options
  - a hard cap on dev spend
  - the strongest dev/prod isolation
  - nothing to harden for dev
  - no idle cost when the codespace is stopped, beyond storage within the free 15 GB-month
- **Cons:**
  - 60 free hours a month. Beyond that you either add a card (and there is then no hard cap
    unless a GitHub budget stops usage [A]) or switch to A.
  - The codespace stops after 30 minutes idle (configurable to 4 h) [O].
  - **A codespace stopped for 30 days is deleted, unpushed work included** [O].
  - Claude Code needs a login per codespace, and its memory files must be carried over (§6).
  - Internet access is required.
- **Migration path to A:** Hetzner can **rescale** a CX23 to a CX33 in place [A]. If dev hours
  exceed the quota, development can move onto the prod VM without redesigning prod.

### 4.3 Alternative C — $0 (free tiers)

- **C1:** **GCP e2-micro** for the live system, plus Codespaces (as in B).
  - Resources: 2 vCPUs at 12.5% each, so **0.25 vCPU sustained**, bursting to 100% for short
    periods (about 30 s at full load); **1 GB RAM**; 30 GB standard disk; 1 GB egress/month
    (North America to everywhere except China and Australia); regions us-west1, us-central1 and
    us-east1 only [O].
  - A Cloud Billing account (a card) is needed for the Free Tier [A]. **Budget alerts do not cap
    spending.** A wrong region, disk type or traffic is billed, with no guaranteed upper bound.
  - The live system fits in RAM (§7: about 0.65–0.9 GB with a 1–2 GB swap file as a buffer
    only). The CPU is tight, and feed latency needs measuring after provisioning [A].
  - Backups count toward the 1 GB egress: nightly, compressed, about 0.3 GB/month [E].
- **C2:** **Oracle Always Free**, A1.Flex, **2 OCPU / 12 GB** for any tenancy [O], 200 GB block
  storage, 10 TB egress [O]. It has room for the live system and the same-VM dev of A, at $0.
  - **Idle reclamation applies** when, over 7 days, the 95th-percentile CPU, network and memory
    are all under 20% [O]. A light live system can look idle. The official doc does not say
    pay-as-you-go accounts are exempt [O]; third parties say they are [T], so this is
    **unverified**.
  - "Out of host capacity" errors are documented [O]. Resources must be in the home region [O].
  - A card is needed at signup [A].
- **Pros:** $0 a month.
- **Cons:**
  - The risks are of the kind this milestone is trying to remove: a reclaimed or throttled host
    looks exactly like the old silent outages.
  - Charges without a cap on GCP and Oracle pay-as-you-go.
  - More tuning work.

### 4.4 Interim — take only the LLM off the PC (step 1 in every alternative)

- **What it removes:** the 1.9 GB model and the CPU saturation of about 11 s per call [M]. This
  is most of the felt load.
- **What stays local:** the API (~150 MB [E]), the worker (147 MB [M]), Vite, and Tailscale
  Serve. The PC must still be on, with the processes started.
- **Time to reach it:** the provider PR (#261) takes 4–8 h. The evaluation (#262) takes 1–3 days
  of elapsed time on free-tier daily caps.
- **Reuse:** 100%; every alternative needs it.
- **Verdict:** **this does not satisfy the requirement.** It is the first step, not the solution.

### 4.5 Side by side

| | A: one CX33 | B: CX23 + Codespaces | C1: e2-micro + Codespaces | C2: Oracle A1 |
|---|---|---|---|---|
| Monthly (no dev beyond the free quota) | €8.99 ≈ ₪30.9 | €5.99 ≈ ₪20.6 | $0 | $0 |
| Dev at 120 h/month | same €8.99 | +$10.80 ≈ ₪33.2 (needs a card) | +$10.80 | $0 |
| Prod/dev isolation | process + permissions | **separate machines** | separate machines | process + permissions |
| Hard spending cap | fixed price, postpaid | fixed VM; dev capped without a card | ✗ (alerts only) | ✗ on PAYG |
| Biggest risk | dev hurting prod | quota and auto-delete of codespaces | throttled CPU, 1 GB RAM | reclamation, capacity |
| Setup (hours, §10.3) | ~30–50 | ~27–45 | ~30–50 | ~30–50 + capacity hunting |
| Fit with an OpenShift habit | SSH host (k3s possible on 8 GB) | prod small; k3s doesn't fit 4 GB | ✗ | k3s fits |

---

## 5. Runtime: Docker Compose vs k3s (separate from the host choice)

| Aspect | Compose | k3s (single node) |
|---|---|---|
| Memory and CPU overhead | Docker engine plus containerd, about 0.05–0.1 GB [E] | **Official minimum for a server node: 2 cores, 2 GB RAM**, excluding workloads [O] |
| Restart after a crash or reboot | `restart: unless-stopped` + `docker.service` enabled at boot | kubelet restarts pods; the k3s systemd unit starts at boot |
| Deploy and rollback | Set the image digest, `docker compose up -d`; roll back with the previous digest | `kubectl set image` / `rollout undo`, with revision history |
| Limits between dev and prod | Container limits for prod. **Dev processes outside Docker need systemd slices in both cases** | Requests, limits and PriorityClass for pods. Dev processes are still outside k8s and still need slices |
| Secrets | A root-only env file, or file-mounted secrets | Secrets (not encrypted at rest unless configured) |
| Networking | One compose network; `web` published on 127.0.0.1 | Traefik, CoreDNS, Services, Ingress: more moving parts |
| Volumes and the risk of deleting them | A **bind mount** survives `docker compose down -v` (named volumes don't) | **local-path PVCs default to reclaim `Delete`**: removing the PVC deletes the data unless it is set to `Retain` |
| Logs and health | `docker logs` (configure rotation), healthchecks | `kubectl logs`, probes |
| Setup and maintenance | ~1–2 h setup, rare upgrades [E] | ~3–6 h setup, k3s upgrades, more to debug [E] |
| Fit with the owner's experience | lower | high (OpenShift-like) |
| Switching later | Compose → k8s: writing manifests, about 0.5–1 day [E] | k8s → Compose: easy |

**Decision proposed: Compose now. Do not maintain both.**

- k3s costs about 2 GB on a 4 GB box and adds failure modes. **On a single node it adds no
  resilience against losing the VM.** Its real value here is familiarity and portability, which
  can be bought later in about a day.
- **The OpenShift Developer Sandbox adds no value on the critical path.** Defer the OpenShift
  compatibility check (#264).

**Pod and service design, corrected.** API and worker run as **two separate services** sharing a
**host bind mount** on one machine.

- A shared pod is *not* required. SQLite needs both processes on the same local filesystem,
  which two services on one host already are. Kubernetes `ReadWriteOnce` is per **node**, not per
  pod, so it neither forces co-location in one pod nor guarantees a single writer.
- **A single worker** is enforced by four layers:
  1. exactly one worker service in the prod Compose project, never scaled
  2. the DB lease, which prevents overlapping cycles **on that one file**
  3. the operational rule: one corpus, one writer, and the PC never runs a worker again after
     the cutover
  4. dev guards (§11)
- **The worker's stop grace period must exceed a cycle:** `stop_grace_period: 300s` (F11).

---

## 6. Day-to-day development (leading alternatives)

| Question | A: same VM (Remote-SSH) | B/C: Codespaces |
|---|---|---|
| Open the project | VS Code on the PC → Remote-SSH over Tailscale (`dev@<vm>`) | VS Code on the PC → "Codespaces: Connect", or github.com in a browser |
| Files and git checkout | `/home/dev/signal-sports` on the VM; persistent | `/workspaces/signal-sports` in the codespace; **deleted 30 days after it stops**, so push every session |
| Where the editor backend runs | VS Code server and extension host on the VM; only the UI is on the PC | the same, in the codespace |
| Claude Code | On the VM, as `dev`. Its memory lives on the VM (copy `~/.claude/projects/<proj>/memory` over once) | In the codespace. Memory must be copied in each time, e.g. through a private dotfiles repo [A]; the login is per codespace |
| Hot reload and preview | `uvicorn --reload` on 8100, Vite on 5174, against `dev.db` | the same inside the codespace |
| Dev from the browser and phone | The PC through VS Code port forwarding. The phone through a second Tailscale Serve port, e.g. `https://<vm>:8443` (**different cookie name**, §11) | Forwarded ports are private and need a GitHub login; they work in a phone browser [A] |
| Backend tests, frontend checks | `pytest` and `npm run ...` inside the dev slice, which takes one core for 2.5–5 min [E] | the same, inside the codespace |
| Quality gates (N05, census) | Against a **pulled snapshot** (§11), never the live DB | the same |
| Image builds | **CI only** (GitHub Actions, free for this public repo [O]), never on the VM | CI only |
| Trying a branch without touching prod | Run the dev stack from the branch checkout; prod keeps running the deployed digest | the same |
| Dev → CI → prod | PR → CI (tests + image build) → merge → `deploy <sha>` on the VM (§12.4) | the same, with the deploy run over SSH from the codespace or the PC |
| QA snapshot | `pull_snapshot`: the latest sanitized backup from object storage | the same, with a dev-only read token as a Codespaces secret |
| Connection drops | Processes keep running on the VM; use `tmux` for long jobs | The codespace keeps running until the idle timeout (30 min default, up to 4 h [O]) and then stops; files persist |
| PC is switched off | Nothing changes on the VM | The codespace stops after the idle timeout; no compute cost while stopped |
| Two dev or test jobs in parallel | They share the dev slice (CPU and RAM) and need distinct ports | One codespace per branch is possible, but each one spends quota |

**Security boundary:**

- **A:** permissions plus a slice, a sudo-less dev user, and no docker group. That is weaker
  than separate machines.
- **B/C:** prod is unreachable unless a credential is copied in. Never put prod SSH keys,
  Tailscale prod access or the prod env into a codespace.
- **In both:** the codespace's `GITHUB_TOKEN` can push to the repo [A]. Branch protection on
  `main`, with PR and CI, limits what an agent can do.

---

## 7. Resources, including development

All rows are **[E]** except the measured worker figure (147 MB [M]) and the CI timings (F3).

| Scenario | RAM | CPU | Notes |
|---|---|---|---|
| 1. Live system only | **0.65–1.0 GB**: OS 0.25–0.35, Docker 0.05–0.1, Tailscale 0.03–0.05, API 0.12–0.18, worker 0.15–0.25, nginx 0.01 | under 5% of a vCPU on average; short bursts during cycles | fits 1 GB (tight), 4 GB (easy) |
| 2. + dev server | **2.0–3.5 GB**: + VS Code server 0.6–1.5, Claude Code 0.3–0.5, dev API 0.15–0.3, Vite 0.15–0.3 | bursts on reload | same-VM dev only |
| 3. + test run | **2.4–4.2 GB**: + pytest 0.3–0.7 | one core for 2.5–5 min | |
| 4. + build | **2.4–4.5 GB**: + `npm run build` / `tsc` 0.4–1.0 | short spikes | images are built in CI, not here |
| 5. Realistic parallel peak | **3.2–5.2 GB** | 2–4 cores busy | dev server + tests + build + an active agent |

**Disk:**
- Live system: about 3–5 GB, of which images 0.6–1.0, DB 0.04 (+0.7/year), logs 0.5 or less
  with rotation, local backups 0.5 or less.
- Same-VM dev adds 3–5 GB: the checkout, `.venv` 0.4–0.6, `node_modules` 0.4–0.6, DB copies and
  snapshots.
- Build caches stay in CI.

**Conclusions:**

- **4 GB is enough for the live system alone** (B, C2). **1 GB is enough only for the live
  system, with swap as a buffer** (C1).
- **Same-VM development needs 8 GB** (A, the CX33). On 4 GB, scenario 5 would push prod into
  swap or the OOM killer.
- **Swap** (2–4 GB) is a buffer against spikes, not a substitute for RAM: a swapping prod is a
  slow prod.
- **Under OOM pressure,** the kernel kills the process with the highest `oom_score`. Protect prod
  with `oom_score_adj`, and cap dev (`MemoryMax`) so it is killed first.
- **ARM vs x86:** x86 is now cheaper at Hetzner [O]. CI runners, Codespaces [A: x86_64] and the
  PC are x86 too, so the choice is **x86 with single-arch amd64 images**. The project's
  dependencies would work on ARM, but nothing is gained.
- **Moving builds to CI** costs the dev loop nothing: dev still runs tests and the dev servers
  locally in its environment, and only images (and the deploy artifact) come from CI.

---

## 8. LLM providers

The task: classify a Hebrew headline and subtitle into strict JSON, about 45 times a day in prod,
roughly 1.75M input tokens and 0.1–0.5M output tokens a month. The output range includes
reasoning tokens for reasoning models [E]. **A bigger model is not assumed to be better, and an
OpenAI-compatible API is not assumed to behave identically.** Both get measured (§8.2). The rules
fallback and the guardrails stay as they are.

### 8.1 Candidates (checked 2026-10-13)

| Candidate | Exact model | Structured output | Free limits | Over the limit | Paid price (per 1M in / out) | Card / cap | Data | Fit |
|---|---|---|---|---|---|---|---|---|
| **Groq** | `openai/gpt-oss-20b`, `openai/gpt-oss-120b` (production) [O] | **strict JSON Schema, constrained decoding** [O] | per **organization** and model: 30 RPM, 1K RPD, 8K TPM, 200K TPD [O] | HTTP 429 + `retry-after` [O] | $0.075 / $0.30; $0.15 / $0.60 [O] | free tier needs no card [O]; paid spend controls [A] | not retained by default; up to 30 days for abuse monitoring; zero-retention available [O] | **Lead.** `qwen/qwen3.8-27b` is **Preview, "evaluation only"** [O], so it is not for prod |
| **Gemini** | `gemini-3.1-flash-lite` (stable) [O]. `gemini-2.5-flash-lite` is now limited to past users [O] | JSON schema supported [A] | free tier exists; limits unpublished [O] | — | $0.25 / $1.50 [O] | paid requires **prepaying at least $5**; **hard spend caps** at the tier and project level [O] | free-tier content is used to improve products [O] | **Lead fallback**, with a genuine cap |
| OpenAI | `gpt-5-nano` [O] | yes [A] | none | — | $0.05 / $0.40 [O] | prepaid credits [A] | — | possible paid option |
| Anthropic | Haiku 5.5 [O] | yes [A] | none | — | $0.10 / $0.50 (prompts up to 100K) [O] | prepaid credits [A] | — | possible paid option |
| Cloudflare Workers AI | gpt-oss-120b and others | **no JSON mode for gpt-oss or Qwen3** [O] | 10K neurons/day [O] (about 2.1K/day for our load) | blocked on the free plan [A] | 31,818 / 68,182 neurons per 1M [O] | free plan without a card [A] | — | fallback only, with parse risk |
| Cerebras | gpt-oss-120b, qwen-3.8-27b | [A] | 5 RPM, 1M TPD [O] | — | not retrieved | promo credit requires a card [O] | — | a backup option |

### 8.2 Bounded evaluation (#262), before switching

- **Data:**
  - census #2's eligible rows (about 225 per model per run)
  - **plus census #3 (#241) once rated, which is data never used for the #237 fit.** Prefer
    census #3 for the verdict.
- **Measure, against the owner's ratings:**
  - shown precision, feed+ recall, push precision and recall
  - JSON validity and schema errors (they should be zero with strict mode)
  - field changes against stored facts
  - latency, timeouts and 429s
  - **actual tokens, including reasoning tokens** (at `reasoning_effort=low`)
- **Candidates:** Groq `gpt-oss-20b` and `gpt-oss-120b`, with Gemini 3.1 Flash-Lite as an
  optional third.
- **Cost of the evaluation:**
  - about 2 models × 3 runs × 225 calls ≈ 1,350 calls ≈ 1.75M tokens
  - **$0** on free tiers, but Groq's 200K tokens/day caps it at about 150 calls per model per
    day, so **2–5 days of elapsed time**
  - about $0.3–1 if paid [E]

### 8.3 Cost: live use vs development (estimates [E])

| | Groq 20b | Groq 120b | Gemini 3.1 FL | gpt-5-nano | Haiku 5.5 |
|---|---|---|---|---|---|
| Live use, paid ($/month) | 0.16–0.28 | 0.32–0.56 | 0.59–1.19 | 0.13–0.29 | 0.23–0.43 |
| Live use on a free tier | $0 | $0 | $0 [A: limits] | — | — |
| A heavy dev month, 1–10× live volume | +$0.2–3 | +$0.3–5 | +$0.6–10 | +$0.1–3 | +$0.2–4 |

**Quota collision:** Groq's limits are **per organization** [O]. Dev experiments on the prod key
can exhaust the day's quota, and prod then falls back to rules for the rest of the day.
**Use a separate organization or key for dev, or a different provider** (for example Gemini's
free tier for dev, Groq for prod). Implementation notes for #261: request strict
`json_schema`, set `reasoning_effort=low`, and record usage per call. No multi-provider
failover is needed: switching providers is a config change followed by an evaluation.

---

## 9. Prices (all checked 2026-10-13)

### 9.1 Line items

| Item | Price | Currency, period | Tax | Region | Source | Verifiable without an account |
|---|---|---|---|---|---|---|
| Hetzner CX23 (2 vCPU x86, 4 GB, 40 GB, 20 TB) | 5.49 per month, cap; 0.0088 per hour | EUR | **excl. VAT** [O] | DE / FI | Hetzner price adjustment, effective 15 Jun 2026 [O]; specs [T] | yes |
| Hetzner CX33 (4 vCPU x86, 8 GB, 80 GB, 20 TB) | 8.49 per month; 0.0136 per hour | EUR | excl. VAT | DE / FI | [O]; specs [T] | yes |
| Hetzner CAX11 / CAX21 (ARM) | 5.99 / 10.49 per month | EUR | excl. VAT | DE / FI | [O] | yes |
| Hetzner Primary IPv4 | 0.50 per month | EUR | excl. VAT | — | [O] | yes |
| Hetzner backups (7 slots) | 20% of the server price | EUR | excl. VAT | — | [O] | yes |
| Hetzner snapshots / volumes | 0.0143 / 0.0572 per GB-month | EUR | excl. VAT | — | [T] | yes |
| Hetzner traffic over 20 TB | billed in 100 MB blocks [O]; €1/TB [T] | EUR | excl. VAT | EU | [O] / [T] | yes |
| GCP e2-micro + 30 GB disk + 1 GB egress | $0 within limits; overage at list price | USD | — | us-west1 / us-central1 / us-east1 | [O] | yes |
| Oracle A1 2 OCPU / 12 GB, 200 GB block, 10 TB egress | $0 within limits | USD | — | home region | [O] | yes |
| GitHub Codespaces | 120 core-h + 15 GB-month free; $0.18/h (2-core), $0.36/h (4-core); $0.07/GB-month | USD | unclear [A] | — | [O] | yes |
| GitHub Actions, GHCR | free for a public repo and public packages | — | — | — | [O] | yes |
| Tailscale Personal | $0: 6 users, unlimited user devices, 50 tagged resources | — | — | — | [O] | yes |
| healthchecks.io Hobbyist | $0: 20 checks, email alerts, no card | — | — | — | [O] | yes |
| Cloudflare R2 | 10 GB-month, 1M class-A and 10M class-B operations free; then $0.015/GB-month; **egress free** | USD | — | global | [O]; card requirement [A] | yes |
| Backblaze B2 | first 10 GB free; $6.95/TB-month; free egress up to 3× storage | USD | — | — | [O] | yes |
| LLM | see §8.1 | USD | — | — | [O] | yes |
| A domain | **not needed** (tailnet hostname) | — | — | — | — | — |

**VAT:** Hetzner's prices exclude VAT [O]. Whether VAT is charged to an Israeli private customer
is **unverified** [A], so check the first invoice. As a planning bound, assume 0% to 18%: Hetzner
CX23 €5.99–7.07, CX33 €8.99–10.61.

**When "off":** a Hetzner server is billed in full while it exists, even powered off [O]. Billing
stops only on delete. Snapshots and volumes keep billing. A stopped codespace costs storage only,
within the free 15 GB-month [O]. GCP and Oracle free resources cost nothing idle, but attached
paid extras would keep billing.

### 9.2 Cost classes

| Class | A | B | C1 | C2 |
|---|---|---|---|---|
| 1. Expected monthly | €8.99 (₪30.9) | €5.99 (₪20.6) | $0 | $0 |
| 2. Busy month (paid LLM fallback, 120 h dev) | €8.99 + ≤$5 LLM ≈ ₪31–46 | €5.99 + $10.80 Codespaces + ≤$5 LLM ≈ ₪54–69 | $10.80 + ≤$5 ≈ ₪33–48 | ≤$5 ≈ ₪0–15 |
| 3. Setup month | ≤ €8.99, billed hourly from creation | ≤ €5.99 | $0 | $0 |
| 4. After any credits or trials end | unchanged (no credits used) | unchanged | unchanged (Always Free, not trial) | unchanged |
| 5. Plausible overrun | VAT; Hetzner's next price rise (three so far in 2026 [T]) | VAT; a Codespaces card without a budget stop | **no hard cap**: misconfiguration or egress over 1 GB | **no hard cap** on PAYG; reclamation |

Exchange rate: ECB 12 Oct 2026, from §0.

---

## 10. Budget scenarios

### 10.1 By development hours

These hour counts are **planning assumptions**, not measured usage.

| Per month | A: CX33 | B: CX23 + Codespaces 2-core | C1: e2-micro + Codespaces | C2: Oracle |
|---|---|---|---|---|
| Live system only | €8.99 ≈ ₪30.9 | €5.99 ≈ ₪20.6 | $0 | $0 |
| Light dev (20 h) | €8.99 (dev hours change capacity, not cost) | €5.99 + $0 | $0 | $0 |
| Regular dev (60 h) | €8.99 | €5.99 + $0 (exactly at the free quota) | $0 | $0 |
| Intensive dev (120 h) | €8.99 | €5.99 + **$10.80** ≈ ₪53.7, or blocked at 60 h without a card | $10.80 ≈ ₪33.2, or blocked | $0 |

Hetzner hourly dev VM, as a variant of B: a CX33 that exists only during sessions costs
€0.0136/h [O] plus a snapshot of about €0.07–0.14/month [E]. That is about **€0.3 / €0.8 /
€1.6** at 20 / 60 / 120 h. It needs a create-from-snapshot and delete-with-snapshot script, takes
about 2–5 minutes per session, and **work is lost if the server is deleted without a snapshot**.

### 10.2 What each budget tier buys

| Tier | Best option | Notes |
|---|---|---|
| **$0** | C1 (GCP e2-micro + Codespaces ≤60 h) or C2 (Oracle A1) | Free LLM tier, R2 free, healthchecks.io free. Trade-offs in §4.3 |
| **≤ $5/month** | Still C1 or C2, plus a paid LLM fallback ($0.2–1) | No stable paid VPS with enough RAM is this cheap; Lightsail's $3.50 tier has 512 MB [O] |
| **≤ $10/month** | **B** (€5.99 ≈ $6.70), or **A** (€8.99 ≈ $10.05, right at the edge; over it if VAT applies) | Stability without free-tier risks |
| More | A with Hetzner backups (+€1.70), or B with paid Codespaces beyond 60 h | Only if the dev hours or extra safety justify it |

Subscriptions are separate: a Claude or ChatGPT subscription does **not** include API credits
for the application [A, standard terms]. The LLM lines above are infrastructure.

### 10.3 Setup and maintenance time (hours, estimates [E])

| Work | A | B | C1 | C2 |
|---|---|---|---|---|
| Common to all hosted options: images + lock (8–14), safety guards (3–5), monitoring (2–4), backups + restore drill (4–8), cutover (3–5, plus the soak period), QA from snapshots (3–6) | 23–42 | 23–42 | 23–42 | 23–42 |
| Host-specific | VM hardening, dev user, slices, quotas, Remote-SSH, dev Serve port: 6–10 | VM: 3–5; devcontainer: 2–4 | billing guard, firewall, swap tuning: 4–8; devcontainer: 2–4 | capacity hunting (open-ended), hardening, dev user: 6–10 |
| **Total setup** | **~30–50 h** | **~27–45 h** | **~30–50 h** | **~30–50 h + capacity** |
| Maintenance | ~1–2 h/month | ~0.5–1 h/month | ~1–2 h/month | ~1–2 h/month |

---

## 11. Data protection and dev/prod separation

| Rule | How |
|---|---|
| **One authoritative DB** | Prod VM: `/srv/signal/prod/data/signal_sports.db`, a bind mount owned by the prod user |
| **Never two live workers** | One worker service, never scaled. The lease. **After the cutover the PC never runs a worker.** Dev runs no worker by default |
| A dev worker when needed | Only with `DEPLOY_ENV=dev` on a dev DB path. **Guards refuse Telegram, and refuse a DATABASE_URL under the prod data dir.** Results sync is off by default, the LLM uses the dev key, and fetching real sources is allowed (it only reads them) |
| **No real Telegram from dev** | No token in any dev env, plus the guard above (F12) |
| Retention | `RETENTION_CLEANUP_ENABLED=false` until #255 protects rated rows |
| **WAL-safe backups** | `scripts/backup_db.py` (the SQLite backup API) on a systemd timer or a backup service: **every 6 h** (RPO ≤ 6 h) or nightly (RPO ≤ 24 h) |
| **Off-host, independent of the PC** | Compress, **encrypt with `age` to a public key** (the host can encrypt but never decrypt), then upload to **R2** (or B2). The private key is offline: a password manager plus a printed copy. Pulling to the PC is an optional extra copy, never the only one |
| Other essentials | Ratings and census files: in git. In-progress census ratings: commit after each rating session. **`calib.py`: commit it to `backend/scripts/`** (F14). Secrets: password manager plus the host env file (root, mode 600); never in object storage unencrypted, never in git or issues. Claude memory: copied to the dev environment |
| Backup retention | 6-hourly kept 2 days, daily 14, weekly 8, monthly 6: about 30 objects of about 10 MB compressed, roughly 0.3 GB [E] |
| **Restore drill** | Before the cutover and then quarterly: download, decrypt, `PRAGMA integrity_check`, compare counts, run the N05 gate on the restored copy |
| Expected loss and time to restore | RPO 6–24 h, depending on schedule. Articles lost in that window are mostly re-fetched from the sources' RSS windows (1–2 days) [E]. RTO about 1–2 h onto a new VM from the runbook [E] |
| Backup before changes | `deploy` takes a backup before every deploy, and every `apply_*` correction script runs after a backup |
| **No accidental deletion** | A bind mount, never a named volume (`docker compose down -v` would delete it). Hetzner delete and rebuild protection on the server [A]. Object-storage retention or versioning where available [A]. Never run `rm` on the data dir in scripts |

---

## 12. Risks and checks before the cutover

### 12.1 Source access from the target host (required)

A home connection in Israel and a datacenter in Germany or the US can see different responses:
geo-blocking, bot protection, CDN differences.

- **Before migrating the corpus,** run a **fetch-only** probe from the new host. The adapters
  fetch and parse without writing to the DB (extend `scripts/probe_hebrew_rss.py`).
- Compare item counts and titles for the same hour against the PC's worker. **HTTP 200 alone
  does not count.**
- A preliminary signal is favourable (F16), but it came from another datacenter.

### 12.2 Alerting on a stop (required)

| Check on healthchecks.io (free, 20 checks) | Pinged when | Grace period |
|---|---|---|
| `cycle-ok` | after every **succeeded** cycle | ~30 min |
| `data-fresh` | a cycle where ≥1 article was inserted *and* the newest `published_at` is under 3 h old | ~6–8 h, to tolerate quiet nights [E: tune from the data] |
| `backup-ok` | after a successful off-host upload | ~26 h (nightly) or ~8 h (6-hourly) |
| `results-ok` (optional) | after a results sync | ~26 h |

The worker pings outbound only, with a short timeout, and a failed ping never fails a cycle.
This tells apart a dead process (no `cycle-ok`), ingestion that runs but gets nothing
(`data-fresh` goes silent), and failing backups.

### 12.3 Private access

- **Tailscale on the host,** with the node **tagged** (for example `tag:prod`). Key expiry is
  disabled by default for tagged devices; the default for others is 180 days [O].
- `tailscaled` is enabled at boot.
- Serve: `tailscale serve --bg --https=443 http://127.0.0.1:8080`. Whether `--bg` persists across
  a reboot needs **verifying** [A]. The only listener is nginx on 127.0.0.1:8080; the API is not
  exposed by itself.
- **Hetzner Cloud Firewall:** no inbound rules (Tailscale works outbound) [A].
- **Recovery** if tailnet access is lost: the Hetzner web console plus an emergency SSH key.
- **Never `tailscale funnel`.**
- **Cookies, CSRF and origins:**
  - prod `CSRF_ALLOWED_ORIGINS=https://<prod-host>.<tailnet>.ts.net`, `AUTH_COOKIE_SECURE=true`
  - dev origins separate
  - **cookies are scoped to the host, not the port.** If dev is served on the same hostname
    (option A), dev must use a different `AUTH_COOKIE_NAME`
- Prod: `AUTH_SIGNUP_ENABLED=false`, every `ALLOW_*` flag off, refused at startup (#265).

### 12.4 Deploy and rollback

- **Reproducible builds:** a lock file (carve item 1 out of #198) and immutable image tags. Deploy
  by **digest**.
- **`deploy <sha>`:**
  1. back up
  2. pull the digest
  3. `docker compose up -d` with the worker `stop_grace_period: 300s`, so an in-flight cycle
     finishes (F11)
  4. check health: `/health`, the worker heartbeat, then the next cycle succeeding and the
     `cycle-ok` ping arriving
  5. record the digest
- **Schema:** additive startup migrations, which both processes run under `BEGIN IMMEDIATE`
  (F10).
  - A code rollback means redeploying the previous digest. That's normally safe because old
    code ignores new columns [E].
  - **A data restore is a separate, deliberate act:** stop the worker, restore the backup, start.
  - A schema change goes out only with a fresh backup.
- **Worker shutdown:** SIGTERM finishes the current cycle. If it's ever killed mid-cycle, the
  lease is taken over after 30 minutes (F11), which is visible as a short `cycle-ok` gap.

### 12.5 Other risks

| Risk | Mitigation |
|---|---|
| A free LLM tier changes | config switch plus evaluation; rules fallback |
| Dev LLM use exhausts the prod quota | separate keys or orgs (§8.3) |
| A codespace is deleted with unpushed work | push every session; set retention to the 30-day maximum |
| Dev hurts prod (A) | slices, quotas, `oom_score_adj`, no docker group or sudo |
| A free host is reclaimed or throttled (C) | monitoring, off-host backups, a documented move to B |
| The disk fills | log rotation, backup retention, a dev quota (A) |
| Silent charges (GCP, Oracle, a Codespaces card) | prefer hard caps; alerts are only alerts |
| Hetzner raises prices again | the same images and Compose run anywhere |

---

## 13. Phased execution plan

Steps 1–7 are the **critical path**; step 8 can wait.

| # | Step | Result | Depends on | Effort [E] | Extra cost | Owner action | Done when | Rollback |
|---|---|---|---|---|---|---|---|---|
| 1 | **LLM off the PC** (#261, #262) | prod uses a hosted LLM; Ollama stopped | — | 4–8 h + 2–5 days elapsed | $0 (free tier) | create Groq keys (prod and dev), approve the switch | 24 h on the hosted LLM with under 5% failures, Ollama stopped | set the env back to `ollama` |
| 2 | **Choose the architecture and budget** (#267, rewritten) | a decision record | this doc | 1–2 h of owner time | — | **decide**: A, B or C; card or no card; dev hours | the decision is recorded on #267 | — |
| 3 | **Runtime artifacts** (#263, #265, the lock file, monitoring hooks, stop grace) | images built by CI; Compose stack; guards; healthchecks pings | 2 | 15–28 h | $0 (CI free) | create the healthchecks.io account | stack smoke-tested (for example in a codespace with Docker [A]) | revert PRs |
| 4 | **Remote dev workflow** (new devcontainer issue, or the A dev user; #270) | edit, run and test without a local stack | 2 | 3–8 h | $0 | — | one real change made end to end without the local stack | the local dev path still exists |
| 5 | **Host + checks** (#268, the source probe, #266, private access) | VM up with an empty DB; sources verified; backups and drill done; Tailscale and firewall set | 2, 3 | 8–14 h | VM billing starts, hourly (≤ the monthly cap) | create the accounts, the Tailscale tag and the backup key | §12.1–12.3 all green | delete the VM (billing stops) |
| 6 | **Controlled cutover** (#269) | the live system runs on the host | 1, 3, 5 | 3–5 h | — | runs it | per §14 | copy the DB back and run locally (one writer) |
| 7 | **Acceptance** | the hosting requirement is met | 6 | 7 days elapsed | — | keeps the PC off | §14 all checked | — |
| 8 | Deferrable | — | after 7 | — | — | — | — | — |

Deferrable items in step 8:
- Kubernetes/OpenShift manifests (#264) and the Sandbox check
- automated deploys
- IaC
- multi-arch images
- Litestream or continuous replication
- retention (#255)
- Telegram re-enable (#251, milestone 10)
- ONE re-enable (#258)

---

## 14. Acceptance criteria (hosting)

These are **separate from the 14-day product pilot** (#253). Hosting needs no product proof.

- [ ] **The PC stays off for 7 days** while the live system keeps working: at least 95% of
      expected cycles succeed each day, and the feed and results are reachable from the phone.
- [ ] The owner opens the project, changes code, and runs the app and the tests **without Ollama
      or a local stack**.
- [ ] Dev and tests **never write to the live DB and never send real messages**: guards plus
      separation, and a test proves the guard refuses.
- [ ] Dev load is bounded: a test run plus a build while prod runs leaves prod's heartbeat and
      cycle times unaffected (A), or dev is a separate machine (B/C).
- [ ] **Failures are noticed without opening the app.** Stopping the worker triggers an alert
      within the grace period; a failing ingestion triggers `data-fresh`; a failed backup
      triggers `backup-ok`.
- [ ] An **external backup restores** cleanly (drill recorded).
- [ ] The **monthly cost is known** from a real invoice, including VAT and the conditions that
      could raise it.
- [ ] **Promote and roll back are documented and performed once:** dev → PR → CI → deploy, then
      roll back to the previous digest.

---

## 15. Recommendation

**Recommended: B. A Hetzner CX23 (x86, 4 GB) runs the live system with Docker Compose, and
GitHub Codespaces is the development environment.** About **€5.99/month ≈ ₪20.6**, plus $0 for
dev up to about 60 h/month.

Why:

1. It takes **everything** off the PC.
2. It is the lowest *predictable* paid cost, with a **hard stop** on dev spend.
3. It has the **strongest isolation**: AI tools in the dev environment cannot reach the live DB
   or secrets.
4. Nothing extra needs hardening for dev.
5. x86 matches CI and dev.
6. There is a clean upgrade path to A by rescaling the VM, if dev hours grow.

**Second choice: A.** One Hetzner CX33 (8 GB) for both, at **€8.99 ≈ ₪30.9**. It wins if
development regularly exceeds about 60 h/month (at 120 h, B costs ₪54 or blocks), or if you
prefer one persistent box where Claude Code's memory and long jobs live.

**Cheapest that still meets the requirements: C1.** A GCP e2-micro for the live system plus
Codespaces, at **$0**, accepting:
- 1 GB RAM and 0.25 vCPU sustained (performance unproven)
- a card on file with no hard cap
- US latency
- a 1 GB/month egress budget

C2 (Oracle A1) is the $0 option with room for same-VM dev, at a real reclamation and capacity
risk.

**The recommendation changes if:**

| Condition | Then |
|---|---|
| Dev hours regularly go over ~60 per month | **A**, or B with paid Codespaces if isolation matters more than about ₪33/month |
| A strict $0 is required and the risk is acceptable | **C1**; C2 if the capacity is actually granted and reclamation proves a non-issue |
| VAT is charged, or Hetzner raises prices again | re-check C1 and C2, or other EU VPS providers |
| GitHub cuts the Codespaces quota | **A** |
| Long-running dev processes are needed (an overnight dev worker) | **A** |
| A multi-node or HA requirement appears | out of scope: Kubernetes multi-node plus an external DB, reconsidered from scratch |

---

## 16. Proposed changes to issues #261–#270

These are proposals only. **No remote issue was changed.**

| Issue | Proposal |
|---|---|
| #261 provider | **Keep and amend:** strict `json_schema` where supported; `reasoning_effort=low`; record usage (including reasoning tokens); support separate prod and dev keys; document that OpenAI-compatible does not mean identical behaviour |
| #262 evaluate + switch | **Keep and amend:** candidates are Groq `gpt-oss-20b` and `gpt-oss-120b` (production models; exclude preview `qwen3.8-27b` from prod), with Gemini 3.1 Flash-Lite optional; prefer held-out census #3; the metric list from §8.2; budget and elapsed time |
| #263 containerize | **Amend:** Compose is the production runtime; **amd64-only**; bind mount, not a named volume; `stop_grace_period` for the worker; the lock file (from #198); deploy by digest; a `deploy <sha>` script with a pre-backup and health gate; **remove k8s** from scope |
| #264 k8s/OpenShift manifests | **Defer.** Move it out of milestone 13 |
| #265 hosted safety | **Keep and amend:** add `DEPLOY_ENV=dev` guards (refuse Telegram, refuse the prod data path) and a distinct `AUTH_COOKIE_NAME` per environment |
| #266 backups | **Amend:** object storage as the primary off-host target (R2, or B2); `age` public-key encryption with the key offline; a 6-hourly or nightly schedule; the retention policy; RPO/RTO; a restore drill; a backup heartbeat; deletion protections; the PC pull as optional only |
| #267 host decision | **Rewrite:** the decision covers the prod host **and** the dev environment **and** the runtime **and** the budget tier, per §4–§10 |
| #268 provision | **Amend:** the per-decision checklist (firewall, server protection, tagged Tailscale node, persistent Serve, dev user, slices and quotas if A); no k3s |
| #269 cutover | **Amend:** acceptance becomes **the PC off for 7 days**; the source probe, monitoring and restore drill become prerequisites |
| #270 QA without local stack | **Amend:** the dev workflow per alternative; **sanitized** snapshots (auth tables stripped); a dev-only read token; never a local worker |

**New issues proposed:**

1. **External heartbeat monitoring** (healthchecks.io: `cycle-ok`, `data-fresh`, `backup-ok`).
   Required before the cutover.
2. **Source reachability and content probe from the target host** (fetch-only). Required before
   the cutover.
3. **Remote dev environment:** `devcontainer.json` for Codespaces (B/C), or a dev user plus slices
   on the VM (A), plus moving Claude memory.
4. **Dependency lock for reproducible images:** carve item 1 out of #198 into milestone 13.
5. **Linux equivalents** for the Windows-only scripts and docstrings (`worker.ps1`,
   `.venv/Scripts`). Small; can fold into #263 or #270.
6. **Commit `calib.py`** (the census fit/held-out tool, currently only in a temp scratchpad) to
   `backend/scripts/`. Small, and urgent before the temp folder is cleaned.

**Deferred:** #264, the OpenShift Sandbox check, multi-arch images, IaC, automated deploys.

---

## 17. Open questions and the owner's decisions

1. **How many development hours a month do you expect?** This decides between B (≤60 h free)
   and A (fixed price), and whether Codespaces needs a card.
2. **Prod host:** Hetzner CX23 (B), CX33 (A), or a $0 free tier (C1, GCP / C2, Oracle).
3. **A card on file:** acceptable for GCP or Oracle (no hard cap)? For GitHub Codespaces past
   the quota?
4. **Where should Claude Code live:** on a persistent VM (A, memory in one place) or per
   codespace (B, memory copied in)?
5. **LLM:** Groq for prod (free tier), and which provider or key for dev and evaluations, so they
   don't share the prod quota.
6. **Backups:** R2 or B2; a 6-hourly or nightly schedule (RPO 6 h vs 24 h); who keeps the
   offline `age` key.
7. **Region:** Hetzner Germany or Finland (EU latency to Israel) vs GCP US.
8. **Later, not blocking:** ONE re-enable (#258); Telegram re-enable (#251).

**Still unverified** (each with how to check):
- VAT for an Israeli private customer: the first invoice.
- Hetzner CX/CAX specs and snapshot/volume prices: the third-party source vs the console.
- Oracle's PAYG exemption from reclamation: Oracle docs or support.
- The R2 and B2 card requirement: at signup.
- Groq's paid spend controls, and OpenAI/Anthropic prepaid hard-cap behaviour: the consoles.
- Gemini 3.1 Flash-Lite free limits: measure.
- Cerebras paid prices.
- Codespaces architecture (x86_64) and whether a GitHub budget can stop usage once a card is on
  file.
- API and dev-tool memory on Linux, and e2-micro performance: measure after provisioning.
- Source access from the real host: the §12.1 probe.
- Reasoning-token counts at low effort: the §8.2 evaluation.
- `tailscale serve --bg` persistence across a reboot: test on the host.
- Hetzner rescale, firewall and protection features: the console.
- That old code ignores newer columns: a test against a migrated copy.

---

## 18. Sources (all checked 2026-10-13)

- Hetzner — [price adjustment, 15 June 2026](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/) (official prices, excl. VAT and IPv4) · [IPv4 pricing](https://docs.hetzner.com/general/infrastructure-and-availability/ipv4-pricing/) · [billing FAQ](https://docs.hetzner.com/cloud/billing/faq/) (hourly billing with a monthly cap; billed while the server exists) · specs and snapshot/volume prices: [costgoat, updated 5 Sep 2026](https://costgoat.com/pricing/hetzner) (third-party)
- Oracle — [Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- Google Cloud — [Free Tier features](https://docs.cloud.google.com/free/docs/free-cloud-features) · [E2 shared-core machine types](https://docs.cloud.google.com/compute/docs/general-purpose-machines)
- AWS — [Lightsail pricing](https://aws.amazon.com/lightsail/pricing/)
- GitHub — [Codespaces billing](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces) · [timeout](https://docs.github.com/en/codespaces/setting-your-user-preferences/setting-your-timeout-period-for-github-codespaces) · [automatic deletion](https://docs.github.com/en/codespaces/setting-your-user-preferences/configuring-automatic-deletion-of-your-codespaces) · [machine types](https://docs.github.com/en/codespaces/customizing-your-codespace/changing-the-machine-type-for-your-codespace) · [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) · [Packages billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages)
- Red Hat — [Developer Sandbox FAQ](https://developers.redhat.com/developer-sandbox/FAQ)
- k3s — [requirements](https://docs.k3s.io/installation/requirements) · Docker — [Compose deploy spec](https://docs.docker.com/reference/compose-file/deploy/) · VS Code — [Remote host requirements](https://code.visualstudio.com/docs/remote/linux)
- Tailscale — [pricing](https://tailscale.com/pricing) · [key expiry](https://tailscale.com/kb/1028/key-expiry)
- healthchecks.io — [pricing](https://healthchecks.io/pricing/)
- Cloudflare — [R2 pricing](https://developers.cloudflare.com/r2/pricing/) · [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) · [Workers AI JSON mode](https://developers.cloudflare.com/workers-ai/features/json-mode/)
- Backblaze — [B2 pricing](https://www.backblaze.com/cloud-storage/pricing)
- Groq — [models and prices](https://console.groq.com/docs/models) · [rate limits](https://console.groq.com/docs/rate-limits) · [structured outputs](https://console.groq.com/docs/structured-outputs) · [your data](https://console.groq.com/docs/your-data)
- Google Gemini API — [models](https://ai.google.dev/gemini-api/docs/models) · [pricing](https://ai.google.dev/gemini-api/docs/pricing) · [billing and spend caps](https://ai.google.dev/gemini-api/docs/billing)
- OpenAI — [API pricing](https://developers.openai.com/api/docs/pricing) · Anthropic — [pricing](https://claude.com/pricing)
- Cerebras — [rate limits](https://inference-docs.cerebras.ai/support/rate-limits) · [pricing](https://www.cerebras.ai/pricing)
- Exchange rates — [ECB euro reference rates, 12 Oct 2026](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)

---

## Change log

- **2026-10-13 (v2):** rewritten after the owner's clarified requirements.
  - The requirement now covers the development environment, and its urgency no longer depends on
    the product.
  - Project findings were checked in code, measurements and config, with evidence tags.
  - Three full architectures, the interim step, budgets by dev hours and tier, and setup hours
    were compared.
  - **Compose replaces k3s**, and #264 and the Sandbox are deferred.
  - **x86 replaces ARM**: since 15 June 2026 x86 is cheaper at Hetzner.
  - The single-pod claim was corrected: RWO is per node and guarantees no single writer.
  - The LLM table was rebuilt: Groq's qwen3.8-27b is preview-only, Gemini 2.5 Flash-Lite is
    restricted, and Gemini has hard caps.
  - New must-haves: monitoring, the source probe, the lock file, the stop grace period, dev
    guards, and PC-independent encrypted backups.
  - Acceptance is now "the PC off for 7 days", and issue changes are proposed (not applied).
- **2026-10-13 (v1):** first draft for review.
