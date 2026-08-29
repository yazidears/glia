# Security model

Most web apps fetch from hosts they chose. **Glia fetches from hosts the open web chose for it** — article pages surfaced by Cala citations and image results from public corpora — and then decodes whatever images it finds there. That is the defining security fact about this product, and it drives everything below.

Nothing here is aspirational. Unimplemented controls are marked **TODO**.

## Threat model

| # | Threat | Why it applies to us | Control |
|---|---|---|---|
| **T1** | **SSRF via discovered URLs** | The reference fetcher requests URLs we did not choose. A hostile or compromised page can redirect to `169.254.169.254`, `localhost`, or an internal address. **This is the primary threat.** | Scheme allowlist (`https` only), DNS resolution checked against private/loopback/link-local/CGNAT ranges **before** connecting, redirects capped at 2 and re-validated at every hop, no proxy trust, connect timeout 3 s / total 8 s. Aikido Zen SSRF detection as defence in depth. |
| **T2** | **Malformed or hostile media** | We decode arbitrary remote images. Decoder bugs and decompression bombs are real. | `HEAD` first, reject non-`image/*` content types, hard byte cap (5 MB) enforced during streaming not after, `Image.MAX_IMAGE_PIXELS` set, decode inside a try/except that discards on any exception, never trust the extension. |
| **T3** | Provider key exfiltration | Five server-side keys. A fal `ADMIN` key can deploy and delete apps and mint further keys. | Keys live only in the FastAPI process. `apps/web` receives none. Use an `API`-scoped fal key. Secrets scanning at commit time and in CI. |
| **T4** | Ephemeral token abuse | The browser holds an OpenAI realtime token. | 600-second TTL, minted per session, scoped to a **transcription** session, `OpenAI-Safety-Identifier` set to a hashed user id. Never mint from an unauthenticated route. |
| **T5** | Voice PII reaching third parties | People say names, addresses and phone numbers while thinking out loud. That text flows into Cala queries and the fal prompt. Pioneer states it may use data to improve models by default. | `X-Fal-Store-IO: 0` on every fal call. GLiNER2-PII redaction before egress (**TODO** — see `docs/PARTNERS.md` §3). Transcripts are session-scoped and deletable. |
| **T6** | Cost exhaustion | Cala bills per query and a speech loop can fire continuously. fal bills per output. | Distiller gate, 8-second debounce, Postgres response cache, Redis credit ledger with a hard ceiling that refuses rather than overspends, per-session generation cap. |
| **T7** | Malicious dependency | Six SDKs plus a large JS tree, installed under time pressure. | safe-chain intercepts pnpm **and** uv installs. Frozen lockfiles in CI. Aikido SCA on both lockfiles. |
| **T8** | Injection into our datastores | Transcript text and remote metadata reach Postgres and Redis. | Parameterised queries only. Zen blocks SQLi/NoSQLi/command injection/path traversal at runtime. |
| **T9** | XSS via remote metadata | Image titles, author names, licence strings and `og:` tags come from untrusted pages and render in our UI. | Treated as text, never HTML. No `dangerouslySetInnerHTML` anywhere. Nonce-based CSP with no `unsafe-inline`. Remote image hosts constrained by CSP `img-src`. |
| **T10** | Prompt injection via page content | Scraped `og:description` and article text can carry instructions, and that text can reach the synthesis model. | Scraped text is used for ranking only, never placed in a model prompt as instructions. The synthesis prompt is built from the transcript, the distilled attributes and pinned image *metadata we control* — delimited and labelled untrusted. |
| **T11** | Secret committed to a public repo | Public repo, one day, three people. | Aikido pre-commit secrets hook on all three machines, Aikido secrets scanning with live validation, Entire's five always-on redaction passes on captured transcripts. |
| **T12** | Session hijack | Standard. | httpOnly + Secure + SameSite=Strict cookies, short-lived tokens. WebSocket connections authenticated at handshake and bound to a session id. |

## The image fetcher

This is the one module to get right. Everything else in the app is ordinary.

