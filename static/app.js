// Mandi-Mausam front end: plain JavaScript, no build step.
// Sections: language strings -> helpers -> asking (streaming) -> rendering -> voice.

const $ = (id) => document.getElementById(id);
const state = { lastAnswer: "", recorder: null, chunks: [], timer: null, fromVoice: false };

// ------------------------------------------------------------------ language strings (English, हिंदी, मराठी)
const T = {
  en: {
    heroTitle: "Sell today, or hold?", skip: "Skip to the question",
    tag: "Tell me your crop, your village and how many quintals you have. I check today's mandi prices and this week's weather, then give you one clear answer with every number sourced.",
    keep: "You keep about", perQ: "per quintal, after transport", forQ: (total, qty) => `₹${total} for your ${qty} quintals`,
    priceLabel: "Best mandi price", perQPlain: "per quintal, before transport", addRate: "Add your transport cost to see what you keep.",
    mediaCredit: "Illustrative footage made with Kling AI",
    skyWhere: (p) => `${p} right now`, skyVals: (t, h, c) => `${t}°C, humidity ${h}%, clouds ${c}%`,
    skyRain: (mm) => `, rain ${mm} mm`, skyDry: ", no rain",
    skyOver: "Above the 70% onion storage line", skyUnder: "Below the 70% onion storage line",
    skySrc: (time) => `Live from Open-Meteo, ${time}`, skyOff: "Live weather is unavailable right now",
    langLabel: "Language", askTitle: "Ask your question",
    placeholder: "e.g. I have 20 quintals of onion near Lasalgaon. Should I sell today or wait, and where?",
    exampleQ: "I have 20 quintals of onion stored near Lasalgaon, Nashik. Should I sell today or wait, and at which mandi?",
    micAria: "Speak your question", micLabel: "Speak",
    qtyLabel: "Quantity", qtyUnit: "(quintals)", rateLabel: "Transport cost", rateUnit: "(₹ per km, include the return trip if charged)",
    getAnswer: "Get my answer", example: "Try the Lasalgaon example", autoRead: "Read the answer aloud",
    working: "Checking live data…", listen: "Listen",
    mandisTitle: "Nearby mandis", weatherTitle: "Next 7 days at your village",
    weatherHint: "Onions store best below 70% humidity. A rainy day is 2.5 mm of rain or more (IMD definition).",
    thMandi: "Mandi", thReported: "Reported", thPrice: "Price ₹/qtl", thDistance: "Distance", thTransport: "Transport ₹/qtl", thNet: "You keep ₹/qtl",
    howTitle: "How I decided", sourcesTitle: "Sources",
    footer: "Prototype for the Forge buildathon. Advice is informational; prices come from official Agmarknet reports via data.gov.in and can change during the day.",
    rec: { SELL_NOW: "Sell now", HOLD: "Hold", NEED_INFO: "I need a little more information", CANNOT_HELP: "I can't help with this" },
    headSell: (m) => `Sell at ${m}`, headHold: "Hold for now",
    money: (net, total, qty) => `You keep about ₹${net} per quintal` + (total ? ` · ₹${total} for ${qty} quintals` : ""),
    moneyNoNet: (price) => `Price ₹${price} per quintal. Add your transport cost to see what you keep.`,
    chipDate: (d) => `Reported ${d}`, chipKm: (k) => `${k} km by road`, chipRisk: (r) => `Storage risk: ${r}`,
    risk: { high: "high", medium: "medium", low: "low" }, riskCaps: { high: "HIGH", medium: "MEDIUM", low: "LOW" },
    grounded: "✓ All numbers traced to live data", ungrounded: (n) => `⚠ Unverified numbers: ${n}`,
    answeredIn: (s, m) => `Answered in ${s} s by ${m}`,
    roadDist: "road distance", lineDist: "straight-line distance (routing unavailable)", addCost: "add quantity and transport cost for the amount you keep",
    stale: (d) => `${d}d old`, noMandi: "No mandi data for this question.", noWeather: "No weather data.",
    rainChance: (p) => `${p}% chance`,
    stepNames: { find_place: "Found your village", get_weather_outlook: "Checked the 7-day weather", compare_mandis: "Compared nearby mandis",
                 grounding_check: "Checked every number against live data", llm_call: "AI step", format: "Answer format", precheck: "Checked the question", limit: "Step limit", llm: "AI model" },
    needQuestion: "Please type or say your question.",
    listenPrep: "Preparing audio…", listenPlay: "Playing…", listenNone: "There is no answer to read aloud yet.",
    listenFail: (m) => `Could not play the audio: ${m}`, noAnswerText: "No answer text to read aloud.",
    fetched: "fetched", cached: "(cached)", staleFallback: "live call failed, showing last real data",
    micUnsupported: "Voice input isn't supported in this browser. Please type instead.", micListening: "Listening… tap again to stop (max 25 s).",
    micUnderstanding: "Understanding your voice…", micGot: "Got it. Asking now…", micFail: (m) => `Voice input failed: ${m}. Please type instead.`,
    micDenied: "Microphone permission denied. Please type instead.", serverDown: "Could not reach the server. Check your connection and try again.",
  },
  hi: {
    heroTitle: "आज बेचें, या रुकें?", skip: "सवाल पर जाएँ",
    tag: "अपनी फसल, गाँव और कितने क्विंटल हैं, बताइए। मैं आज के मंडी भाव और इस हफ़्ते का मौसम देखकर एक साफ़ जवाब दूँगा, हर आँकड़े के स्रोत के साथ।",
    keep: "आपके हाथ में लगभग", perQ: "प्रति क्विंटल, ढुलाई के बाद", forQ: (total, qty) => `आपके ${qty} क्विंटल के ₹${total}`,
    priceLabel: "सबसे अच्छा मंडी भाव", perQPlain: "प्रति क्विंटल, ढुलाई से पहले", addRate: "हाथ में कितना आएगा, यह देखने के लिए ढुलाई खर्च भरें।",
    mediaCredit: "Kling AI से बना चित्रात्मक वीडियो",
    skyWhere: (p) => `${p === "Lasalgaon" ? "लासलगाँव" : p} में अभी`, skyVals: (t, h, c) => `${t}°C, नमी ${h}%, बादल ${c}%`,
    skyRain: (mm) => `, बारिश ${mm} मिमी`, skyDry: ", बारिश नहीं",
    skyOver: "प्याज़ भंडारण की 70% सीमा से ऊपर", skyUnder: "प्याज़ भंडारण की 70% सीमा से नीचे",
    skySrc: (time) => `Open-Meteo से लाइव, ${time}`, skyOff: "लाइव मौसम अभी उपलब्ध नहीं है",
    langLabel: "भाषा", askTitle: "अपना सवाल पूछें",
    placeholder: "जैसे: लासलगाँव के पास मेरे पास 20 क्विंटल प्याज़ है। आज बेचूँ या रुकूँ, और किस मंडी में?",
    exampleQ: "लासलगाँव, नासिक के पास मेरे पास 20 क्विंटल प्याज़ रखा है। आज बेचूँ या रुकूँ, और किस मंडी में?",
    micAria: "बोलकर सवाल पूछें", micLabel: "बोलें",
    qtyLabel: "मात्रा", qtyUnit: "(क्विंटल)", rateLabel: "ढुलाई खर्च", rateUnit: "(₹ प्रति किमी, लौटने का किराया लगे तो जोड़ें)",
    getAnswer: "मेरा जवाब दिखाइए", example: "लासलगाँव का उदाहरण आज़माएँ", autoRead: "जवाब बोलकर सुनाएँ",
    working: "लाइव डेटा जाँच रहे हैं…", listen: "सुनें",
    mandisTitle: "नज़दीकी मंडियाँ", weatherTitle: "आपके गाँव में अगले 7 दिन",
    weatherHint: "प्याज़ 70% से कम नमी में सबसे अच्छा रखता है। बारिश का दिन यानी 2.5 मिमी या उससे ज़्यादा बारिश (IMD परिभाषा)।",
    thMandi: "मंडी", thReported: "रिपोर्ट", thPrice: "भाव ₹/क्विं.", thDistance: "दूरी", thTransport: "ढुलाई ₹/क्विं.", thNet: "हाथ में ₹/क्विं.",
    howTitle: "मैंने कैसे तय किया", sourcesTitle: "स्रोत",
    footer: "फ़ोर्ज बिल्डथॉन के लिए प्रोटोटाइप। सलाह केवल जानकारी के लिए है; भाव data.gov.in के ज़रिए आधिकारिक एगमार्कनेट रिपोर्ट से आते हैं और दिन में बदल सकते हैं।",
    rec: { SELL_NOW: "अभी बेचें", HOLD: "रुकें", NEED_INFO: "थोड़ी और जानकारी चाहिए", CANNOT_HELP: "इसमें मदद नहीं कर सकता" },
    headSell: (m) => `${m} में बेचें`, headHold: "अभी रुकें",
    money: (net, total, qty) => `आपको लगभग ₹${net} प्रति क्विंटल मिलेगा` + (total ? ` · ${qty} क्विंटल के ₹${total}` : ""),
    moneyNoNet: (price) => `भाव ₹${price} प्रति क्विंटल। हाथ में कितना आएगा यह देखने के लिए ढुलाई खर्च भरें।`,
    chipDate: (d) => `रिपोर्ट ${d}`, chipKm: (k) => `सड़क से ${k} किमी`, chipRisk: (r) => `भंडारण का जोखिम: ${r}`,
    risk: { high: "ज़्यादा", medium: "मध्यम", low: "कम" }, riskCaps: { high: "ज़्यादा", medium: "मध्यम", low: "कम" },
    grounded: "✓ हर आँकड़ा लाइव डेटा से मिलाया गया", ungrounded: (n) => `⚠ जाँचे नहीं गए आँकड़े: ${n}`,
    answeredIn: (s, m) => `${m} ने ${s} सेकंड में जवाब दिया`,
    roadDist: "सड़क की दूरी", lineDist: "सीधी दूरी (रूट उपलब्ध नहीं)", addCost: "हाथ में आने वाली रकम देखने के लिए मात्रा और ढुलाई खर्च भरें",
    stale: (d) => `${d} दिन पुराना`, noMandi: "इस सवाल के लिए मंडी का डेटा नहीं मिला।", noWeather: "मौसम का डेटा नहीं मिला।",
    rainChance: (p) => `${p}% संभावना`,
    stepNames: { find_place: "आपका गाँव मिला", get_weather_outlook: "7 दिन का मौसम देखा", compare_mandis: "नज़दीकी मंडियों की तुलना की",
                 grounding_check: "हर आँकड़ा लाइव डेटा से मिलाया", llm_call: "AI चरण", format: "जवाब का रूप", precheck: "सवाल जाँचा", limit: "चरण सीमा", llm: "AI मॉडल" },
    needQuestion: "कृपया अपना सवाल लिखिए या बोलिए।",
    listenPrep: "आवाज़ तैयार हो रही है…", listenPlay: "बज रहा है…", listenNone: "अभी सुनाने के लिए कोई जवाब नहीं है।",
    listenFail: (m) => `आवाज़ नहीं बज सकी: ${m}`, noAnswerText: "सुनाने के लिए जवाब का टेक्स्ट नहीं है।",
    fetched: "लिया गया", cached: "(कैश)", staleFallback: "लाइव कॉल विफल, आख़िरी असली डेटा दिखाया गया",
    micUnsupported: "इस ब्राउज़र में बोलकर पूछना उपलब्ध नहीं है। कृपया लिखिए।", micListening: "सुन रहे हैं… रोकने के लिए फिर दबाएँ (अधिकतम 25 सेकंड)।",
    micUnderstanding: "आपकी आवाज़ समझ रहे हैं…", micGot: "समझ गया। जवाब ढूँढ रहे हैं…", micFail: (m) => `आवाज़ से पूछना विफल: ${m}। कृपया लिखिए।`,
    micDenied: "माइक्रोफ़ोन की अनुमति नहीं मिली। कृपया लिखिए।", serverDown: "सर्वर तक नहीं पहुँच सके। कनेक्शन जाँचकर फिर कोशिश करें।",
  },
  mr: {
    heroTitle: "आज विकायचे, की थांबायचे?", skip: "प्रश्नाकडे जा",
    tag: "तुमचे पीक, गाव आणि किती क्विंटल आहे ते सांगा. मी आजचे बाजारभाव आणि या आठवड्याचे हवामान पाहून एक स्पष्ट उत्तर देईन, प्रत्येक आकड्याच्या स्रोतासह.",
    keep: "तुमच्या हातात सुमारे", perQ: "प्रति क्विंटल, वाहतुकीनंतर", forQ: (total, qty) => `तुमच्या ${qty} क्विंटलचे ₹${total}`,
    priceLabel: "सर्वोत्तम बाजारभाव", perQPlain: "प्रति क्विंटल, वाहतुकीपूर्वी", addRate: "हातात किती येईल ते पाहण्यासाठी वाहतूक खर्च भरा.",
    mediaCredit: "Kling AI ने बनवलेला चित्रात्मक व्हिडिओ",
    skyWhere: (p) => `${p === "Lasalgaon" ? "लासलगाव" : p} येथे आत्ता`, skyVals: (t, h, c) => `${t}°C, आर्द्रता ${h}%, ढग ${c}%`,
    skyRain: (mm) => `, पाऊस ${mm} मिमी`, skyDry: ", पाऊस नाही",
    skyOver: "कांदा साठवणुकीच्या 70% मर्यादेच्या वर", skyUnder: "कांदा साठवणुकीच्या 70% मर्यादेच्या खाली",
    skySrc: (time) => `Open-Meteo वरून थेट, ${time}`, skyOff: "थेट हवामान सध्या उपलब्ध नाही",
    langLabel: "भाषा", askTitle: "तुमचा प्रश्न विचारा",
    placeholder: "उदा. लासलगावजवळ माझ्याकडे 20 क्विंटल कांदा आहे. आज विकू की थांबू, आणि कोणत्या बाजारात?",
    exampleQ: "लासलगाव, नाशिकजवळ माझ्याकडे 20 क्विंटल कांदा साठवलेला आहे. आज विकू की थांबू, आणि कोणत्या बाजारात?",
    micAria: "बोलून प्रश्न विचारा", micLabel: "बोला",
    qtyLabel: "प्रमाण", qtyUnit: "(क्विंटल)", rateLabel: "वाहतूक खर्च", rateUnit: "(₹ प्रति किमी, परतीचे भाडे लागत असल्यास धरा)",
    getAnswer: "माझे उत्तर द्या", example: "लासलगावचे उदाहरण पाहा", autoRead: "उत्तर मोठ्याने वाचा",
    working: "थेट डेटा तपासत आहोत…", listen: "ऐका",
    mandisTitle: "जवळचे बाजार", weatherTitle: "तुमच्या गावात पुढील 7 दिवस",
    weatherHint: "कांदा 70% पेक्षा कमी आर्द्रतेत उत्तम टिकतो. पावसाचा दिवस म्हणजे 2.5 मिमी किंवा जास्त पाऊस (IMD व्याख्या).",
    thMandi: "बाजार", thReported: "नोंद", thPrice: "दर ₹/क्विं.", thDistance: "अंतर", thTransport: "वाहतूक ₹/क्विं.", thNet: "हातात ₹/क्विं.",
    howTitle: "मी कसे ठरवले", sourcesTitle: "स्रोत",
    footer: "फोर्ज बिल्डथॉनसाठी प्रोटोटाइप. सल्ला फक्त माहितीसाठी आहे; दर data.gov.in मार्फत अधिकृत अ‍ॅगमार्कनेट अहवालातून येतात आणि दिवसभरात बदलू शकतात.",
    rec: { SELL_NOW: "आत्ताच विका", HOLD: "थांबा", NEED_INFO: "थोडी अधिक माहिती हवी", CANNOT_HELP: "यात मदत करू शकत नाही" },
    headSell: (m) => `${m} येथे विका`, headHold: "सध्या थांबा",
    money: (net, total, qty) => `तुम्हाला सुमारे ₹${net} प्रति क्विंटल मिळतील` + (total ? ` · ${qty} क्विंटलचे ₹${total}` : ""),
    moneyNoNet: (price) => `दर ₹${price} प्रति क्विंटल. हातात किती येईल ते पाहण्यासाठी वाहतूक खर्च भरा.`,
    chipDate: (d) => `नोंद ${d}`, chipKm: (k) => `रस्त्याने ${k} किमी`, chipRisk: (r) => `साठवणीचा धोका: ${r}`,
    risk: { high: "जास्त", medium: "मध्यम", low: "कमी" }, riskCaps: { high: "जास्त", medium: "मध्यम", low: "कमी" },
    grounded: "✓ प्रत्येक आकडा थेट डेटाशी जुळवला", ungrounded: (n) => `⚠ न तपासलेले आकडे: ${n}`,
    answeredIn: (s, m) => `${m} ने ${s} सेकंदांत उत्तर दिले`,
    roadDist: "रस्त्याचे अंतर", lineDist: "सरळ अंतर (मार्ग उपलब्ध नाही)", addCost: "हातात येणारी रक्कम पाहण्यासाठी प्रमाण आणि वाहतूक खर्च भरा",
    stale: (d) => `${d} दिवस जुने`, noMandi: "या प्रश्नासाठी बाजाराचा डेटा मिळाला नाही.", noWeather: "हवामानाचा डेटा मिळाला नाही.",
    rainChance: (p) => `${p}% शक्यता`,
    stepNames: { find_place: "तुमचे गाव सापडले", get_weather_outlook: "7 दिवसांचे हवामान पाहिले", compare_mandis: "जवळच्या बाजारांची तुलना केली",
                 grounding_check: "प्रत्येक आकडा थेट डेटाशी जुळवला", llm_call: "AI पायरी", format: "उत्तराचे स्वरूप", precheck: "प्रश्न तपासला", limit: "पायरी मर्यादा", llm: "AI मॉडेल" },
    needQuestion: "कृपया तुमचा प्रश्न लिहा किंवा बोला.",
    listenPrep: "आवाज तयार होत आहे…", listenPlay: "वाजत आहे…", listenNone: "वाचून दाखवण्यासाठी अजून उत्तर नाही.",
    listenFail: (m) => `आवाज वाजू शकला नाही: ${m}`, noAnswerText: "वाचून दाखवण्यासाठी उत्तराचा मजकूर नाही.",
    fetched: "घेतले", cached: "(कॅश)", staleFallback: "थेट कॉल अयशस्वी, शेवटचा खरा डेटा दाखवला",
    micUnsupported: "या ब्राउझरमध्ये बोलून विचारणे उपलब्ध नाही. कृपया लिहा.", micListening: "ऐकत आहे… थांबवण्यासाठी पुन्हा दाबा (कमाल 25 सेकंद).",
    micUnderstanding: "तुमचा आवाज समजून घेत आहे…", micGot: "समजले. उत्तर शोधत आहे…", micFail: (m) => `आवाजाने विचारणे अयशस्वी: ${m}. कृपया लिहा.`,
    micDenied: "मायक्रोफोनची परवानगी मिळाली नाही. कृपया लिहा.", serverDown: "सर्व्हरशी संपर्क होऊ शकला नाही. कनेक्शन तपासून पुन्हा प्रयत्न करा.",
  },
};

