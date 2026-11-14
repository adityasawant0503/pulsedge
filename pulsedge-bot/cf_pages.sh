#!/usr/bin/env bash
# Copies the website (the pulsedge/ folder) to Cloudflare Pages, free, at https://<project>.pages.dev.
# The GitHub Pages site keeps working as before; this is a second, shorter address for the Instagram bio,
# on a host whose free plan allows a paid product.
#
# Needs two repository secrets (Settings -> Secrets and variables -> Actions):
#   CLOUDFLARE_API_TOKEN   a Cloudflare API token with "Cloudflare Pages: Edit"
#   CLOUDFLARE_ACCOUNT_ID  the account ID shown in the Cloudflare dashboard
# Without them this script does nothing and succeeds. Optional repository variable CF_PAGES_PROJECT
# picks the project name (default "pulsedge"); if that address is already taken on pages.dev,
# Cloudflare adds a few letters to it and the address actually used is printed in the run summary.
set -euo pipefail

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  echo "::notice::Cloudflare copy skipped: add the CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID repository secrets to turn it on."
  exit 0
fi

project="${CF_PAGES_PROJECT:-pulsedge}"
msg="${COMMIT_MESSAGE:-site update}"; msg="${msg%%$'\n'*}"
wrangler=(npx --yes wrangler@4.156.0)
export WRANGLER_SEND_METRICS=false

# First run only: create the project, with master as the production branch.
if ! out=$("${wrangler[@]}" pages project create "$project" --production-branch=master 2>&1); then
  if ! grep -qi "already exists" <<<"$out"; then
    echo "$out"
    exit 1
  fi
fi

out=$("${wrangler[@]}" pages deploy pulsedge --project-name="$project" --branch=master \
  --commit-message="${msg}" --commit-dirty=true 2>&1) || {
  echo "$out"
  exit 1
}
echo "$out" | tail -5

# The deploy prints https://<deployment id>.<project address>.pages.dev; drop the id to get the address.
url=$(grep -oE 'https://[a-z0-9-]+\.[a-z0-9-]+\.pages\.dev' <<<"$out" | tail -1 | sed -E 's#https://[a-z0-9-]+\.#https://#')
if [ -n "$url" ]; then
  echo "Site address: $url"
  [ -n "${GITHUB_STEP_SUMMARY:-}" ] && echo "Cloudflare copy is live at **$url**" >>"$GITHUB_STEP_SUMMARY"
fi
