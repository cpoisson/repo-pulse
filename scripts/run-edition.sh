#!/usr/bin/env bash
# Unattended repo-pulse edition, e.g. from cron:
#   0 6 * * 1  cd /path/to/repo-pulse && AGENT=pi scripts/run-edition.sh configs/<name>.yaml >> logs/cron.log 2>&1
#
# Deterministic steps run here (0 tokens). An agent is called only to write the narrative from the digest; the script
# then re-validates, builds and layout-checks the deck, and fails loudly if anything is off.
#
#   AGENT       pi | codex | claude | none   (none = rule-based narrative, no agent; useful for dry runs)
#   AGENT_ARGS  extra flags for the agent CLI, e.g. AGENT_ARGS="--model anthropic/claude-sonnet-5-5" for pi
#   AS_OF       edition date (default: today)
set -euo pipefail

CONFIG=${1:?usage: run-edition.sh configs/<name>.yaml [as_of]}
AS_OF=${2:-${AS_OF:-$(date +%F)}}
AGENT=${AGENT:-pi}
AGENT_ARGS=${AGENT_ARGS:-}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

NAME=$(basename "$CONFIG" .yaml)
REPO=$(awk -F': ' '/^repo:/{print $2; exit}' "$CONFIG")
SLUG=${REPO/\//__}
DATA="data/$SLUG"
mkdir -p logs out "$DATA"
LOG="logs/$NAME-$AS_OF.log"
LOCK="/tmp/repo-pulse-$NAME.lock"
exec > >(tee -a "$LOG") 2>&1

# one run per repo at a time
if ! mkdir "$LOCK" 2>/dev/null; then echo "another run holds $LOCK; exiting"; exit 0; fi
trap 'rmdir "$LOCK"' EXIT

# configs and gold labels are gitignored, so git status cannot see agent edits: fingerprint them instead
protected() { find src configs "$DATA/gold.json" -type f ! -name '*.pyc' -print0 2>/dev/null | sort -z | xargs -0 shasum; }

rp() { uv run repo-pulse -c "$CONFIG" --as-of "$AS_OF" "$@"; }
echo "== $(date -Is) repo-pulse $REPO as-of $AS_OF (agent: $AGENT)"

if [[ ! -s "$DATA/gold.json" ]]; then
  echo "!! $REPO has no gold set: run the first edition interactively (skills/repo-pulse/SKILL.md steps 1-3)"; exit 2
fi

# 1. deterministic pipeline
rp collect
rp classify
rp analyze

# 2. agent writes the narrative (only judgment step)
NARR="$DATA/narrative-input-$AS_OF.json"
SUMMARY="out/$NAME-pulse-$AS_OF.summary.txt"
DIGEST="$DATA/digest-$AS_OF.txt"
PREV=$(ls "$DATA"/narrative-input-*.json 2>/dev/null | grep -v -- "-$AS_OF.json" | sort | tail -1 || true)
rp digest > "$DIGEST"

if [[ "$AGENT" != none ]]; then
  PROMPT=$(sed -e "s|{{CONFIG}}|$CONFIG|g" -e "s|{{AS_OF}}|$AS_OF|g" -e "s|{{REPO}}|$REPO|g" \
               -e "s|{{DIGEST_FILE}}|$DIGEST|g" -e "s|{{NARRATIVE_FILE}}|$NARR|g" -e "s|{{SUMMARY_FILE}}|$SUMMARY|g" \
               -e "s|{{PREVIOUS_NARRATIVE}}|${PREV:-none}|g" tasks/edition.md)
  guard_before=$(protected)
  case "$AGENT" in
    # pi: print mode, only the tools the task needs, no session file, skip AGENTS.md (dev docs, not needed here)
    pi)     pi -p --no-session -nc --tools read,write,edit,bash $AGENT_ARGS "$PROMPT" ;;
    codex)  codex exec -C "$ROOT" --sandbox workspace-write --skip-git-repo-check -o "logs/$NAME-$AS_OF.agent.txt" $AGENT_ARGS "$PROMPT" ;;
    claude) claude -p --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash(uv run repo-pulse:*)" $AGENT_ARGS "$PROMPT" ;;
    *)      echo "!! unknown AGENT=$AGENT"; exit 2 ;;
  esac
  guard_after=$(protected)
  if [[ "$guard_before" != "$guard_after" ]]; then
    echo "!! agent modified protected files (src/, configs/ or gold.json):"; diff <(echo "$guard_before") <(echo "$guard_after") || true; exit 3
  fi
  [[ -s "$NARR" ]] || { echo "!! agent did not write $NARR"; exit 4; }
fi

# 3. re-validate independently of what the agent reported, then build and check
out=$(rp narrate 2>&1); echo "$out"
if [[ "$AGENT" != none ]] && ! grep -q "dropped 0" <<<"$out"; then
  echo "!! narrative still has unsupported claims (see dropped lines above)"; exit 5
fi
rp build
uvx --with playwright python skills/repo-pulse/scripts/check_deck.py "out/$NAME-pulse-$AS_OF.html" --out "out/$NAME-$AS_OF-shots"

echo "== done: out/$NAME-pulse-$AS_OF.html"
[[ -s "$SUMMARY" ]] && cat "$SUMMARY" || true
