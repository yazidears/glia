# Entire side-challenge workflow

## Ready state

- Entire CLI installed and authenticated.
- Repository enabled for Codex capture.
- Codex lifecycle hooks installed, reviewed, and trusted.
- Entire cross-agent skills available.
- Local diagnostics pass with `entire doctor`.
- No Git remote configured; checkpoints stay local until Yazide explicitly approves a push.

## During the hackathon

Create one logical commit after each demo-safe milestone:

```bash
git status --short
git add <only-the-files-for-this-milestone>
git diff --cached --check
git commit -m "Describe the completed milestone"
entire checkpoint list
```

Suggested milestones:

1. First fixture-backed vertical demo flow.
2. First real provider-backed result.
3. Polished and failure-safe demo experience.
4. Submission-ready build and recorded backup.

## Before every commit

- Confirm the app still launches and the core flow works.
- Keep `.env*` values, provider tokens, attendee information, and real customer data out of Git.
- Stage only files belonging to the milestone.
- Use a clear message so judges can understand the build progression.

## Verification

```bash
entire status
entire doctor
entire checkpoint list
```

`entire status` should show the active Codex session. After a successful milestone commit, `entire checkpoint list` should show its checkpoint.