```
url ──▶ scheme allowlist (https only)
    ──▶ resolve DNS, reject private / loopback / link-local / CGNAT / IPv6-mapped
    ──▶ HEAD: content-type must be image/*, content-length under cap
    ──▶ GET with byte budget enforced while streaming
    ──▶ redirects: max 2, every hop re-validated from scratch
    ──▶ decode with Pillow, MAX_IMAGE_PIXELS set, discard on any exception
    ──▶ reject under ~400px on the short edge
    ──▶ perceptual hash, dedupe against the session set
    ──▶ candidate
```

Rules that are easy to get wrong and must not be:

- **Re-validate after every redirect.** Validating only the first URL is the classic SSRF bypass.
- **Enforce the byte cap while streaming.** `Content-Length` is attacker-controlled and may be absent.
- **Never pass a user-supplied or remote-supplied URL to the fetcher without going through this path.** One helper function, one entry point, no exceptions.
- **Do not follow `http://`.** Not even to upgrade it.

Concurrency is bounded by a semaphore. A hostile page will not be allowed to open fifty sockets.

### A note on hotlinking

Lane A candidates are displayed from their origin URLs. That is normal reference behaviour and keeps attribution intact, but it means our page requests third-party hosts from the user's browser. CSP `img-src` is scoped accordingly, and the referrer is stripped. We do **not** re-host Lane A images. Lane B images are permissively licensed and displayed with their licence and author.

### Pinned references are re-hosted, not hotlinked to fal

A pinned image is **not** handed to fal as an origin URL. Two things make that impossible: a grid tile's display URL is our own `/api/image` proxy on localhost, which fal cannot reach at all, and fal's fetcher sends a blank User-Agent that `upload.wikimedia.org` answers with 403.

So the bytes go through us. `generation/references.py` reads the pin's `origin_image_url`, fetches it through the fetcher above — same allowlist, same resolved-address check, same redirect refusal, same byte cap, no relaxed path — and uploads it to fal's storage. What the model receives is a URL on fal's own CDN.

Two consequences worth stating:

- The one new outbound request to a remote-supplied URL is the `PUT` to fal's `upload_url`. It cannot use the host allowlist — fal chooses that host — so it gets the rest: https only, plus the same resolved-address check via `fetch.resolves_publicly()`, which is now the single definition of "not public" for every outbound request built from a URL we did not hardcode. "Nothing is read back, so it is not SSRF" is **not** the argument and should not be used as one: a blind write to an internal endpoint is a real primitive, and the guard does not depend on the direction of the data.
- A reference that cannot be fetched or uploaded is dropped, never repaired by falling back to the display URL. The generation proceeds without it and the response names the pin.

Those images are third-party works used as visual reference for an original output, and re-hosting them on fal's storage is a copy we did not previously make. For a hackathon demo this is fine and it is what reference-conditioned models are for; a product shipping to customers would need a licensing position, and we say so rather than pretending otherwise.

## Runtime — Aikido Zen

`aikido_zen.protect()` is the **first statement** in the API entrypoint, before any other import. `AikidoFastAPIMiddleware` adds per-route rate limiting and user identification.

Run `AIKIDO_BLOCK=false` (detect-only) while building — our fetcher deliberately talks to unfamiliar hosts, and a false positive at 18:00 would break the demo. Flip to `AIKIDO_BLOCK=true` at 17:30, then re-run the happy path before recording.

## Supply chain

- `@aikidosec/safe-chain` on every dev machine and in CI (`--ci`). Blocks known-malicious and <48h-old packages across pnpm and uv.
- `pnpm install --frozen-lockfile`, `uv sync --frozen`. Never unfreeze to make a build green.
- Aikido SCA reads `pnpm-lock.yaml` and `uv.lock`, including subfolders. Both committed.
- CycloneDX SBOM exported via Aikido's public API and rendered in the app's own security panel.

## Data handling

**Audio never reaches our servers.** The browser streams directly to OpenAI over WebRTC; we only receive settled transcript text. This is a deliberate architectural choice — it removes an entire category of storage, retention and breach exposure.

Transcripts, candidates, pins and generations are session-scoped rows in Postgres, deletable by session id. Redis holds only caches, hashes and counters, all with TTLs.

Logs are structlog JSON with a request id. **Transcript content is never logged** — token counts and hashes only.