const lang = () => $("language").value;
const t = () => T[lang()] || T.en;

// ------------------------------------------------------------------ helpers
const num = (v) => (v === null || v === undefined ? "–" : Number(v).toLocaleString("en-IN"));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const trim = (s) => String(s ?? "").trim();

function applyLang() {
  const L = t();
  document.documentElement.lang = lang();
  document.querySelectorAll("[data-i18n]").forEach((el) => { if (typeof L[el.dataset.i18n] === "string") el.textContent = L[el.dataset.i18n]; });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", L[el.dataset.i18nAria]); });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.setAttribute("title", L[el.dataset.i18nTitle]); });
  $("question").placeholder = L.placeholder;
  document.querySelectorAll(".langs button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang())));
  try { localStorage.setItem("mm-lang", lang()); } catch (e) { /* storage may be unavailable */ }
  if (state.last) render(state.last, { keepSpeech: true });
  renderSkyReadout();
}

$("language").addEventListener("change", applyLang);
document.querySelectorAll(".langs button").forEach((b) => b.addEventListener("click", () => {
  $("language").value = b.dataset.lang; applyLang();
}));
$("example").addEventListener("click", () => {
  $("question").value = t().exampleQ; $("qty").value = "20"; $("rate").value = ""; $("question").focus();
});
$("ask").addEventListener("click", () => ask());
$("listen").addEventListener("click", listen);
$("mic").addEventListener("click", toggleMic);

// ------------------------------------------------------------------ asking: streamed, with a plain fallback
async function ask() {
  const question = $("question").value.trim();
  if (!question) { showError(t().needQuestion); return; }
  const body = { question, language: lang() };
  const qty = parseFloat($("qty").value); if (qty > 0) body.quantity_quintals = qty;
  const rate = parseFloat($("rate").value); if (rate >= 0) body.transport_rate_per_km = rate;

  $("ask").disabled = true; $("error").hidden = true; $("result").hidden = true;
  $("working").hidden = false; $("working").classList.remove("done"); $("live").innerHTML = "";
  state.last = null;
  try {
    let result = null, sawStep = false;
    try {
      result = await streamAnswer(body, () => { sawStep = true; });
    } catch (e) {
      if (sawStep) throw e;                       // a half-finished stream: surface the problem
      result = await plainAnswer(body);           // streaming unavailable (proxy, old browser): ask normally
    }
    if (!result.ok) { showError(result.error || "Something went wrong.", result.trace); return; }
    state.last = result;
    render(result);
    if ($("auto-read").checked && result.answer) listen();
  } catch (e) {
    showError(t().serverDown);
    console.error(e);
  } finally {
    $("ask").disabled = false; $("working").classList.add("done"); $("working").hidden = true;
  }
}

async function plainAnswer(body) {
  const res = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ? JSON.stringify(data.detail) : `Server error ${res.status}`);
  return data;
}

