// Mandi-Mausam front end: plain JavaScript, no build step.
const $ = (id) => document.getElementById(id);
const state = { lastAnswer: "", recorder: null, chunks: [] };

const PLACEHOLDERS = {
  en: "e.g. I have 20 quintals of onion near Lasalgaon. Should I sell today or wait, and where?",
  hi: "जैसे: लासलगाँव के पास मेरे पास 20 क्विंटल प्याज़ है। आज बेचूँ या रुकूँ, और किस मंडी में?",
  mr: "उदा. लासलगावजवळ माझ्याकडे 20 क्विंटल कांदा आहे. आज विकू की थांबू, आणि कोणत्या बाजारात?",
};
const EXAMPLE = {
  en: "I have 20 quintals of onion stored near Lasalgaon, Nashik. Should I sell today or wait, and at which mandi?",
  hi: "लासलगाँव, नासिक के पास मेरे पास 20 क्विंटल प्याज़ रखा है। आज बेचूँ या रुकूँ, और किस मंडी में?",
  mr: "लासलगाव, नाशिकजवळ माझ्याकडे 20 क्विंटल कांदा साठवलेला आहे. आज विकू की थांबू, आणि कोणत्या बाजारात?",
};
const REC_LABEL = { SELL_NOW: "SELL NOW", HOLD: "HOLD", NEED_INFO: "NEED MORE INFO", CANNOT_HELP: "CAN'T HELP WITH THIS" };
const STEP_LABEL = {
  find_place: "Found your village",
  get_weather_outlook: "Checked 7-day weather",
  compare_mandis: "Compared nearby mandis",
  grounding_check: "Checked every number against live data",
  llm: "AI model",
  limit: "Step limit",
  format: "Answer format",
};

const lang = () => $("language").value;
const num = (v) => (v === null || v === undefined ? "–" : Number(v).toLocaleString("en-IN"));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });

$("language").addEventListener("change", () => { $("question").placeholder = PLACEHOLDERS[lang()]; });
$("example").addEventListener("click", () => {
  $("question").value = EXAMPLE[lang()];
  $("qty").value = "20";
  $("rate").value = "";
  $("question").focus();
});
$("ask").addEventListener("click", ask);
$("listen").addEventListener("click", listen);
$("mic").addEventListener("click", toggleMic);

async function ask() {
  const question = $("question").value.trim();
  if (!question) { showError("Please type or say your question."); return; }
  const body = { question, language: lang() };
  const qty = parseFloat($("qty").value); if (qty > 0) body.quantity_quintals = qty;
  const rate = parseFloat($("rate").value); if (rate >= 0) body.transport_rate_per_km = rate;

  $("ask").disabled = true; $("error").hidden = true; $("result").hidden = true; $("working").hidden = false;
  try {
    const res = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail ? JSON.stringify(data.detail) : `Server error ${res.status}`);
    if (!data.ok) { showError(data.error || "Something went wrong.", data.trace); return; }
    render(data);
  } catch (e) {
    showError("Could not reach the server. Check your connection and try again.");
    console.error(e);
  } finally {
    $("ask").disabled = false; $("working").hidden = true;
  }
}

function showError(msg, trace) {
  $("error").hidden = false;
  $("error").innerHTML = `<strong>${esc(msg)}</strong>` + (trace && trace.length ? `<ol class="trace">${trace.map(traceItem).join("")}</ol>` : "");
}

