#!/usr/bin/env bash
# Tests Sarvam's chat models (OpenAI-compatible) with a tool call, using your Sarvam key.
# Prints status, timing and what the model did; never prints the key.
# Run:  bash scripts/check_sarvam_llm.sh
cd "$(dirname "$0")/.." || exit 1
set -a; . ./.env; set +a
[ -z "$SARVAM_API_KEY" ] && { echo "SARVAM_API_KEY is empty in .env"; exit 1; }
BODY='{"model":"MODEL","temperature":0.2,"messages":[{"role":"user","content":"What is the weather in Lasalgaon? Use the tool."}],"tools":[{"type":"function","function":{"name":"get_weather","description":"Get the 7-day weather for a place","parameters":{"type":"object","properties":{"place":{"type":"string"}},"required":["place"]}}}],"tool_choice":"auto"}'
for M in sarvam-30b sarvam-105b; do
  printf "%-36s " "Sarvam chat + tool call [$M]"
  curl -s -m 60 -o /tmp/sarvam_chk.txt -w "HTTP %{http_code} in %{time_total}s\n" \
    -X POST "https://api.sarvam.ai/v1/chat/completions" \
    -H "Authorization: Bearer $SARVAM_API_KEY" -H "Content-Type: application/json" \
    -d "${BODY/MODEL/$M}" || echo "(no response: network blocked or timed out)"
  python3 - << 'PY'
import json
try:
    d = json.load(open('/tmp/sarvam_chk.txt'))
    c = d['choices'][0]
    tc = [t['function']['name'] + ' ' + t['function']['arguments'] for t in (c['message'].get('tool_calls') or [])]
    print('  finish_reason:', c.get('finish_reason'), '| tool calls:', tc or 'none', '| text:', (c['message'].get('content') or '')[:80])
except Exception:
    print('  could not read response:', open('/tmp/sarvam_chk.txt').read()[:200])
PY
  echo
done
rm -f /tmp/sarvam_chk.txt