async function streamAnswer(body, onFirstStep) {
  const res = await fetch("/api/ask_stream", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok || !res.body) throw new Error("stream unavailable");
  const reader = res.body.getReader(), dec = new TextDecoder();
  let buf = "", result = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line) continue;
      const ev = JSON.parse(line);
      if (ev.type === "step") { onFirstStep(); addLiveStep(ev.step); }
      else if (ev.type === "result") result = ev.result;
      else if (ev.type === "error") throw new Error(ev.error);
    }
  }
  if (!result) throw new Error("no result");
  return result;
}

// One line per real step, added the moment the server finishes it.
function addLiveStep(s) {
  const L = t(), ai = s.step === "llm_call";
  const li = document.createElement("li");
  if (ai) li.className = "ai";
  li.innerHTML = `<span class="tick ${s.ok ? "" : "fail"}">${s.ok ? "✓" : "✗"}</span>
    <span><span class="step-name">${esc(L.stepNames[s.step] || s.step)}</span><span class="step-detail">${esc(s.detail || "")}</span></span>
    <span class="ms">${s.ms != null ? (s.ms >= 1000 ? (s.ms / 1000).toFixed(1) + " s" : s.ms + " ms") : ""}</span>`;
  $("live").appendChild(li);
  li.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function showError(msg, trace) {
  $("error").hidden = false;
  $("error").innerHTML = `<strong>${esc(msg)}</strong>` + (trace && trace.length ? `<ol class="trace">${trace.map(traceItem).join("")}</ol>` : "");
}

// ------------------------------------------------------------------ rendering
function render(d, opts = {}) {
  const L = t();
  $("result").hidden = false;

  const best = (d.mandis && d.mandis.ok)
    ? (d.mandis.mandis.find((r) => trim(r.market) === trim(d.best_mandi)) || (["SELL_NOW", "HOLD"].includes(d.recommendation) ? d.mandis.mandis[0] : null))
    : null;

  $("verdict").className = `card verdict ${d.recommendation}`;
  const rec = $("rec"); rec.className = `badge ${d.recommendation}`; rec.textContent = L.rec[d.recommendation] || d.recommendation;
  const g = $("grounded"), hasData = d.recommendation !== "NEED_INFO" && !!(d.mandis || d.weather);
  g.hidden = !hasData && d.grounded;          // nothing to verify when we only asked a question back
  g.className = d.grounded ? "pill" : "pill warn";
  g.textContent = d.grounded ? L.grounded : L.ungrounded((d.unsupported_numbers || []).join(", "));

  // headline: the decision in one line
  let head = L.rec[d.recommendation] || "";
  if (d.recommendation === "SELL_NOW" && best) head = L.headSell(trim(best.market));
  else if (d.recommendation === "HOLD") head = L.headHold;
  $("headline").textContent = head;

  // money line: figures come straight from the data, not from the model's text
  const money = $("money");
  if (best && best.net_price_per_quintal_rs != null) {
    const q = d.mandis.quantity_quintals;
    money.innerHTML = `<span class="label">${esc(L.keep)}</span>
      <span class="big" data-count="${best.net_price_per_quintal_rs}">₹${num(best.net_price_per_quintal_rs)}</span>
      <span class="unit">${esc(L.perQ)}</span>
      ${best.net_total_rs != null && q != null ? `<span class="total">${esc(L.forQ(num(best.net_total_rs), num(q)))}</span>` : ""}`;
    money.setAttribute("aria-label", L.money(num(best.net_price_per_quintal_rs), best.net_total_rs != null ? num(best.net_total_rs) : null, q != null ? num(q) : ""));
    money.hidden = false;
  } else if (best && best.modal_price != null) {
    money.innerHTML = `<span class="label">${esc(L.priceLabel)}</span>
      <span class="big" data-count="${best.modal_price}">₹${num(best.modal_price)}</span>
      <span class="unit">${esc(L.perQPlain)}</span><span class="hint">${esc(L.addRate)}</span>`;
    money.removeAttribute("aria-label");
    money.hidden = false;
  } else { money.hidden = true; money.innerHTML = ""; }
  if (!opts.keepSpeech) countUp(money.querySelector("[data-count]"));

  // chips: date, road distance, storage risk
  const chips = [];
  if (best && best.arrival_date) chips.push(`<span class="chip">${esc(L.chipDate(fmtDate(best.arrival_date)))}${best.stale ? `, ${esc(L.stale(best.age_days))}` : ""}</span>`);
  if (best && best.distance_km != null) chips.push(`<span class="chip">${esc(L.chipKm(num(best.distance_km)))}</span>`);
  const risk = d.weather && d.weather.ok ? d.weather.summary.storage_risk : null;
  if (risk) chips.push(`<span class="chip risk-${risk}">${esc(L.chipRisk(L.risk[risk] || risk))}</span>`);
  $("chips").innerHTML = chips.join("");

  $("answer").textContent = d.answer || "";
  state.lastAnswer = d.answer || "";
  $("reasons").innerHTML = (d.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("");
  const af = $("ask-farmer"); af.hidden = !d.ask_farmer || d.ask_farmer === d.answer; af.textContent = d.ask_farmer || "";
  $("elapsed").textContent = L.answeredIn(d.elapsed_s, d.model);
  $("listen").disabled = !d.answer;
  if (!opts.keepSpeech) $("listen-status").textContent = d.answer ? "" : L.noAnswerText;

  renderMandis(d.mandis, trim(d.best_mandi));
  renderWeather(d.weather, d.place);
  $("trace").innerHTML = (d.trace || []).map(traceItem).join("");
  renderSources(d);
  // hide panels that have nothing to show (e.g. when we only asked the farmer for more details)
  $("mandi-card").hidden = !d.mandis;
  $("weather-card").hidden = !d.weather;
  $("how-card").hidden = !(d.trace && d.trace.length);
  $("sources-card").hidden = !$("sources").children.length;
  $("elapsed").hidden = d.recommendation === "NEED_INFO" && !d.elapsed_s;
  if (!opts.keepSpeech) $("result").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderMandis(m, best) {
  const L = t(), tbody = $("mandis").querySelector("tbody"), cov = $("coverage");
  if (!m || !m.ok) {
    tbody.innerHTML = `<tr><td colspan="7">${esc(m ? m.error : L.noMandi)}</td></tr>`;
    $("mandi-note").textContent = ""; cov.hidden = true;
    return;
  }
  $("mandi-note").textContent = `${m.commodity}, ${m.state}, ${m.distance_method === "road" ? L.roadDist : L.lineDist}` + (m.transport_cost_known ? "" : `; ${L.addCost}`);
  cov.hidden = !m.coverage_note; cov.textContent = m.coverage_note || "";
  const lab = (k) => esc(L[k] || "");
  tbody.innerHTML = m.mandis.map((r) => `
    <tr class="${best && trim(r.market) === best ? "best" : ""}">
      <td>${r.rank}</td>
      <td><span class="mkt">${esc(trim(r.market))}</span><span class="where">${esc(r.district || "")}${r.variety ? ", " + esc(r.variety) : ""}</span></td>
      <td data-label="${lab("thReported")}"><span>${fmtDate(r.arrival_date)}${r.stale ? `<span class="stale">${esc(L.stale(r.age_days))}</span>` : ""}</span></td>
      <td class="num" data-label="${lab("thPrice")}">${num(r.modal_price)}</td>
      <td class="num" data-label="${lab("thDistance")}">${r.distance_km != null ? num(r.distance_km) + " km" : "–"}</td>
      <td class="num" data-label="${lab("thTransport")}">${num(r.transport_per_quintal_rs)}</td>
      <td class="num" data-label="${lab("thNet")}"><b>${num(r.net_price_per_quintal_rs)}</b></td>
    </tr>`).join("");
}

function renderWeather(w, place) {
  const L = t(), box = $("weather");
  if (!w || !w.ok) { box.innerHTML = `<p>${esc(w ? w.error : L.noWeather)}</p>`; $("weather-note").textContent = ""; return; }
  $("weather-note").textContent = place && place.found ? `${place.name}${place.district ? ", " + place.district : ""}` : "";
  const dayName = (iso) => new Date(iso + "T00:00:00").toLocaleDateString(lang() === "en" ? "en-IN" : lang() + "-IN", { weekday: "short", day: "numeric" });
  box.innerHTML = w.days.map((d) => {
    const h = Math.max(0, Math.min(100, Number(d.humidity_mean_pct) || 0));
    return `
    <div class="day ${d.risk}">
      <div class="bar" role="img" aria-label="${esc(dayName(d.date))}: ${num(d.humidity_mean_pct)}% humidity, ${num(d.rain_mm)} mm rain">
        <i style="--h:${h}%"></i><span class="line"></span><b>${num(d.humidity_mean_pct)}%</b>
      </div>
      <span class="when">${dayName(d.date)}</span>
      <span class="rain">${num(d.rain_mm)} mm<br>${esc(L.rainChance(num(d.rain_chance_pct)))}</span>
      <span class="risk">${esc(L.risk[d.risk] || d.risk)}</span>
    </div>`;
  }).join("");
}

function traceItem(s) {
  const L = t(), name = L.stepNames[s.step] || s.step;
  const args = s.args ? Object.entries(s.args).map(([k, v]) => `${k}=${v}`).join(", ") : "";
  return `<li><span class="${s.ok ? "ok" : "fail"}">${s.ok ? "✓" : "✗"}</span> <b>${esc(name)}</b>: ${esc(s.detail || "")}
    ${args ? `<br><code>${esc(s.step)}(${esc(args)})</code>` : ""}${s.ms != null ? ` <span class="hint">${s.ms} ms</span>` : ""}</li>`;
}

function renderSources(d) {
  const L = t(), srcs = [];
  if (d.place && d.place.source) srcs.push(d.place.source);
  if (d.weather && d.weather.source) srcs.push(d.weather.source);
  if (d.mandis && d.mandis.sources) srcs.push(...d.mandis.sources.filter(Boolean));
  const seen = new Set();
  $("sources").innerHTML = srcs.filter((s) => !seen.has(s.name) && seen.add(s.name)).map((s) => `
    <li>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>` : esc(s.name)}
    ${s.fetched_at ? `<span class="hint">${esc(L.fetched)} ${new Date(s.fetched_at).toLocaleString("en-IN")}${s.from_cache ? " " + esc(L.cached) : ""}${s.stale_fallback ? ", " + esc(L.staleFallback) : ""}</span>` : ""}</li>`).join("");
}

// ------------------------------------------------------------------ voice out (Sarvam text-to-speech)
async function listen() {
  const L = t(), status = $("listen-status");
  if (!state.lastAnswer) { status.textContent = L.listenNone; return; }
  $("listen").disabled = true; status.textContent = L.listenPrep;
  try {
    const res = await fetch("/api/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: state.lastAnswer, language: lang() }) });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Voice is unavailable");
    const p = $("player"); p.src = `data:audio/wav;base64,${data.audio_base64}`;
    p.onended = () => { status.textContent = ""; };
    await p.play(); status.textContent = L.listenPlay;
  } catch (e) {
    status.textContent = L.listenFail(e.message);
  } finally {
    $("listen").disabled = false;
  }
}

// ------------------------------------------------------------------ voice in (Sarvam speech-to-text), hands-free
async function toggleMic() {
  const L = t(), btn = $("mic"), status = $("mic-status");
  if (state.recorder && state.recorder.state === "recording") { state.recorder.stop(); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder) { status.textContent = L.micUnsupported; return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
    state.recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    state.chunks = [];
    state.recorder.ondataavailable = (e) => e.data.size && state.chunks.push(e.data);
    state.recorder.onstop = async () => {
      stream.getTracks().forEach((tr) => tr.stop());
      btn.classList.remove("rec"); clearTimeout(state.timer);
      status.textContent = t().micUnderstanding;
      const blob = new Blob(state.chunks, { type: state.recorder.mimeType || "audio/webm" });
      const fd = new FormData(); fd.append("audio", blob, "speech.webm"); fd.append("language", lang());
      try {
        const res = await fetch("/api/transcribe", { method: "POST", body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Could not transcribe");
        $("question").value = data.transcript; status.textContent = t().micGot;
        $("auto-read").checked = true;                 // asked by voice: answer by voice, hands-free
        ask();
      } catch (e) { status.textContent = t().micFail(e.message); }
    };
    state.recorder.start(); btn.classList.add("rec"); status.textContent = L.micListening;
    state.timer = setTimeout(() => state.recorder.state === "recording" && state.recorder.stop(), 25000);
  } catch (e) {
    status.textContent = L.micDenied;
  }
}

// The big number counts up once when a new answer arrives (skipped for reduced motion).
function countUp(el) {
  if (!el || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const target = Number(el.dataset.count); if (!(target > 0)) return;
  const t0 = performance.now(), dur = 700;
  const step = (now) => {
    const p = Math.min(1, (now - t0) / dur), v = Math.round(target * (1 - Math.pow(1 - p, 3)));
    el.textContent = "₹" + v.toLocaleString("en-IN");
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ------------------------------------------------------------------ live sky (home page)
// The hero panel paints Lasalgaon's weather right now from /api/sky (Open-Meteo):
// cloud cover sets the clouds, current rain sets the raindrops, wind sets the drift,
// humidity above the 70% storage line raises mist around the onion. No data, no rain.
const sky = { data: null, clouds: [], drops: [], mist: [], raf: 0, last: 0, visible: true, overlay: false };

async function loadSky() {
  const panel = $("sky-panel");
  if (!panel || getComputedStyle(panel).display === "none") return;     // phones: panel hidden, skip the call
  try {
    const res = await fetch("/api/sky");
    sky.data = await res.json();
  } catch (e) { sky.data = { ok: false }; }
  renderSkyReadout();
  startSky();
}

function renderSkyReadout() {
  const box = $("sky-read"), d = sky.data;
  if (!box || !d) return;
  const L = t(), q = (c) => box.querySelector(c);
  box.hidden = false;
  if (!d.ok) {
    q(".sky-where").textContent = L.skyOff;
    ["sky-vals", "sky-line", "sky-src"].forEach((c) => { q("." + c).textContent = ""; q("." + c).hidden = true; });
    return;
  }
  ["sky-vals", "sky-line", "sky-src"].forEach((c) => { q("." + c).hidden = false; });
  q(".sky-where").textContent = L.skyWhere(d.place.name);
  q(".sky-vals").textContent = L.skyVals(num(Math.round(d.temperature_c)), num(d.humidity_pct), num(d.cloud_cover_pct))
    + (d.rain_mm > 0 ? L.skyRain(num(d.rain_mm)) : L.skyDry);
  const line = q(".sky-line");
  line.textContent = d.humid_for_storage ? L.skyOver : L.skyUnder;
  line.className = "sky-line" + (d.humid_for_storage ? " over" : "");
  const when = new Date(d.time + ":00+05:30").toLocaleTimeString(lang() === "en" ? "en-IN" : lang() + "-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" });
  q(".sky-src").textContent = L.skySrc(when);
}

function skyLevels() {
  const d = sky.data && sky.data.ok ? sky.data : null;
  return {
    cover: d ? d.cloud_cover_pct / 100 : 0.35,
    rain: d ? Math.min(1, d.rain_mm / 4) : 0,          // 4 mm or more reads as a downpour
    wet: d && d.rain_mm > 0,
    wind: d ? d.wind_kmh : 6,
    mist: d ? Math.max(0, Math.min(1, (d.humidity_pct - 60) / 35)) : 0,
    day: d ? d.is_day : true,
  };
}

function startSky() {
  const cv = $("sky"); if (!cv) return;
  const ctx = cv.getContext("2d"), still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let W = 0, H = 0;
  const size = () => {
    const r = cv.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
    W = r.width; H = r.height; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  size(); new ResizeObserver(size).observe(cv);
  $("sky-panel").classList.toggle("sky-panel-night", !skyLevels().day);

  const lv = skyLevels(), rnd = (a, b) => a + Math.random() * (b - a);
  const nClouds = Math.round(2 + lv.cover * 8);
  sky.clouds = Array.from({ length: nClouds }, (_, i) => ({
    x: rnd(-0.2, 1.1), y: rnd(0.04, 0.42), s: rnd(0.55, 1.25), v: rnd(0.6, 1.4),
    puffs: Array.from({ length: 5 }, () => [rnd(-1, 1), rnd(-0.35, 0.25), rnd(0.45, 0.85)]),
  }));
  const nDrops = lv.wet ? Math.round(40 + lv.rain * 260) : 0;
  sky.drops = Array.from({ length: nDrops }, () => ({ x: Math.random(), y: Math.random(), l: rnd(10, 22), v: rnd(0.8, 1.2) }));
  sky.mist = Array.from({ length: lv.mist > 0 ? 7 : 0 }, () => ({ x: Math.random(), y: rnd(0.62, 0.98), r: rnd(0.25, 0.45), v: rnd(0.4, 1) }));

  const frame = (now) => {
    const dt = Math.min(0.05, (now - (sky.last || now)) / 1000); sky.last = now;
    const L = skyLevels();
    // sky: clear blue to monsoon grey by cloud cover; dusk-indigo at night
    if (sky.overlay) ctx.clearRect(0, 0, W, H);   // footage underneath: add only live rain and mist
    const g = ctx.createLinearGradient(0, 0, 0, H);
    if (sky.overlay) { /* no painted sky */ }
    else if (L.day) {
      g.addColorStop(0, mix([122, 170, 204], [128, 146, 156], L.cover));
      g.addColorStop(1, mix([226, 238, 244], [214, 222, 224], L.cover));
    } else {
      g.addColorStop(0, mix([22, 34, 58], [36, 44, 56], L.cover));
      g.addColorStop(1, mix([58, 72, 104], [74, 84, 98], L.cover));
    }
    if (!sky.overlay) { ctx.fillStyle = g; ctx.fillRect(0, 0, W, H); }

    // clouds drift with the wind
    const drift = (4 + L.wind * 1.2) / 1000;
    if (!sky.overlay) for (const c of sky.clouds) {
      c.x += drift * c.v * dt * 10; if (c.x > 1.3) c.x = -0.3;
      const cx = c.x * W, cy = c.y * H, base = Math.min(W, H) * 0.16 * c.s;
      for (const [dx, dy, r] of c.puffs) {
        const px = cx + dx * base, py = cy + dy * base, pr = base * r;
        const rg = ctx.createRadialGradient(px, py, 0, px, py, pr);
        const shade = L.day ? mix([255, 255, 255], [196, 206, 212], L.cover) : "rgb(120,132,150)";
        rg.addColorStop(0, shade.replace("rgb", "rgba").replace(")", `,${0.5 + L.cover * 0.4})`));
        rg.addColorStop(1, shade.replace("rgb", "rgba").replace(")", ",0)"));
        ctx.fillStyle = rg; ctx.beginPath(); ctx.arc(px, py, pr, 0, Math.PI * 2); ctx.fill();
      }
    }

    // rain, only when it is actually raining there now
    if (sky.drops.length) {
      const slant = Math.min(0.5, L.wind / 40);
      ctx.strokeStyle = L.day ? "rgba(70, 92, 110, .55)" : "rgba(200, 214, 230, .5)"; ctx.lineWidth = 1.2; ctx.beginPath();
      for (const d of sky.drops) {
        d.y += d.v * dt * 1.4; d.x += slant * dt * 0.4;
        if (d.y > 1) { d.y = -0.05; d.x = Math.random(); }
        if (d.x > 1) d.x -= 1;
        const x = d.x * W, y = d.y * H;
        ctx.moveTo(x, y); ctx.lineTo(x - slant * d.l, y + d.l);
      }
      ctx.stroke();
    }

    // humidity mist around the onion, stronger the further above 70% it is
    for (const m of sky.mist) {
      m.x += m.v * dt * 0.012; if (m.x > 1.4) m.x = -0.4;
      const r = m.r * W, rg = ctx.createRadialGradient(m.x * W, m.y * H, 0, m.x * W, m.y * H, r);
      rg.addColorStop(0, `rgba(255,255,255,${(sky.overlay ? 0.2 : 0.35) * L.mist})`); rg.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);
    }
    if (!still && sky.visible) sky.raf = requestAnimationFrame(frame);
  };
  const run = () => { cancelAnimationFrame(sky.raf); sky.last = 0; sky.raf = requestAnimationFrame(frame); };
  // pause when the panel scrolls away or the tab is hidden
  new IntersectionObserver(([e]) => { sky.visible = e.isIntersecting; if (sky.visible) run(); }).observe(cv);
  document.addEventListener("visibilitychange", () => { sky.visible = !document.hidden; if (sky.visible) run(); });
  run();
}

function mix(a, b, k) {
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * Math.max(0, Math.min(1, k))));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

// Hero footage (Kling AI loop): laptops only, never on data-saver or reduced motion.
// If the file is missing or fails, the live drawn sky stays. With footage, the canvas
// only adds what the live data says: rain streaks while it rains, mist above 70% humidity.
function loadHeroVideo() {
  const v = $("hero-video"), panel = $("sky-panel"), conn = navigator.connection || {};
  if (!v || !panel || conn.saveData || !matchMedia("(min-width: 901px)").matches || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  v.addEventListener("canplay", () => {
    v.hidden = false; panel.classList.add("has-video"); sky.overlay = true; $("media-credit").hidden = false;
    v.play().catch(() => { /* autoplay blocked: poster stays, live overlay still works */ });
  }, { once: true });
  v.addEventListener("error", () => { sky.overlay = false; panel.classList.remove("has-video"); v.hidden = true; $("media-credit").hidden = true; });
  v.src = "/static/media/hero.mp4";
  v.load();
}

// ------------------------------------------------------------------ start
try { const saved = localStorage.getItem("mm-lang"); if (saved && T[saved]) $("language").value = saved; } catch (e) { /* ignore */ }
applyLang();
loadHeroVideo();
loadSky();