function render(d) {
  $("result").hidden = false;
  const rec = $("rec"); rec.className = `badge ${d.recommendation}`; rec.textContent = REC_LABEL[d.recommendation] || d.recommendation;
  const g = $("grounded");
  g.className = d.grounded ? "pill" : "pill warn";
  g.textContent = d.grounded ? "✓ All numbers traced to live data" : `⚠ Unverified numbers: ${d.unsupported_numbers.join(", ")}`;
  $("answer").textContent = d.answer;
  state.lastAnswer = d.answer;
  $("reasons").innerHTML = (d.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("");
  const af = $("ask-farmer"); af.hidden = !d.ask_farmer; af.textContent = d.ask_farmer || "";
  $("elapsed").textContent = `Answered in ${d.elapsed_s}s · ${d.model}`;
  $("listen").disabled = !d.answer;
  $("listen-status").textContent = d.answer ? "" : "No answer text to read aloud.";

  renderMandis(d.mandis, d.best_mandi);
  renderWeather(d.weather, d.place);
  $("trace").innerHTML = (d.trace || []).map(traceItem).join("");
  renderSources(d);
  $("result").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderMandis(m, best) {
  const tbody = $("mandis").querySelector("tbody");
  if (!m || !m.ok) {
    tbody.innerHTML = `<tr><td colspan="7">${esc(m ? m.error : "No mandi data for this question.")}</td></tr>`;
    $("mandi-note").textContent = "";
    return;
  }
  $("mandi-note").textContent = `· ${m.commodity}, ${m.state} · ${m.distance_method === "road" ? "road distance" : "straight-line distance (routing unavailable)"}` +
    (m.transport_cost_known ? "" : " · add quantity and transport cost for net price");
  const cov = $("coverage"); cov.hidden = !m.coverage_note; cov.textContent = m.coverage_note || "";
  tbody.innerHTML = m.mandis.map((r) => `
    <tr class="${best && r.market === best ? "best" : ""}">
      <td>${r.rank}</td>
      <td>${esc(r.market)}<br><small class="hint">${esc(r.district || "")}${r.variety ? " · " + esc(r.variety) : ""}</small></td>
      <td>${fmtDate(r.arrival_date)} ${r.stale ? `<span class="stale">(${r.age_days}d old)</span>` : ""}</td>
      <td class="num">${num(r.modal_price)}</td>
      <td class="num">${r.distance_km != null ? num(r.distance_km) + " km" : "–"}</td>
      <td class="num">${num(r.transport_per_quintal_rs)}</td>
      <td class="num"><b>${num(r.net_price_per_quintal_rs)}</b></td>
    </tr>`).join("");
}

function renderWeather(w, place) {
  const box = $("weather");
  if (!w || !w.ok) { box.innerHTML = `<p>${esc(w ? w.error : "No weather data.")}</p>`; $("weather-note").textContent = ""; return; }
  $("weather-note").textContent = place && place.found ? `· ${place.name}, ${place.district || ""}` : "";
  box.innerHTML = w.days.map((d) => `
    <div class="day ${d.risk}">
      <b>${new Date(d.date + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric" })}</b>
      🌧 ${num(d.rain_mm)} mm<br>${num(d.rain_chance_pct)}% chance<br>💧 ${num(d.humidity_mean_pct)}%
      <div class="risk">${d.risk}</div>
    </div>`).join("");
}

function traceItem(t) {
  const label = STEP_LABEL[t.step] || t.step;
  const args = t.args ? Object.entries(t.args).map(([k, v]) => `${k}=${v}`).join(", ") : "";
  return `<li><span class="${t.ok ? "ok" : "fail"}">${t.ok ? "✓" : "✗"}</span> <b>${esc(label)}</b>: ${esc(t.detail || "")}
    ${args ? `<br><code>${esc(t.step)}(${esc(args)})</code>` : ""}${t.ms != null ? ` <span class="hint">${t.ms} ms</span>` : ""}</li>`;
}

function renderSources(d) {
  const srcs = [];
  if (d.place && d.place.source) srcs.push(d.place.source);
  if (d.weather && d.weather.source) srcs.push(d.weather.source);
  if (d.mandis && d.mandis.sources) srcs.push(...d.mandis.sources.filter(Boolean));
  const seen = new Set();
  $("sources").innerHTML = srcs.filter((s) => !seen.has(s.name) && seen.add(s.name)).map((s) => `
    <li>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>` : esc(s.name)}
    ${s.fetched_at ? `<span class="hint">· fetched ${new Date(s.fetched_at).toLocaleString("en-IN")}${s.from_cache ? " (cached)" : ""}${s.stale_fallback ? " · live call failed, showing last real data" : ""}</span>` : ""}</li>`).join("");
}

async function listen() {
  const status = $("listen-status");
  if (!state.lastAnswer) { status.textContent = "There is no answer to read aloud yet."; return; }
  $("listen").disabled = true; status.textContent = "Preparing audio…";
  try {
    const res = await fetch("/api/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: state.lastAnswer, language: lang() }) });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Voice is unavailable");
    const p = $("player"); p.src = `data:audio/wav;base64,${data.audio_base64}`;
    p.onended = () => { status.textContent = ""; };
    await p.play(); status.textContent = "Playing…";
  } catch (e) {
    status.textContent = `Could not play the audio: ${e.message}`;
  } finally {
    $("listen").disabled = false;
  }
}

async function toggleMic() {
  const btn = $("mic"), status = $("mic-status");
  if (state.recorder && state.recorder.state === "recording") { state.recorder.stop(); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder) { status.textContent = "Voice input isn't supported in this browser. Please type instead."; return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
    state.recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    state.chunks = [];
    state.recorder.ondataavailable = (e) => e.data.size && state.chunks.push(e.data);
    state.recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      btn.classList.remove("rec"); clearTimeout(state.timer);
      status.textContent = "Understanding your voice…";
      const blob = new Blob(state.chunks, { type: state.recorder.mimeType || "audio/webm" });
      const fd = new FormData(); fd.append("audio", blob, "speech.webm"); fd.append("language", lang());
      try {
        const res = await fetch("/api/transcribe", { method: "POST", body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Could not transcribe");
        $("question").value = data.transcript; status.textContent = "Got it. Asking now…";
        ask();
      } catch (e) { status.textContent = `Voice input failed: ${e.message}. Please type instead.`; }
    };
    state.recorder.start(); btn.classList.add("rec"); status.textContent = "Listening… tap again to stop (max 25 s).";
    state.timer = setTimeout(() => state.recorder.state === "recording" && state.recorder.stop(), 25000);
  } catch (e) {
    status.textContent = "Microphone permission denied. Please type instead.";
  }
}
