#!/bin/sh
# Register the two bundled classifiers in a fresh install.
#
# Everything here is a plain API call — the same calls the admin UI makes, and
# the same ones you would use to register a classifier living in another repo.
#
#   NEWS_URL=http://localhost:8000 ADMIN_EMAIL=admin@example.edu \
#   ADMIN_PASSWORD=admin ./scripts/register_classifiers.sh

set -e

NEWS_URL="${NEWS_URL:-http://localhost:8000}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.edu}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"
REGEX_URL="${REGEX_URL:-http://classifier-regex:8000}"
REGEX_SECRET="${REGEX_CLASSIFIER_SECRET:-dev-regex-secret}"
AI_URL="${AI_URL:-http://classifier-ai:8000}"
AI_SECRET="${AI_CLASSIFIER_SECRET:-dev-ai-secret}"
AI_MODEL="${OPENROUTER_MODEL:-anthropic/claude-haiku-4.5}"

echo "logging in as $ADMIN_EMAIL..."
TOKEN=$(curl -sS -X POST "$NEWS_URL/api/v1/auth/token" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
    | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

if [ -z "$TOKEN" ]; then
    echo "could not obtain a token; check the credentials and that main is up" >&2
    exit 1
fi

register() {
    echo "registering $1..."
    curl -sS -X POST "$NEWS_URL/api/v1/admin/classifiers" \
        -H "Authorization: Bearer $TOKEN" \
        -H 'Content-Type: application/json' \
        -d "$2" \
        -w '\n  -> HTTP %{http_code}\n'
}

# Keywords first: cheap, deterministic, and its high priority means a rule an
# editor wrote wins over the model's guess on the same facet.
register "regex" "$(cat <<JSON
{
  "slug": "regex",
  "name": "Regex / keyword classifier",
  "base_url": "$REGEX_URL",
  "secret": "$REGEX_SECRET",
  "facets": [],
  "priority": 200,
  "min_confidence": 0.6,
  "auto_apply": true,
  "timeout_s": 10
}
JSON
)"

register "openrouter" "$(cat <<JSON
{
  "slug": "openrouter",
  "name": "OpenRouter LLM classifier",
  "base_url": "$AI_URL",
  "secret": "$AI_SECRET",
  "facets": [],
  "priority": 100,
  "min_confidence": 0.6,
  "auto_apply": true,
  "timeout_s": 60,
  "config": {"model": "$AI_MODEL", "temperature": 0}
}
JSON
)"

echo "done. Check them with: curl -H \"Authorization: Bearer \$TOKEN\" $NEWS_URL/api/v1/admin/classifiers"