## HTTP hardening

Nonce-based CSP, no `unsafe-inline`, no `unsafe-eval`, `img-src` scoped to the lanes we permit. HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` (we do not leak our origin to scraped hosts), COOP/COEP. CORS restricted to the deployed web origin, no wildcards. Body size limits and per-route timeouts everywhere. WebSocket messages are size-capped and schema-validated on arrival.

## What we are explicitly not doing today

Stated plainly, because a jury respects a known limitation more than a silent gap.

- No SOC 2, no pentest, no formal key rotation schedule.
- No user accounts in the hackathon build — sessions are anonymous and ephemeral.
- PII redaction of transcripts before egress is designed and documented but **TODO**.
- Aikido's free tier cannot gate CI on SAST findings, only dependency findings. SAST findings are visible in the dashboard and triaged by hand.
- Entire checkpoints in a public repo are public. Redaction is strong but it is redaction, not encryption. We do not paste credentials into agent sessions.
- No licensing position on reference-conditioned generation from third-party images. Fine for a demo, not for a product.

## Incident procedure during the event

A leaked key is a five-minute problem if handled immediately and a lost hackathon if hidden.

1. Revoke the key in the vendor console. First, before anything else.
2. Rotate, update the deployment env, redeploy.
3. `git push --force` does **not** remove a secret from a public repo. Assume compromise the moment it lands — revoke, do not scrub.
4. Tell the team in the channel. No silent fixes.

---

# Public-repo audit checklist

**This repository is public, and Aikido will scan it.** The rules require a public GitHub repo with full source, and the Aikido side challenge means the codebase is not just a means to a demo — it is a judged artefact in its own right. A scanner will read this code with no sympathy for the deadline.

Two consequences shape how we work:

1. **Anything committed is published, permanently.** A secret pushed at 18:50 is compromised at 18:50. `git push --force` does not unpublish it — GitHub keeps unreferenced objects, forks retain them, and crawlers index public pushes within seconds. The only remedy is revocation.
2. **Findings are visible.** Aikido's dashboard will show what it found. A clean scan is a claim we can make on stage; a scan we never ran is a question we cannot answer.

## Set this up first, not last

Before the first line of application code:

```bash
# 1. secrets pre-commit hook — on ALL THREE machines, no exceptions
curl -fsSL https://raw.githubusercontent.com/AikidoSec/pre-commit/6cc79e039ee78b206520f143d618a44665c904b3/installation-samples/install-global/install-aikido-hook.sh | bash

# 2. supply-chain guard, before any install
curl -fsSL https://github.com/AikidoSec/safe-chain/releases/latest/download/install-safe-chain.sh | sh
npm safe-chain-verify

