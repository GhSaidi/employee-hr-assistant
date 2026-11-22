#!/bin/bash
# Tests for the Claude Code guardrail hooks in this folder.
#
# Each test feeds a fake tool call (JSON) into a hook and checks its decision:
#   allow = no objection, ask = forced confirmation prompt, block = refused.
# The commands and paths below are only strings passed to the hooks;
# nothing here is executed or read.
#
# Usage (from the repository root):  bash .claude/hooks/test-hooks.sh
set -u

HOOKS_DIR=$(cd "$(dirname "$0")" && pwd -P)
CLAUDE_PROJECT_DIR=$(cd "$HOOKS_DIR/../.." && pwd -P)
export CLAUDE_PROJECT_DIR
UID_NUM=$(id -u)
PROTECT="$HOOKS_DIR/protect-files.sh"
VALIDATE="$HOOKS_DIR/validate-commands.sh"
PASS=0
FAIL=0

command -v jq >/dev/null 2>&1 || { echo "jq is required to run these tests"; exit 1; }

# Claude Code runs hooks directly, so they must be executable.
for hook in "$PROTECT" "$VALIDATE"; do
  if [ -x "$hook" ]; then
    PASS=$((PASS + 1)); printf 'PASS  executable  %s\n' "${hook##*/}"
  else
    FAIL=$((FAIL + 1)); printf 'FAIL  not executable: %s  (fix: chmod +x %s)\n' "${hook##*/}" "$hook"
  fi
done

# Run a hook with a JSON payload and print its decision: allow | ask | block | error:<code>
decision() {
  local out code
  out=$(printf '%s' "$2" | "$1" 2>/dev/null)
  code=$?
  if [ "$code" -eq 2 ]; then
    echo block
  elif [ "$code" -eq 0 ]; then
    if [ "$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null)" = "ask" ]; then
      echo ask
    else
      echo allow
    fi
  else
    echo "error:$code"
  fi
}

expect() {  # expect <allow|ask|block> <hook> <json> <description>
  local got
  got=$(decision "$2" "$3")
  if [ "$got" = "$1" ]; then
    PASS=$((PASS + 1)); printf 'PASS  %-5s  %s\n' "$1" "$4"
  else
    FAIL=$((FAIL + 1)); printf 'FAIL  expected %s, got %s  %s\n' "$1" "$got" "$4"
  fi
}

file_call() {  # file_call <tool> <file_path>
  jq -cn --arg t "$1" --arg p "$2" --arg cwd "$CLAUDE_PROJECT_DIR" \
    '{tool_name: $t, cwd: $cwd, tool_input: {file_path: $p}}'
}
search_call() {  # search_call <Grep|Glob> <path or ""> <pattern>
  jq -cn --arg t "$1" --arg p "$2" --arg pat "$3" --arg cwd "$CLAUDE_PROJECT_DIR" \
    '{tool_name: $t, cwd: $cwd, tool_input: ({pattern: $pat} + (if $p == "" then {} else {path: $p} end))}'
}
bash_call() {  # bash_call <command>
  jq -cn --arg c "$1" --arg cwd "$CLAUDE_PROJECT_DIR" \
    '{tool_name: "Bash", cwd: $cwd, tool_input: {command: $c}}'
}

