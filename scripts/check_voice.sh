#!/usr/bin/env bash
# Tests Sarvam text-to-speech with your key and plays each result (macOS). Never prints the key.
# Run:  bash scripts/check_voice.sh
cd "$(dirname "$0")/.." || exit 1
set -a; . ./.env; set +a
[ -z "$SARVAM_API_KEY" ] && { echo "SARVAM_API_KEY is empty in .env"; exit 1; }
speak() {  # language code, text
  printf "%-6s " "$1"
  curl -s -m 40 -o /tmp/mm_tts.json -w "HTTP %{http_code} in %{time_total}s  " -X POST https://api.sarvam.ai/text-to-speech \
    -H "api-subscription-key: $SARVAM_API_KEY" -H "Content-Type: application/json" \
    -d "{\"text\":\"$2\",\"target_language_code\":\"$1\",\"speaker\":\"shubh\",\"model\":\"bulbul:v3\"}"
  python3 - "$1" << 'PY'
import base64, json, sys
try:
    d = json.load(open('/tmp/mm_tts.json')); wav = base64.b64decode("".join(d["audios"]))
    open(f"/tmp/mm_tts_{sys.argv[1]}.wav", "wb").write(wav); print(f"-> {len(wav)//1024} KB audio")
except Exception:
    print("-> no audio:", open('/tmp/mm_tts.json').read()[:200])
PY
  [ -f "/tmp/mm_tts_$1.wav" ] && afplay "/tmp/mm_tts_$1.wav"
}
speak en-IN "Sell today at the best mandi. Prices are lower tomorrow."
speak hi-IN "आज ही सबसे अच्छी मंडी में प्याज बेचिए।"
speak mr-IN "आज सर्वात चांगल्या बाजारात कांदा विका."
rm -f /tmp/mm_tts.json /tmp/mm_tts_*.wav
