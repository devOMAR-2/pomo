#!/usr/bin/env bash
# project_status.sh — move a ticket (by T-KEY) to a new Project Status.
#
# Usage:  scripts/project_status.sh T-003 "In Progress"
#
# Requires: gh CLI authenticated, and PROJECT_OWNER + PROJECT_NUMBER either
# exported or present in sync-report.json.

set -euo pipefail

KEY="${1:?usage: project_status.sh T-KEY STATUS}"
NEW_STATUS="${2:?usage: project_status.sh T-KEY STATUS}"

REPORT="${SYNC_REPORT:-sync-report.json}"
if [[ ! -f "$REPORT" ]]; then
  # fallback location from the pipeline layout
  [[ -f "02-tasks/sync-report.json" ]] && REPORT="02-tasks/sync-report.json"
fi
[[ -f "$REPORT" ]] || { echo "sync-report.json not found"; exit 1; }

ISSUE_NUMBER=$(jq -r ".mapping[\"$KEY\"]" "$REPORT")
OWNER=$(jq -r '.project.owner' "$REPORT")
PROJECT_NUMBER=$(jq -r '.project.number' "$REPORT")
PROJECT_ID=$(jq -r '.project.id' "$REPORT")

if [[ -z "$ISSUE_NUMBER" || "$ISSUE_NUMBER" == "null" ]]; then
  echo "No issue number for $KEY in $REPORT"; exit 1
fi

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)

# 1. Resolve issue node id.
ISSUE_NODE=$(gh api "repos/$REPO/issues/$ISSUE_NUMBER" -q .node_id)

# 2. Find the project item id for this issue within the project.
ITEM_ID=$(gh api graphql -f query='
  query($owner:String!, $number:Int!) {
    user(login:$owner) { projectV2(number:$number) { items(first:100) { nodes {
      id content { ... on Issue { number } }
    } } } }
    organization(login:$owner) { projectV2(number:$number) { items(first:100) { nodes {
      id content { ... on Issue { number } }
    } } } }
  }
' -f owner="$OWNER" -F number="$PROJECT_NUMBER" \
 | jq -r --arg n "$ISSUE_NUMBER" \
   '[.data.user.projectV2.items.nodes, .data.organization.projectV2.items.nodes]
    | add | map(select(.content.number == ($n|tonumber))) | .[0].id')

if [[ -z "$ITEM_ID" || "$ITEM_ID" == "null" ]]; then
  echo "Issue #$ISSUE_NUMBER is not on project #$PROJECT_NUMBER"; exit 1
fi

# 3. Resolve Status field id + target option id.
read -r STATUS_FIELD_ID STATUS_OPTION_ID < <(gh api graphql -f query='
  query($owner:String!, $number:Int!) {
    user(login:$owner) { projectV2(number:$number) { fields(first:30) { nodes {
      ... on ProjectV2SingleSelectField { id name options { id name } }
    } } } }
    organization(login:$owner) { projectV2(number:$number) { fields(first:30) { nodes {
      ... on ProjectV2SingleSelectField { id name options { id name } }
    } } } }
  }
' -f owner="$OWNER" -F number="$PROJECT_NUMBER" \
 | jq -r --arg s "$NEW_STATUS" '
    [.data.user.projectV2.fields.nodes, .data.organization.projectV2.fields.nodes]
    | add | map(select(.name=="Status")) | .[0]
    | "\(.id) \([.options[] | select(.name==$s)] | .[0].id)"')

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
