#!/usr/bin/env bash
# Finds which Gemini route works with your key. Prints status codes and timings only,
# never the key itself. Run:  bash scripts/check_llm.sh
cd "$(dirname "$0")/.." || exit 1
set -a; . ./.env; set +a
[ -z "$GEMINI_API_KEY" ] && { echo "GEMINI_API_KEY is empty in .env"; exit 1; }
echo "key starts with: ${GEMINI_API_KEY:0:3}...  (${#GEMINI_API_KEY} characters)"
echo

try() {  # label, url, auth header, json body
  printf "%-44s " "$1"
  curl -s -m 40 -o /tmp/llm_check_out.txt -w "HTTP %{http_code} in %{time_total}s\n" \
    -X POST "$2" -H "Content-Type: application/json" -H "$3" -d "$4" || echo "(no response: network blocked or timed out)"
  head -c 220 /tmp/llm_check_out.txt | tr '\n' ' '; echo; echo
}

OAI='{"model":"MODEL","messages":[{"role":"user","content":"Reply with the single word OK"}]}'
NAT='{"contents":[{"parts":[{"text":"Reply with the single word OK"}]}]}'

for M in gemini-flash-latest gemini-2.5-flash; do
  try "OpenAI-style + Bearer   [$M]" \
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions" \
    "Authorization: Bearer $GEMINI_API_KEY" "${OAI/MODEL/$M}"
  try "Native + x-goog-api-key [$M]" \
    "https://generativelanguage.googleapis.com/v1beta/models/$M:generateContent" \
    "x-goog-api-key: $GEMINI_API_KEY" "$NAT"
done
rm -f /tmp/llm_check_out.txt
