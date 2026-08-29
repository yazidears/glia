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

Pinned image URLs are passed to fal as generation references. Those images are third-party works used as visual reference for an original output. For a hackathon demo this is fine and it is what reference-conditioned models are for; a product shipping to customers would need a licensing position, and we say so rather than pretending otherwise.

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
