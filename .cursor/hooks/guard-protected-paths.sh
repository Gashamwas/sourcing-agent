#!/bin/bash
# Pre-edit guard for protected paths.
#
# Blocks edits to:
#   - config/brief-*-draft.json (draft briefs)
#   - output/** (immutable finalized run output)
#
# ...unless the user's current prompt explicitly names the file/pattern,
# signaling they truly intend to touch it.
#
# Fail-open on unexpected errors (so we don't wedge the agent on parsing bugs).

set -u

input=$(cat)

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // .tool // empty' 2>/dev/null)
file_path=$(printf '%s' "$input" | jq -r '
  .tool_input.file_path
  // .tool_input.path
  // .tool_input.target_file
  // empty
' 2>/dev/null)
user_prompt=$(printf '%s' "$input" | jq -r '
  .conversation.user_messages[-1].content
  // .user_prompt
  // .prompt
  // ""
' 2>/dev/null)

if [[ -z "$file_path" ]]; then
  echo '{ "permission": "allow" }'
  exit 0
fi

# Normalize: strip leading ./ and leading repo root if present so we match
# both absolute and relative paths.
normalized="$file_path"
normalized="${normalized#./}"
repo_root="/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/"
normalized="${normalized#$repo_root}"

is_draft_brief=false
is_output=false

if [[ "$normalized" =~ ^config/brief-.*-draft\.json$ ]]; then
  is_draft_brief=true
fi

if [[ "$normalized" =~ ^output/ ]]; then
  is_output=true
fi

if ! $is_draft_brief && ! $is_output; then
  echo '{ "permission": "allow" }'
  exit 0
fi

# Escape hatch: user explicitly named the path (or a clear fragment of it)
# in their most recent prompt.
basename_path=$(basename "$normalized")
if [[ -n "$user_prompt" ]]; then
  if printf '%s' "$user_prompt" | grep -qF "$normalized" \
     || printf '%s' "$user_prompt" | grep -qF "$basename_path"; then
    echo '{ "permission": "allow" }'
    exit 0
  fi
fi

if $is_draft_brief; then
  cat <<'JSON'
{
  "permission": "deny",
  "user_message": "Blocked: attempting to edit a draft brief (config/brief-*-draft.json). These files are scratch/in-flight product thinking and should not be modified unless you explicitly name the file in your request.",
  "agent_message": "This file is a draft brief. Per repo policy (AGENTS.md + .cursor/rules/briefs-and-output.mdc), do not edit draft briefs unless the user explicitly names the file. Stop and confirm with the user before proceeding."
}
JSON
  exit 0
fi

if $is_output; then
  cat <<'JSON'
{
  "permission": "deny",
  "user_message": "Blocked: attempting to edit output/ directly. This directory holds immutable finalized run output; rebuild artifacts through the owning code path instead of hand-editing.",
  "agent_message": "output/ is immutable finalized run output. Per repo policy (AGENTS.md + .cursor/rules/briefs-and-output.mdc), do not hand-edit files here. If the artifact is wrong, fix the upstream code path that wrote it and regenerate."
}
JSON
  exit 0
fi

echo '{ "permission": "allow" }'
exit 0
