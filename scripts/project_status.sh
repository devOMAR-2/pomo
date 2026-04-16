#!/usr/bin/env bash
# project_status.sh — move a ticket (by T-KEY) to a new Project Status.
#
# Usage:  scripts/project_status.sh T-003 "In Progress"
#
# Requires: gh CLI authenticated with `project` scope, and sync-report.json
# present (either at repo root, at 02-tasks/, or pointed at by $SYNC_REPORT).
#
# Works with Projects v2 owned by either a user or an organization: queries
# the user namespace first, falls back to the organization namespace. All
# command-substitution outputs are piped through `tr -d '\r'` to strip any
# carriage returns introduced by Windows / Git Bash pipes, which would
# otherwise cause GitHub to reject mutation IDs as invalid.

set -euo pipefail

KEY="${1:?usage: project_status.sh T-KEY STATUS}"
NEW_STATUS="${2:?usage: project_status.sh T-KEY STATUS}"

REPORT="${SYNC_REPORT:-sync-report.json}"
if [[ ! -f "$REPORT" ]]; then
  [[ -f "02-tasks/sync-report.json" ]] && REPORT="02-tasks/sync-report.json"
fi
[[ -f "$REPORT" ]] || { echo "sync-report.json not found"; exit 1; }

ISSUE_NUMBER=$(jq -r ".mapping[\"$KEY\"]" "$REPORT" | tr -d '\r')
OWNER=$(jq -r '.project.owner' "$REPORT" | tr -d '\r')
PROJECT_NUMBER=$(jq -r '.project.number' "$REPORT" | tr -d '\r')
PROJECT_ID=$(jq -r '.project.id' "$REPORT" | tr -d '\r')

if [[ -z "$ISSUE_NUMBER" || "$ISSUE_NUMBER" == "null" ]]; then
  echo "No issue number for $KEY in $REPORT"; exit 1
fi

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner | tr -d '\r')

# 1. Resolve issue node id.
ISSUE_NODE=$(gh api "repos/$REPO/issues/$ISSUE_NUMBER" -q .node_id | tr -d '\r')

# 2. Find the project item id for this issue within the project.
#    Try the user namespace first; fall back to organization.
ITEM_QUERY_USER='
  query($owner:String!, $number:Int!) {
    user(login:$owner) { projectV2(number:$number) { items(first:100) { nodes {
      id content { ... on Issue { number } }
    } } } }
  }'

ITEM_QUERY_ORG='
  query($owner:String!, $number:Int!) {
    organization(login:$owner) { projectV2(number:$number) { items(first:100) { nodes {
      id content { ... on Issue { number } }
    } } } }
  }'

ITEM_ID=$(gh api graphql -f query="$ITEM_QUERY_USER" \
  -f owner="$OWNER" -F number="$PROJECT_NUMBER" 2>/dev/null \
  | jq -r --arg n "$ISSUE_NUMBER" \
    '.data.user.projectV2.items.nodes
     | map(select(.content.number == ($n|tonumber))) | .[0].id // empty' \
  | tr -d '\r')

if [[ -z "$ITEM_ID" ]]; then
  ITEM_ID=$(gh api graphql -f query="$ITEM_QUERY_ORG" \
    -f owner="$OWNER" -F number="$PROJECT_NUMBER" 2>/dev/null \
    | jq -r --arg n "$ISSUE_NUMBER" \
      '.data.organization.projectV2.items.nodes
       | map(select(.content.number == ($n|tonumber))) | .[0].id // empty' \
    | tr -d '\r')
fi

if [[ -z "$ITEM_ID" || "$ITEM_ID" == "null" ]]; then
  echo "Issue #$ISSUE_NUMBER is not on project #$PROJECT_NUMBER"; exit 1
fi

# 3. Resolve Status field id + target option id (user-first, org-fallback).
FIELDS_QUERY_USER='
  query($owner:String!, $number:Int!) {
    user(login:$owner) { projectV2(number:$number) { fields(first:30) { nodes {
      ... on ProjectV2SingleSelectField { id name options { id name } }
    } } } }
  }'

FIELDS_QUERY_ORG='
  query($owner:String!, $number:Int!) {
    organization(login:$owner) { projectV2(number:$number) { fields(first:30) { nodes {
      ... on ProjectV2SingleSelectField { id name options { id name } }
    } } } }
  }'

FIELDS_JSON=$(gh api graphql -f query="$FIELDS_QUERY_USER" \
  -f owner="$OWNER" -F number="$PROJECT_NUMBER" 2>/dev/null \
  | jq '.data.user.projectV2.fields.nodes // empty')

if [[ -z "$FIELDS_JSON" || "$FIELDS_JSON" == "null" ]]; then
  FIELDS_JSON=$(gh api graphql -f query="$FIELDS_QUERY_ORG" \
    -f owner="$OWNER" -F number="$PROJECT_NUMBER" 2>/dev/null \
    | jq '.data.organization.projectV2.fields.nodes // empty')
fi

read -r STATUS_FIELD_ID STATUS_OPTION_ID < <(echo "$FIELDS_JSON" \
  | jq -r --arg s "$NEW_STATUS" '
      map(select(.name=="Status")) | .[0]
      | "\(.id) \([.options[] | select(.name==$s)] | .[0].id)"' \
  | tr -d '\r')

if [[ -z "$STATUS_OPTION_ID" || "$STATUS_OPTION_ID" == "null" ]]; then
  echo "No option '$NEW_STATUS' on Status field"; exit 1
fi

# 4. Update.
gh api graphql -f query='
  mutation($p:ID!, $i:ID!, $f:ID!, $o:String!) {
    updateProjectV2ItemFieldValue(input:{
      projectId:$p, itemId:$i, fieldId:$f,
      value:{ singleSelectOptionId:$o }
    }) { projectV2Item { id } }
  }
' -f p="$PROJECT_ID" -f i="$ITEM_ID" -f f="$STATUS_FIELD_ID" -f o="$STATUS_OPTION_ID" > /dev/null

echo "✓ $KEY (#$ISSUE_NUMBER) -> $NEW_STATUS"