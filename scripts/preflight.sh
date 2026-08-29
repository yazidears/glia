#!/usr/bin/env bash

set -u

failures=0
warnings=0

ok() { printf 'OK    %s\n' "$1"; }
warn() { printf 'WARN  %s\n' "$1"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }

has_command() {
  if command -v "$1" >/dev/null 2>&1; then
    ok "$1 is installed"
  else
    fail "$1 is missing"
  fi
}

printf 'Hackathon preflight\n\n'

has_command git
has_command bun
has_command gh
has_command entire
has_command codex
has_command curl

if command -v bun >/dev/null 2>&1; then
  ok "Bun $(bun --version) is the default JavaScript runtime"
fi

node_version=$( (node --version) 2>/dev/null )
if [ -n "$node_version" ]; then
  ok "Node $node_version works"
else
  warn "Homebrew Node is unusable; stay on Bun unless Node is repaired deliberately"
fi

codex_version=$( (codex --version) 2>/dev/null )
if [ -n "$codex_version" ]; then
  ok "$codex_version works"
else
  fail "Codex CLI did not start"
fi

if gh auth status >/dev/null 2>&1; then
  ok "GitHub CLI is authenticated"
else
  warn "GitHub CLI is not authenticated"
fi

if entire version >/dev/null 2>&1; then
  ok "Entire CLI responds"
  entire_state=$(entire status 2>&1 || true)
  if printf '%s' "$entire_state" | grep -q '^● Enabled'; then
    ok "Entire is enabled for this repository"
  else
    warn "Entire is not enabled here yet; finish login, then run: entire enable -y --agent codex"
  fi
fi

if curl --silent --head --max-time 5 https://luma.com/barcelona-summer-lock-in >/dev/null 2>&1; then
  ok "Internet and event page are reachable"
else
  warn "Could not reach the event page"
fi

free_gb=$(df -g . | awk 'NR==2 {print $4}')
if [ "${free_gb:-0}" -ge 10 ]; then
  ok "${free_gb} GiB free on the current volume"
else
  warn "Only ${free_gb:-unknown} GiB free on the current volume"
fi

printf '\nOptional provider environment names (values are never printed)\n'
for name in OPENAI_API_KEY CALA_API_KEY PIONEER_API_KEY FAL_KEY; do
  if [ -n "${!name:-}" ]; then
    ok "$name is present in this shell"
  else
    warn "$name is not present; on-site credits may provide it"
  fi
done

printf '\nResult: %s failure(s), %s warning(s)\n' "$failures" "$warnings"

if [ "$failures" -gt 0 ]; then
  exit 1
fi
