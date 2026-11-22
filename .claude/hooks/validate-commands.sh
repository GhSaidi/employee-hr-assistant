#!/bin/bash
# Claude Code PreToolUse hook for the Bash tool.
#
# Decisions:
#   exit 2              -> block (the message on stderr is shown to Claude)
#   "ask" JSON + exit 0 -> force a confirmation prompt, whatever the permission mode
#   exit 0, no output   -> no objection (the normal permission rules still apply)
#
# This is pattern matching on the command text: it catches mistakes and obvious
# misuse, it is not a security boundary. Fails closed if the input can't be read.
# Written for /bin/bash 3.2 (the macOS default), so it runs everywhere.
set -u

deny() { echo "Blocked: $1" >&2; exit 2; }
ask() {
  jq -n --arg r "$1" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $r}}'
  exit 0
}

command -v jq >/dev/null 2>&1 || deny "jq is not installed; cannot validate (failing closed)"

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -er '.tool_input.command' 2>/dev/null) \
  || deny "could not parse command (failing closed)"

# Normalize: lowercase, single line, no quotes or backslashes
# (defeats tricks like r"m", \rm, c'a't and multi-line commands).
LC=$(printf '%s' "$CMD" | tr '[:upper:]' '[:lower:]' | tr '\n' ' ' | tr -d "\"'" | tr -d '\\')

m() { grep -qE -- "$1" <<< "$LC"; }

# Start of a command word: line start, separator, subshell, backtick, path slash, whitespace
SEP='(^|[;&|(`/[:space:]])'
# End of a command word
END='([[:space:];&|)`]|$)'

# ---------- DENY ----------

# Deleting files: never done by Claude, deletions are left to a human.
# Also catches "git rm", "xargs rm", "/bin/rm" and r"m" (rm as its own word).
m "${SEP}(rm|rmdir|unlink|shred|srm|trash)${END}" \
  && deny "deleting files is not allowed; give the command to the user to run"
m "${SEP}git[[:space:]]+clean${END}" \
  && deny "git clean deletes files; give the command to the user to run"
m "${SEP}find[[:space:]].*[[:space:]]-delete${END}" \
  && deny "find -delete deletes files; give the command to the user to run"

# Pipe-to-shell / pipe-to-interpreter / process substitution / eval
m '\|[[:space:]]*(sudo[[:space:]]+)?(ba|z|da|k|c|fi)?sh([^[:alnum:]_-]|$)' \
  && deny "pipe-to-shell pattern"
m '\|[[:space:]]*(python3?|perl|ruby|node)([[:space:]]+-)?([;&|]|$)' \
  && deny "pipe-to-interpreter pattern"
m "${SEP}((ba|z|da)?sh|source)[[:space:]]+(-[a-z]+[[:space:]]+)*<\(" \
  && deny "process-substitution execution"
m "${SEP}eval[[:space:]]" \
  && deny "eval is not allowed"

# Network tools (permission rules only match the start of a command; this also catches chains)
m "${SEP}(curl|wget|nc|ncat|netcat|telnet|ftp|scp|sftp)${END}" \
  && deny "network tool"

# Privilege escalation / world-writable files
m "${SEP}(sudo|su|doas)${END}" && deny "privilege escalation"
m 'chmod[[:space:]]+(-[a-z]+[[:space:]]+)*(777|a\+rwx)' && deny "world-writable chmod"

# Destructive SQL
m 'drop[[:space:]]+(table|database|schema|index)|truncate[[:space:]]+table|delete[[:space:]]+from' \
  && deny "destructive SQL"

# Force push
m "${SEP}git[[:space:]]+push.*([[:space:]]-f([[:space:]]|\$)|--force)" \
  && deny "force push"

# .env files in ANY command (read or write). Templates such as .env.example are allowed.
ENV_TOKENS=$(grep -oE '(^|[[:space:]/=:<>])\.env[a-z0-9._-]*' <<< "$LC" | sed 's/^[^.]*//')
if [ -n "$ENV_TOKENS" ] \
   && printf '%s\n' "$ENV_TOKENS" | grep -qvE '^\.env\.(example|sample|template|dist)$'; then
  deny "command touches a .env file"
fi

# Other sensitive paths, and Claude Code's own guardrails
SENSITIVE='(secrets/|\.(pem|p12|pfx|key)([^a-z0-9_]|$)|id_(rsa|ed25519|ecdsa)|\.ssh/|\.aws/|\.gnupg/|\.netrc|\.npmrc|\.git/(config|hooks)|\.claude/(hooks|settings))'
m "$SENSITIVE" && deny "command touches a sensitive path or Claude Code's own guardrails"

# ---------- ASK ----------

# Docker runs outside any sandbox and can use the API keys passed to containers
# (e.g. indexing with paid OpenAI embeddings), so it always needs explicit approval.
m "${SEP}(docker|docker-compose|podman)${END}" \
  && ask "Docker runs outside the sandbox and may call paid APIs: confirm"

# Git operations that record, publish or discard work
m "${SEP}git[[:space:]]+(commit|push|rebase|reset[[:space:]]+--hard|restore|checkout[[:space:]]+--|stash[[:space:]]+(drop|clear))" \
  && ask "Git operation that records, publishes or discards work: confirm"

# Paths outside the project (the project's own absolute path is fine)
OUTSIDE="$LC"
if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
  PROJECT_LC=$(printf '%s' "$CLAUDE_PROJECT_DIR" | tr '[:upper:]' '[:lower:]')
  OUTSIDE=${LC//"$PROJECT_LC"/}
fi
grep -qE -- '\.\./|(^|[[:space:]=:])~|\$home|\$\{home\}|/users/' <<< "$OUTSIDE" \
  && ask "Command refers to a path outside the project: confirm"

exit 0