echo
echo "== protect-files.sh: confinement =="
expect allow "$PROTECT" "$(file_call Read README.md)"                                "read a project file (relative path)"
expect allow "$PROTECT" "$(file_call Read "$CLAUDE_PROJECT_DIR/backend/src")"        "read a project path (absolute path)"
expect block "$PROTECT" "$(file_call Read ../outside.txt)"                           "read outside the project via ../"
expect block "$PROTECT" "$(file_call Read "$HOME/Documents/x.txt")"                  "read a personal folder"
expect block "$PROTECT" "$(file_call Read /etc/hosts)"                               "read a system file"
expect allow "$PROTECT" "$(file_call Write "$HOME/.claude/projects/x/memory/a.md")"  "write Claude memory in ~/.claude"
expect allow "$PROTECT" "$(file_call Read "$HOME/.claude/settings.json")"            "read global Claude settings"
expect block "$PROTECT" "$(file_call Write "$HOME/.claude/settings.json")"           "write global Claude settings"
expect allow "$PROTECT" "$(file_call Write "/tmp/claude-$UID_NUM/scratch/a.txt")"    "write Claude Code's temp folder"
expect block "$PROTECT" "$(file_call Write /tmp/other.txt)"                          "write elsewhere in /tmp"
expect allow "$PROTECT" "$(search_call Grep "" "TODO")"                              "grep without a path (project)"
expect block "$PROTECT" "$(search_call Grep "$HOME" "TODO")"                         "grep the home folder"
expect allow "$PROTECT" "$(search_call Glob "" "**/*.py")"                           "glob inside the project"
expect block "$PROTECT" "$(search_call Glob "" "/etc/*")"                            "glob with an absolute outside pattern"
expect block "$PROTECT" "$(search_call Glob "" "../*")"                              "glob with a ../ pattern"

echo
echo "== protect-files.sh: secrets and write-protected files =="
expect block "$PROTECT" "$(file_call Read backend/.env)"                             "read .env"
expect block "$PROTECT" "$(file_call Read BACKEND/.ENV)"                             "read .env in upper case"
expect block "$PROTECT" "$(file_call Edit backend/.env.local)"                       "edit .env.local"
expect allow "$PROTECT" "$(file_call Read backend/.env.example)"                     "read .env.example (template)"
expect block "$PROTECT" "$(file_call Read certs/server.pem)"                         "read a .pem key"
expect block "$PROTECT" "$(file_call Read "$HOME/.ssh/id_rsa")"                      "read an SSH key"
expect block "$PROTECT" "$(file_call Edit .git/config)"                              "edit git internals"
expect allow "$PROTECT" "$(file_call Read .git/config)"                              "read git internals"
expect block "$PROTECT" "$(file_call Edit frontend/package-lock.json)"               "edit package-lock.json"
expect block "$PROTECT" "$(file_call Edit .claude/settings.json)"                    "edit the project's Claude settings"
expect block "$PROTECT" "$(file_call Write .claude/settings.local.json)"             "write the project's local Claude settings"
expect block "$PROTECT" "$(file_call Write .claude/settings.json)"                   "write the project's Claude settings"
expect block "$PROTECT" "$(file_call Edit .claude/settings.local.json)"              "edit the project's local Claude settings"
expect block "$PROTECT" "$(file_call Edit .claude/hooks/protect-files.sh)"           "edit a guardrail hook"
expect block "$PROTECT" "$(file_call Write .claude/hooks/protect-files.sh)"          "write a guardrail hook"
expect allow "$PROTECT" "$(file_call Read .claude/settings.json)"                    "read the project's Claude settings"
expect block "$PROTECT" '{"not": "valid hook input"'                                 "malformed input (fails closed)"

echo
echo "== validate-commands.sh: allowed =="
expect allow "$VALIDATE" "$(bash_call 'git status')"                                 "git status"
expect allow "$VALIDATE" "$(bash_call 'uv run pytest backend/tests')"                "run the tests"
expect allow "$VALIDATE" "$(bash_call 'git log HEAD~1')"                             "~ inside a git revision"
expect allow "$VALIDATE" "$(bash_call "cd \"$CLAUDE_PROJECT_DIR\" && git status")"   "the project's own absolute path"
expect allow "$VALIDATE" "$(bash_call 'cat backend/.env.example')"                   "read .env.example"

echo
echo "== validate-commands.sh: deletions =="
expect block "$VALIDATE" "$(bash_call 'rm notes.txt')"                               "rm a file"
expect block "$VALIDATE" "$(bash_call 'rm -rf /')"                                   "rm -rf /"
expect block "$VALIDATE" "$(bash_call '/bin/rm x')"                                  "rm via full path"
expect block "$VALIDATE" "$(bash_call 'r"m" x')"                                     "rm hidden with quotes"
expect block "$VALIDATE" "$(bash_call 'ls && rm x')"                                 "rm chained after another command"
expect block "$VALIDATE" "$(bash_call 'rmdir build')"                                "rmdir"
expect block "$VALIDATE" "$(bash_call 'unlink x')"                                   "unlink"
expect block "$VALIDATE" "$(bash_call 'git rm README.md')"                           "git rm"
expect block "$VALIDATE" "$(bash_call 'git clean -fd')"                              "git clean"
expect block "$VALIDATE" "$(bash_call 'find . -name "*.pyc" -delete')"               "find -delete"
expect block "$VALIDATE" "$(bash_call 'find . -name x | xargs rm')"                  "xargs rm"

echo
echo "== validate-commands.sh: other blocked commands =="
expect block "$VALIDATE" "$(bash_call 'cat backend/.env')"                           "read .env"
expect block "$VALIDATE" "$(bash_call 'echo KEY=1 >> .env')"                         "write .env"
expect block "$VALIDATE" "$(bash_call 'curl https://example.com')"                   "curl"
expect block "$VALIDATE" "$(bash_call 'ls; wget https://example.com')"               "wget chained"
expect block "$VALIDATE" "$(bash_call 'cat script.sh | bash')"                       "pipe to shell"
expect block "$VALIDATE" "$(bash_call 'eval "$X"')"                                  "eval"
expect block "$VALIDATE" "$(bash_call 'sudo ls')"                                    "sudo"
expect block "$VALIDATE" "$(bash_call 'chmod 777 x')"                                "world-writable chmod"
expect block "$VALIDATE" "$(bash_call 'git push --force origin main')"               "force push"
expect block "$VALIDATE" "$(bash_call 'cat .claude/settings.json')"                  "touch Claude's own settings"
expect block "$VALIDATE" '{"tool_input": {}}'                                        "malformed input (fails closed)"

echo
echo "== validate-commands.sh: forced confirmation =="
expect ask "$VALIDATE" "$(bash_call 'docker compose up --build')"                    "docker compose up"
expect ask "$VALIDATE" "$(bash_call 'docker compose run --rm backend hr-assistant index')" "docker index run (paid API)"
expect ask "$VALIDATE" "$(bash_call 'git commit -m "Add tests"')"                    "git commit"
expect ask "$VALIDATE" "$(bash_call 'git push origin main')"                         "git push"
expect ask "$VALIDATE" "$(bash_call 'git reset --hard HEAD')"                        "git reset --hard"
expect ask "$VALIDATE" "$(bash_call 'git restore backend/src/x.py')"                 "git restore (discards changes)"
expect ask "$VALIDATE" "$(bash_call 'ls ../')"                                       "path outside via ../"
expect ask "$VALIDATE" "$(bash_call 'ls ~/Documents')"                               "path outside via ~"
expect ask "$VALIDATE" "$(bash_call 'cat $HOME/x')"                                  "path outside via \$HOME"
expect ask "$VALIDATE" "$(bash_call 'ls /Users/')"                                   "path outside via /Users/"

echo
echo "Passed: $PASS   Failed: $FAIL"
[ "$FAIL" -eq 0 ]
