# Mobile Remote Access (Tailscale Serve)

Part of the Private Mobile Access initiative (#16). This is the first working remote-access
setup: the owner's phone reaches the exact same dev-machine app — real backend, real SQLite
data, real local Ollama — over a private connection, from anywhere. It is **not** a production
deployment and does not add hosting, authentication, or public exposure of any kind.

## Architecture

```
Phone (Tailscale app)
  → Tailscale WireGuard tunnel (private tailnet)
    → Tailscale Serve on the PC (HTTPS :443, cert auto-provisioned)
      → Vite dev server (127.0.0.1:5173, fixed port, strictPort)
        → Vite proxy for /api and /health   ← shipped in #17
          → FastAPI/uvicorn (127.0.0.1:8000)
            → SQLite + local Ollama (localhost:11434)
```

This works only because of the same-origin foundation from #17: the browser talks to one
host (the `https://<machine>.<tailnet>.ts.net` URL), and the frontend already uses relative
`/api/...` paths. **Vite and uvicorn keep listening on `127.0.0.1` only** — Tailscale Serve is
the only thing that terminates a network-facing connection, and it is reachable exclusively
inside the private tailnet. No ports are opened on the LAN or WAN. No backend or CORS changes
are involved anywhere in this setup.

The repository is public. Every example below uses a placeholder,
`<machine>.<tailnet>.ts.net` — never write a real personal hostname, tailnet name, or account
detail into a committed file or a GitHub issue/PR.

---

## Prerequisites

- A Tailscale account (free tier is sufficient for a single-user private tailnet).
- The Tailscale app installed on the Windows PC and on the phone, both signed into the **same**
  tailnet.
- The backend and frontend already runnable as documented in
  [`CURRENT_PROJECT_STATE.md` §12](CURRENT_PROJECT_STATE.md#12-how-to-run-locally) — this guide
  assumes that part already works on `localhost`.

---

## One-time setup

Do this once per machine (PC) and once per device (phone). None of it needs to be repeated for
a normal dev session — see [Normal development session](#normal-development-session) below.

1. **Install Tailscale on the Windows PC.**
   ```powershell
   winget install tailscale.tailscale
   ```
   Open a **new** terminal afterward so `tailscale` is on `PATH`.

2. **Install the Tailscale app on the phone** (App Store / Play Store) and sign in with the
   same Tailscale account as the PC.

3. **Sign in on the PC:**
   ```powershell
   tailscale up
   ```
   Confirm both devices now appear in `tailscale status` and belong to the same tailnet.

4. **Enable MagicDNS and HTTPS Certificates** in the Tailscale admin console
   (`https://login.tailscale.com/admin/dns` and `.../admin/settings` → *HTTPS Certificates*).
   Both are default-on for new tailnets — this step is really "confirm," not "configure," for
   most accounts. HTTPS Certificates is what lets Tailscale Serve provision a real Let's
   Encrypt certificate for the `*.ts.net` hostname instead of a self-signed one.

5. **Start Tailscale Serve in background mode**, pointing at the fixed Vite port from #17:
   ```powershell
   tailscale serve --bg 5173
   ```
   The first run provisions a Let's Encrypt certificate (takes roughly 30–60 seconds) and then
   prints the private URL, e.g. `https://<machine>.<tailnet>.ts.net/`. `--bg` persists this
   config across PC reboots — you do not need to re-run `tailscale serve` every session.

6. **Check Serve status:**
   ```powershell
   tailscale serve status
   ```
   Expect a single mapping: `443 → 127.0.0.1:5173`. If you don't have this port memorized,
   this is also the moment to copy the printed `https://<machine>.<tailnet>.ts.net` URL
   somewhere private (password manager, notes app on the phone) — not into this repository.

7. **Confirm Funnel is not enabled** (Funnel would expose the app to the public internet —
   this setup must never use it):
   ```powershell
   tailscale funnel status
   ```
   This should report Funnel is off. `tailscale serve status` output should also contain no
   Funnel section — see [Security model](#security-model).

8. **Set the local allowed-host override** — see the dedicated section below before your first
   session; it's a one-time value to add to your shell profile or `.env.local`-style habit, not
   a repository change.

---

## Normal development session

Once the one-time setup above is done, a normal session is only slightly different from plain
desktop dev — no Tailscale reconfiguration needed:

1. **Start the backend** (unchanged from `CURRENT_PROJECT_STATE.md` §12):
   ```powershell
   cd backend
   .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

2. **Set the allowed-host override in the same shell**, then start the frontend:
   ```powershell
   $env:__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS = "<machine>.<tailnet>.ts.net"
   cd frontend
   npm run dev
   ```
   This environment variable only needs to be set in whatever shell launches `npm run dev` —
   see [Local allowed-host configuration](#local-allowed-host-configuration) for exactly what
   it does and why it must be set per-shell, not per-repository.

3. **Confirm Tailscale Serve is still active** (it persists across reboots via `--bg`, so this
   is usually a no-op check, not a restart):
   ```powershell
   tailscale serve status
   ```
   If it shows nothing, re-run `tailscale serve --bg 5173` from the one-time setup.

4. **Open the private URL from the phone**: `https://<machine>.<tailnet>.ts.net`. Bookmark it
   once so you don't have to remember or retype the hostname.

That's it — desktop `localhost:5173` and phone `https://<machine>.<tailnet>.ts.net` are now two
windows onto the exact same running dev servers, same SQLite data, same Ollama instance.

---

## Local allowed-host configuration

Vite 6 rejects requests whose `Host` header isn't recognized, to prevent DNS-rebinding attacks
against the dev server. The Tailscale Serve hostname is not `localhost`, so without telling
Vite about it, every phone request gets a `403 Blocked request. This host is not allowed.`

The mechanism, confirmed directly against the installed Vite version (`6.4.3`) rather than
assumed:

- `frontend/vite.config.js`'s `server` block does **not** set `allowedHosts` at all, so it
  resolves to Vite's default: an empty array. `localhost`/`127.0.0.1`/LAN-IP style hosts are
  always allowed regardless (a separate built-in check), which is why desktop dev is completely
  unaffected by any of this.
- At server start, Vite reads **one** environment variable,
  `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` (note the double leading underscore — this is an
  internal Vite mechanism, not a `VITE_`-prefixed app env var), and appends its raw value to the
  allowed-hosts list.

**Version note:** in this repository's current Vite version (`6.4.3`), that value is appended
as a single literal string — verified by reading Vite's source
(`server.allowedHosts = [...server.allowedHosts, additionalHost]`, a plain array push, no
splitting) and by an isolated runtime test (a request with `Host: real-hostname` was blocked
when the variable held `real-hostname,other-hostname`, because Vite compared the request's Host
header against the whole joined string, not against each half). Upstream Vite documentation for
newer releases describes support for comma-separated hosts in this variable, so a later Vite
upgrade may change this behavior — re-check the installed version's actual behavior (source or a
quick runtime test, as above) before relying on multiple comma-separated hosts here. Either way,
this setup only ever needs one hostname, so the practical instruction below doesn't change:

Practical consequence for this repository, today: **set this to exactly one exact hostname,
nothing else.**
```powershell
$env:__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS = "<machine>.<tailnet>.ts.net"
```
In Vite `6.4.3` this is the only value that actually works — a comma-separated list is accepted
by neither host. Even on a future Vite version where comma-separated hosts are supported, this
setup still only has one hostname to allow, so keep this value as a single hostname regardless.

This value is **never committed**. It lives only in the shell that launches `npm run dev` for
that session (or in your own local shell profile, which is also outside this repository). The
repository stays fully generic — no `vite.config.js` change, no committed `allowedHosts`
wildcard, and no personal hostname anywhere in tracked files.

---

## Security model

- **The tailnet is the current security boundary.** Access requires being signed into the same
  private Tailscale tailnet as the PC — WireGuard-encrypted, identity-bound devices. There is
  no separate application-level authentication layer, and none is added by this issue.
  (Forward-looking: the approved **User Platform milestone** — `docs/USER_PLATFORM.md`,
  Epic #48 — adds application-level auth with same-origin cookie sessions designed to work
  through this exact Tailscale Serve → Vite proxy chain, including an explicit
  `AUTH_COOKIE_SECURE` env because the HTTPS termination here is invisible to FastAPI.
  Until those PRs land, this paragraph remains the complete security story.)
- **This is single-user private testing, not production authentication.** Do not treat this
  setup as hardened for multi-user or public use.
- **Never enable Tailscale Funnel** for this setup. Funnel republishes a Serve config to the
  public internet — the opposite of the private-access goal here. `tailscale serve status`
  must show only `443 → 127.0.0.1:5173` with no Funnel section, and `tailscale funnel status`
  must report Funnel off.
- **Vite and uvicorn remain bound to `127.0.0.1`** (loopback only), exactly as shipped in #17.
  Nothing in this issue changes that binding, and nothing should.
- **`/docs` and `/openapi.json` are not proxied to the phone.** The Vite dev proxy (from #17)
  only forwards `/api` and `/health`; FastAPI's interactive docs stay desktop-only by design,
  not by omission.
- **Keep `ALLOW_DEV_RESET=false`** in `backend/.env` between active QA/reset sessions. It gates
  `POST /api/dev/reset-rss-data` and the LLM-gating benchmark endpoint — destructive/expensive
  operations that shouldn't be one accidental phone tap away outside a deliberate reset session.
- **The repository is public.** `backend/.env` and `frontend/.env.local` are both gitignored
  and may hold real API keys or the personal Serve hostname — never commit them, and never
  paste their contents into an issue, PR, or commit message.

---

## Troubleshooting

**"Blocked request. This host is not allowed." in the browser / Vite terminal output**
The phone's request Host header (the `*.ts.net` hostname) isn't in Vite's allowed-hosts list.
Set `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` in the *same shell* before `npm run dev` — see
[Local allowed-host configuration](#local-allowed-host-configuration). Restart `npm run dev`
after setting it; Vite reads the variable once, at server start.

**Set the variable but it's still blocked**
Almost always one of:
- The value has a comma or a second hostname in it — in the currently installed Vite version
  (`6.4.3`), only one exact hostname is supported, see
  [Local allowed-host configuration](#local-allowed-host-configuration) for why.
- The value was set in a different terminal/shell than the one running `npm run dev`.
- The value has a typo, trailing slash, or `https://` prefix — it must be the bare hostname
  only (`<machine>.<tailnet>.ts.net`, no scheme, no path).
- The machine was renamed since the value was set — see below.

**Certificate/HTTPS not ready yet**
The first `tailscale serve --bg 5173` provisions a Let's Encrypt certificate, which can take
30–60 seconds. If the phone shows a certificate error or "not secure" warning immediately after
running the command, wait roughly a minute and reload. Note the certificate publishes the
hostname (not any repository or account content) to public Certificate Transparency logs —
this is normal and expected for any `*.ts.net` HTTPS certificate, and is not itself a privacy
issue since the hostname alone doesn't grant access without also being on the tailnet.

**`tailscale serve status` shows something unexpected, or a Funnel line appears**
Run `tailscale funnel off` immediately if a Funnel section is present. Re-run
`tailscale serve --bg 5173` to restore the intended `443 → 127.0.0.1:5173` mapping. If the port
number looks wrong, it likely means Vite didn't start on 5173 — check `strictPort` didn't
already fail (see below).

**PC went to sleep, or was shut down**
Tailscale Serve, uvicorn, and Vite are all just processes/config on the PC — if the PC sleeps
or shuts down, the phone loses access entirely (this is expected; there is no cloud component).
Wake or turn on the PC and restart the dev servers per
[Normal development session](#normal-development-session). Consider disabling PC sleep during
an active phone-testing session (Windows Settings → Power) if this becomes annoying — this is
a Windows setting, not something this repository configures.

**Vite HMR doesn't seem to update the page on the phone**
Vite's default HMR client behavior is left unchanged by this issue — no `server.hmr` config
was added to `vite.config.js`. In most Tailscale Serve setups this works out of the box, since
Serve proxies both the HTTP and the WebSocket upgrade for the same origin. If it genuinely
doesn't reconnect after a save, a manual phone browser refresh always picks up the latest code
(exactly like a normal dev server) while you investigate further. If a real, observed HMR
failure needs a `server.hmr` override, treat that as a separate, deliberate follow-up — do not
speculatively add HMR config against a problem that hasn't actually been confirmed.

**Machine renamed / hostname changed**
Renaming the PC (or re-registering it in the tailnet) changes the `*.ts.net` hostname. After a
rename: re-run `tailscale serve --bg 5173` if the mapping didn't carry over, update the
`__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` value to the new hostname, restart `npm run dev`, and
re-bookmark the new URL on the phone.

**Frontend or backend restart**
Restarting either dev server does not require touching Tailscale at all — Serve keeps
forwarding to `127.0.0.1:5173` regardless of whether Vite is currently up or mid-restart (the
phone briefly sees a connection error during the restart, then recovers once Vite is back, the
same way a desktop browser tab would). Remember to re-set
`__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` in the shell if you're restarting the frontend from a
fresh terminal.

---

## What changes for real hosting later

If this app is ever hosted for real (out of scope for this initiative), the Vite dev proxy is
replaced by an actual reverse proxy or static hosting + API gateway — but the relative-`/api`
contract established in #17 stays exactly the same, so the frontend code itself would not need
to change for that transition.

---

## Validation

### Agent-verifiable (performed as part of this issue)

- [x] `docs/MOBILE_REMOTE_ACCESS.md` exists and covers every bullet in the issue's Scope section
- [x] `README.md` docs list includes this file
- [x] No personal hostname, tailnet name, account detail, or secret appears anywhere in this
      file or any other committed file changed by this PR (only the `<machine>.<tailnet>.ts.net`
      placeholder is used)
- [x] `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` behavior described here matches the installed
      Vite version's actual source and was confirmed with an isolated runtime test (not just
      assumed from the issue description)
- [x] No application code was changed by this PR — `frontend/vite.config.js`,
      `frontend/src/api/client.js`, and the backend are untouched
- [x] Frontend and backend test suites re-run unchanged (regression only) — see the PR for
      exact results

### User-run physical-device validation (owner only — not claimed here)

These require an actual phone, an actual Tailscale account, and actual LTE connectivity that
this environment does not have. They are **not checked and not claimed** by this
implementation:

- [ ] Phone on the same Wi-Fi: Feed loads via `https://<machine>.<tailnet>.ts.net`
- [ ] Phone on LTE (Wi-Fi off): Feed loads, profile switch works, a feedback action POSTs
      successfully
- [ ] Remote HMR: editing a frontend file hot-updates the page open on the phone
- [ ] `netstat -ano | findstr :5173` shows only a `127.0.0.1` binding
- [ ] `tailscale serve status` shows `443 → 127.0.0.1:5173` and no Funnel line

Per the Epic (#16): **implementation completion does not equal issue acceptance.** This issue
stays open until the owner completes the checklist above.