# 3. verify .env is ignored BEFORE it exists
git check-ignore -v .env    # must print a .gitignore line; if it prints nothing, stop
```

Then connect the repo in Aikido (GitHub App, this repository only) so the baseline scan runs while the repo is still empty. A baseline from hour one means every later finding is attributable to a specific change.

## Findings this stack will actually produce

Anticipate these. Each is a real pattern Aikido's SAST (Aikido Engine + Opengrep, with cross-file taint analysis) flags on FastAPI and React.

| Finding | Where it comes from | What we do |
|---|---|---|
| **SSRF** | `glia/discovery/fetch.py` — a URL from a remote response reaching an HTTP client. Taint analysis will follow it. | **Expect this flag, and welcome it.** The guard chain in the previous section is the answer. If Aikido still flags it after validation, do not suppress it silently — add a comment naming the control, and be ready to explain the validator on stage. A flagged-and-defended SSRF path reads better to a security judge than an unflagged one nobody thought about. |
| **CORS misconfiguration** | `CORSMiddleware` with `allow_origins=["*"]` **and** `allow_credentials=True`. Classic FastAPI finding, and it is a genuine vulnerability, not a false positive. | Explicit origin list from `WEB_ORIGIN`. Never a wildcard with credentials. |
| **Hardcoded secret** | A key pasted into a test, a notebook, a curl example in a doc, or a default argument. | Everything from env. `.env.example` holds names and safe defaults only — never a real value, not even a truncated one. |
| **SQL injection** | Any f-string or `%`-formatting reaching `execute()`. | Parameterised queries only. SQLAlchemy expression language, never string concatenation. |
| **Path traversal** | Writing a cached image using a filename derived from a remote URL. | Store by content hash, never by remote-supplied name. |
| **XSS** | `dangerouslySetInnerHTML` anywhere; rendering remote `og:` metadata, licence strings or author names as markup. | Text nodes only. There is no legitimate use of `dangerouslySetInnerHTML` in this app. |
| **Command injection** | `subprocess` with `shell=True`, e.g. shelling out to an image tool. | Use Pillow in-process. If a subprocess is unavoidable, argument list, never a shell string. |
| **Insecure deserialisation** | `pickle`, or `yaml.load` without `SafeLoader`, on anything remote. | JSON only for external data. |
| **Container findings** | Dockerfile running as root, unpinned base image, secrets in build args. | Pinned digest, `USER app` non-root, secrets at runtime only. |
| **Vulnerable dependency** | Whatever ships with a CVE today. | This is the class that **gates CI on the free tier**. Keep both lockfiles frozen and green. |
| **Verbose error responses** | A stack trace or an upstream vendor error body returned to the client. | RFC 9457 problem details, correlation id, details in the logs only. |

## Public-repo specifics

- **Entire checkpoints are stored in this repository's git refs — on a public repo they are public.** Five redaction passes run automatically and we enable the optional PII and privacy-filter layers on top, but that is redaction, not encryption. Never paste a real credential into an agent session, and never assume the redactor will catch a novel format.
- **No internal hostnames, staging URLs, dashboard links or personal emails** in code, comments or docs.
- **`.env.example` is documentation, not configuration.** Names and safe defaults. Read it once, deliberately, before the final push.
- **Screenshots and the demo video** must not show a dashboard with a live key, an authorization header in devtools, or an open `.env` in an editor. This is the most common way a hackathon leaks a credential.
- **Branch protection on `main`** if there is time. Not essential for a one-day project, but it prevents a panicked force-push at 18:55 from destroying history.

## Before the final push

Run these in order. All of them, once, deliberately.

```bash
# nothing sensitive staged
git status --short --untracked-files=all

# .env has never been committed, in the entire history
git log --all --full-history --name-only -- .env .env.local | head
# ^ must be empty

# no key-shaped strings anywhere in the tree
grep -rInE '(sk-[A-Za-z0-9]|AIK_|pio_sk_|ghp_|xox[baprs]-|-----BEGIN [A-Z ]*PRIVATE KEY)' \
  --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv . || echo "clean"

# frozen, reproducible installs
pnpm install --frozen-lockfile && (cd apps/api && uv sync --frozen)

# full local scan, all scanners
docker run --rm -v "$PWD:/repo" aikidosecurity/local-scanner:latest \
  aikido-local-scanner scan /repo --apikey "$AIKIDO_API_KEY" \
  --repositoryname glia --branchname main \
  --scan-types code dependencies iac secrets --fail-on critical
```

Then, in the Aikido dashboard: trigger a rescan (the free tier rescans only every 3 days, so the automatic one may be stale), confirm zero open critical findings, and export the CycloneDX SBOM — it is worth having on screen.

## Final checklist

- [ ] Repo is **public**
- [ ] `.env` never committed — verified against full history, not just the working tree
- [ ] No key-shaped string anywhere in the tree
- [ ] Aikido GitHub App connected, scan run **today**, zero open criticals
- [ ] CI workflow present and passing, gating on new critical dependency findings
- [ ] safe-chain and the secrets pre-commit hook installed on all three machines
- [ ] Zen running with `AIKIDO_BLOCK=true`, happy path re-tested after the flip
- [ ] Both lockfiles committed and frozen
- [ ] No `dangerouslySetInnerHTML`, no `shell=True`, no wildcard CORS with credentials
- [ ] Dockerfiles run as non-root with pinned base images
- [ ] Demo video and screenshots reviewed frame by frame for exposed credentials
- [ ] Every key rotated if there is **any** doubt about exposure

If a key is exposed: revoke first, rotate second, tell the team third. Never scrub and hope.
