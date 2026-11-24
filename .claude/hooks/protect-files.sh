#!/bin/bash
# Claude Code PreToolUse hook for the file tools
# (Read, Edit, Write, MultiEdit, NotebookEdit, Grep, Glob).
#
# What it enforces:
#   1. Confinement: file tools may only touch the project, ~/.claude (Claude Code
#      config and memory) and Claude Code's temp folder /tmp/claude-<uid>.
#   2. Secrets (.env files, private keys, credentials) are blocked for reading
#      and writing. Templates such as .env.example are allowed.
#   3. Some files are write-protected: git internals, package-lock.json, the
#      global Claude Code settings and this project's guardrails
#      (.claude/settings*.json and .claude/hooks/), which only a human changes.
#
# Exit 0 = allow, exit 2 = block (the message on stderr is shown to Claude).
# Fails closed: if the input can't be validated, the action is blocked.
# Written for /bin/bash 3.2 (the macOS default), so it runs everywhere.
set -u

deny() { echo "Blocked: $1" >&2; exit 2; }

command -v jq >/dev/null 2>&1 || deny "jq is not installed; cannot validate (failing closed)"
[ -n "${CLAUDE_PROJECT_DIR:-}" ] || deny "CLAUDE_PROJECT_DIR is not set; cannot validate (failing closed)"
[ -n "${HOME:-}" ] || deny "HOME is not set; cannot validate (failing closed)"

INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | jq -er '.tool_name' 2>/dev/null) \
  || deny "could not parse hook input (failing closed)"
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
[ -n "$CWD" ] || CWD="$CLAUDE_PROJECT_DIR"

# Every path-like field the file tools use (Grep/Glob use .path, notebooks .notebook_path).
PATHS=$(printf '%s' "$INPUT" | jq -r '
  [.tool_input.file_path, .tool_input.notebook_path, .tool_input.path]
  | map(select(type == "string" and . != "")) | .[]' 2>/dev/null) \
  || deny "could not parse tool input (failing closed)"

# A Glob pattern can point outside the project by itself ("/etc/*", "~/x/**", "../*"):
# check the part before the first wildcard.
if [ "$TOOL" = "Glob" ]; then
  PATTERN=$(printf '%s' "$INPUT" | jq -r '.tool_input.pattern // empty' 2>/dev/null)
  case "$PATTERN" in
    /*|"~"*|*..*)
      PREFIX=$(printf '%s' "$PATTERN" | sed 's/[*?[{].*//')
      PATHS=$(printf '%s\n%s' "$PATHS" "${PREFIX:-.}")
      ;;
  esac
fi

# Nothing to check (e.g. Grep/Glob without a path search the project)
[ -z "$PATHS" ] && exit 0

case "$TOOL" in
  Edit|Write|MultiEdit|NotebookEdit) WRITE=1 ;;
  *) WRITE=0 ;;
esac

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

# Turn a path into an absolute, symlink-free, lowercase path.
# Lowercase because the default macOS filesystem is case-insensitive
# (".ENV" is the same file as ".env").
resolve() {
  local p="$1" out
  case "$p" in
    "~") p="$HOME" ;;
    "~/"*) p="$HOME/${p:2}" ;;
  esac
  case "$p" in
    /*) ;;
    *) p="$CWD/$p" ;;
  esac
  # macOS has no `realpath -m`; python3 resolves "..", "." and symlinks,
  # even for files that don't exist yet.
  out=$(python3 -I -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$p" 2>/dev/null)
  if [ -z "$out" ]; then
    # Without python3, refuse paths that can't be normalized safely.
    case "/$p/" in
      */../*|*/./*) return 1 ;;
    esac
    out="$p"
  fi
  lower "$out"
}

# Folders the file tools may use. /tmp is a symlink to /private/tmp on macOS,
# so both spellings are listed in case python3 is unavailable.
UID_NUM=$(id -u)
ROOTS=()
for root in "$CLAUDE_PROJECT_DIR" "$HOME/.claude" "/tmp/claude-$UID_NUM" "/private/tmp/claude-$UID_NUM"; do
  resolved=$(resolve "$root") && ROOTS+=("$resolved")
done
HOME_CLAUDE=$(resolve "$HOME/.claude") || deny "could not resolve ~/.claude (failing closed)"
PROJECT_CLAUDE=$(resolve "$CLAUDE_PROJECT_DIR/.claude") || deny "could not resolve the project's .claude folder (failing closed)"

is_inside_allowed_root() {
  local root
  for root in "${ROOTS[@]}"; do
    case "$1/" in
      "$root"/*) return 0 ;;
    esac
  done
  return 1
}

# Secrets: blocked for read AND write
is_secret() {
  local p="$1" base="${1##*/}"
  case "$p/" in
    */secrets/*|*/.ssh/*|*/.aws/*|*/.gnupg/*) return 0 ;;
  esac
  case "$base" in
    .env.example|.env.sample|.env.template|.env.dist) return 1 ;;
    .env|.env.*|.envrc|*.pem|*.key|*.p12|*.pfx|id_rsa*|id_ed25519*|id_ecdsa*|.netrc|.npmrc|.credentials.json) return 0 ;;
  esac
  return 1
}

# Blocked for write only (reading is fine)
is_write_protected() {
  local p="$1" base="${1##*/}"
  case "$p/" in
    */.git/*) return 0 ;;
  esac
  [ "$base" = "package-lock.json" ] && return 0
  # Global Claude Code settings: ~/.claude/settings.json, settings.local.json, ...
  case "$p" in
    "$HOME_CLAUDE"/settings*.json) return 0 ;;
  esac
  # This project's guardrails: changed by a human only
  case "$p/" in
    "$PROJECT_CLAUDE"/hooks/*) return 0 ;;
  esac
  case "$p" in
    "$PROJECT_CLAUDE"/settings*.json) return 0 ;;
  esac
  return 1
}

while IFS= read -r raw; do
  [ -z "$raw" ] && continue
  p=$(resolve "$raw") || deny "$raw cannot be resolved safely (failing closed)"
  is_inside_allowed_root "$p" \
    || deny "$raw is outside the allowed folders (the project, ~/.claude, Claude Code's temp folder)"
  is_secret "$p" && deny "$raw is a protected secret path"
  if [ "$WRITE" = 1 ] && is_write_protected "$p"; then
    deny "$raw is write-protected"
  fi
done <<< "$PATHS"

exit 0
