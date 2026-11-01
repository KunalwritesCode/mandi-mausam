"""Builds the animated SVG figures used in README.md.

Every number below is copied from a cited source (listed next to it), or computed from
those numbers. The one worked example (net-price.svg) is labelled as illustrative.
Run:  python docs/make_figures.py
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).parent / "assets"
OUT.mkdir(exist_ok=True)

# Palette: reference data-viz palette (slot 1 blue), neutral grays, fixed status colours.
BLUE, BLUE_DARK, GRAY, GRAY_TXT = "#2a78d6", "#1c5cab", "#d6d3cb", "#52514e"
INK, MUTED, SURFACE, LINE = "#0b0b0b", "#6b6a66", "#fcfcfb", "#e6e4de"
GOOD, CRITICAL = "#0ca30c", "#d03b3b"
FONT = '-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,"Noto Sans",sans-serif'


def frame(w: int, h: int, body: str, title: str, label: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{label}">
<title>{title}</title>
<style>
 text {{ font-family: {FONT}; }}
 .title {{ font-size: 20px; font-weight: 700; fill: {INK}; }}
 .sub {{ font-size: 13px; fill: {GRAY_TXT}; }}
 .lab {{ font-size: 14px; fill: {INK}; }}
 .lab-b {{ font-size: 14px; font-weight: 700; fill: {INK}; }}
 .val {{ font-size: 13px; font-weight: 600; fill: {INK}; }}
 .small {{ font-size: 12px; fill: {GRAY_TXT}; }}
 .src {{ font-size: 11px; fill: {MUTED}; }}
 .on-blue {{ font-size: 13px; font-weight: 700; fill: #ffffff; }}
</style>
<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="16" fill="{SURFACE}" stroke="{LINE}"/>
{body}
</svg>
"""


def grow(final_w: float, delay: float, dur: float = 1.0) -> str:
    """Width animation that starts at 0 on load. Without SMIL support the final width shows."""
    total = delay + dur
    return (f'<animate attributeName="width" dur="{total:.2f}s" fill="freeze" '
            f'values="0;0;{final_w:.1f}" keyTimes="0;{delay / total:.3f};1" '
            f'calcMode="spline" keySplines="0 0 1 1;0.2 0.8 0.2 1"/>')


def fade_in(delay: float, dur: float = 0.5) -> str:
    total = delay + dur
    return (f'<animate attributeName="opacity" dur="{total:.2f}s" fill="freeze" '
            f'values="0;0;1" keyTimes="0;{delay / total:.3f};1"/>')


def inr(v: float) -> str:
    return f"{v:,.0f}"


# ---------------------------------------------------------------- 1. rupee split
def rupee_split() -> None:
    # RBI Working Paper 08/2024 (Oct 2024): farmers' share of the consumer rupee.
    data = [("Tomato", 33), ("Onion", 36), ("Potato", 37)]
    x0, W, h = 150, 690, 36
    body = [
        '<text x="32" y="44" class="title">Of every ₹100 a shopper pays, about a third reaches the farmer</text>',
        '<text x="32" y="66" class="sub">Farmer\'s share of the consumer rupee for India\'s three biggest vegetables</text>',
    ]
    for i, (crop, share) in enumerate(data):
        y = 96 + i * 56
        fw = W * share / 100
        delay = 0.3 + 0.25 * i
        body.append(f'<text x="32" y="{y + 23}" class="lab-b">{crop}</text>')
        body.append(f'<rect x="{x0 + fw + 2:.1f}" y="{y}" width="{W - fw - 2:.1f}" height="{h}" rx="4" fill="{GRAY}">{fade_in(delay + 0.9, 0.4)}</rect>')
        body.append(f'<rect x="{x0}" y="{y}" width="{fw:.1f}" height="{h}" rx="4" fill="{BLUE}">{grow(fw, delay)}</rect>')
        body.append(f'<text x="{x0 + 12}" y="{y + 23}" class="on-blue">₹{share} to the farmer{fade_in(delay + 0.9)}</text>')
        body.append(f'<text x="{x0 + fw + 14:.1f}" y="{y + 23}" class="val" style="fill:{GRAY_TXT}">₹{100 - share} to the rest of the chain{fade_in(delay + 1.1)}</text>')
    body.append('<text x="32" y="282" class="src">Source: RBI Working Paper 08/2024, "Vegetables Inflation in India: A Study of Tomato, Onion and Potato" (estimates rounded).</text>')
    (OUT / "rupee-split.svg").write_text(frame(880, 300, "\n".join(body),
        "Farmer's share of the consumer rupee", "Farmers receive about 33 rupees of every 100 for tomato, 36 for onion and 37 for potato"))


# ---------------------------------------------------------------- 2. post-harvest loss
def post_harvest_loss() -> None:
    # Lok Sabha unstarred question 1773, 5 Dec 2024 (NABCONS 2022, reference years 2020-22), Rs crore.
    data = [("Livestock produce", 29871.41), ("Fruits", 29545.07), ("Vegetables", 27459.08), ("Cereals", 26000.79),
            ("Plantation crops", 16412.56), ("Oilseeds", 10924.97), ("Pulses", 9289.21), ("Eggs", 3287.32)]
    onion = 5156.32
    x0, W, h = 210, 520, 24
    mx = max(v for _, v in data)
    body = [
        '<text x="32" y="44" class="title">₹27,459 crore of vegetables is lost after harvest each year</text>',
        '<text x="32" y="66" class="sub">Estimated value of post-harvest loss by category, ₹ crore. Onion alone accounts for ₹5,156 crore.</text>',
    ]
    y = 92
    for i, (name, v) in enumerate(data):
        fw = W * v / mx
        hi = name == "Vegetables"
        fill = BLUE if hi else GRAY
        delay = 0.2 + 0.12 * i
        body.append(f'<text x="32" y="{y + 17}" class="{"lab-b" if hi else "lab"}">{name}</text>')
        body.append(f'<rect x="{x0}" y="{y}" width="{fw:.1f}" height="{h}" rx="4" fill="{fill}">{grow(fw, delay)}</rect>')
        body.append(f'<text x="{x0 + fw + 10:.1f}" y="{y + 17}" class="val">₹{inr(v)}{fade_in(delay + 0.9)}</text>')
        y += 38
        if hi:
            ow = W * onion / mx
            body.append(f'<text x="48" y="{y + 12}" class="small">of which onion</text>')
            body.append(f'<rect x="{x0}" y="{y}" width="{ow:.1f}" height="14" rx="3" fill="{BLUE_DARK}">{grow(ow, delay + 1.0)}</rect>')
            body.append(f'<text x="{x0 + ow + 10:.1f}" y="{y + 12}" class="val">₹{inr(onion)}{fade_in(delay + 1.8)}</text>')
            y += 28
    body.append(f'<text x="32" y="{y + 26}" class="src">Source: Ministry of Food Processing Industries, Lok Sabha unstarred question 1773 (5 Dec 2024), citing the NABCONS 2022 study (reference years 2020-22).</text>')
    (OUT / "post-harvest-loss.svg").write_text(frame(880, y + 46, "\n".join(body),
        "Post-harvest loss by category", "Vegetables lose 27,459 crore rupees a year after harvest; onion alone 5,156 crore"))


# ---------------------------------------------------------------- 3. Lasalgaon price drop
def lasalgaon_drop() -> None:
    # Free Press Journal, 6 Oct 2026: Lasalgaon APMC summer onion average price.
    p1, p2 = 4451, 3900
    x1, x2 = 230, 650
    def Y(p: float) -> float:
        return 116 + (4600 - p) / 800 * 150
    y1, y2 = Y(p1), Y(p2)
    L = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    drop, pct = p1 - p2, (p1 - p2) / p1 * 100
    body = [
        '<text x="32" y="44" class="title">Five days, ₹551 a quintal: how fast onion prices move</text>',
        '<text x="32" y="66" class="sub">Average price of summer onion at Lasalgaon APMC (Nashik), ₹ per quintal, October 2026</text>',
        f'<line x1="{x1}" x2="{x2}" y1="{Y(3800):.1f}" y2="{Y(3800):.1f}" stroke="{LINE}" stroke-width="1"/>',
        f'<line x1="{x1}" y1="{y1:.1f}" x2="{x2}" y2="{y2:.1f}" stroke="{BLUE}" stroke-width="2.5" stroke-linecap="round" '
        f'stroke-dasharray="{L:.1f}" stroke-dashoffset="0">'
        f'<animate attributeName="stroke-dashoffset" dur="2s" fill="freeze" values="{L:.1f};{L:.1f};0" keyTimes="0;0.3;1"/></line>',
        f'<circle cx="{x1}" cy="{y1:.1f}" r="6" fill="{BLUE}" stroke="{SURFACE}" stroke-width="2"/>',
        f'<circle cx="{x2}" cy="{y2:.1f}" r="6" fill="{BLUE}" stroke="{SURFACE}" stroke-width="2">{fade_in(2.0, 0.3)}</circle>',
        f'<text x="{x1}" y="{y1 - 16:.1f}" text-anchor="middle" class="lab-b">₹{inr(p1)}</text>',
        f'<text x="{x2 + 14}" y="{y2 + 5:.1f}" class="lab-b">₹{inr(p2)}{fade_in(2.0)}</text>',
        f'<text x="{x1}" y="{Y(3800) + 22:.1f}" text-anchor="middle" class="small">1 Oct</text>',
        f'<text x="{x2}" y="{Y(3800) + 22:.1f}" text-anchor="middle" class="small">6 Oct</text>',
        f'<g opacity="1">{fade_in(2.3)}'
        f'<text x="690" y="132" class="lab-b">−₹{drop} a quintal</text>'
        f'<text x="690" y="152" class="small">−{pct:.0f}% in five days</text>'
        f'<text x="690" y="182" class="small">For 20 quintals, that is</text>'
        f'<text x="690" y="200" class="small">₹{inr(drop * 20)} less (our calculation)</text></g>',
        '<text x="32" y="306" class="src">Source: Free Press Journal, "Nashik: Egyptian Onions, Fresh Kharif Arrivals Put Pressure On Onion Prices", 6 Oct 2026.</text>',
    ]
    (OUT / "lasalgaon-drop.svg").write_text(frame(880, 324, "\n".join(body),
        "Lasalgaon onion price, 1 to 6 October 2026", "Average onion price at Lasalgaon fell from 4,451 to 3,900 rupees a quintal between 1 and 6 October 2026"))


# ---------------------------------------------------------------- 4. agent flow (looping)
def agent_flow() -> None:
    T = 9.0  # seconds per loop
    nodes = [
        ("1", "Farmer asks", "voice or text · EN, हिंदी, मराठी"),
        ("2", "Find the village", "Open-Meteo · OSM"),
        ("3", "7-day rain &amp; humidity", "Open-Meteo forecast"),
        ("4", "Mandi prices today", "data.gov.in · Agmarknet"),
        ("5", "Road distance", "OSRM · OSM roads"),
        ("6", "Price after transport", "plain Python maths"),
        ("7", "Check every number", "grounding guard"),
        ("8", "Answer, out loud", "Sarvam-105B · Bulbul voice"),
    ]
    w, h, xs = 188, 70, [32, 246, 460, 674]
    r1, r2 = 118, 262
    pos = [(xs[i], r1) for i in range(4)] + [(xs[3 - i], r2) for i in range(4)]
    cx = [x + w / 2 for x, _ in pos]
    cy = [y + h / 2 for _, y in pos]
    # Path through node centres; cumulative distance -> arrival time.
    seg = [abs(cx[i + 1] - cx[i]) + abs(cy[i + 1] - cy[i]) for i in range(7)]
    total = sum(seg)
    dist = [0.0]
    for s in seg:
        dist.append(dist[-1] + s)
    t0, t1 = 0.5, 8.0
    arrive = [t0 + (t1 - t0) * d / total for d in dist]
    body = [
        '<text x="32" y="44" class="title">How one question becomes one honest answer</text>',
        '<text x="32" y="66" class="sub">The AI model decides which tool to call next and explains the result. Plain code does every rupee of maths.</text>',
        f'<rect x="32" y="82" width="830" height="22" rx="11" fill="#eef3fb"/>',
        f'<text x="447" y="97" text-anchor="middle" class="small">Sarvam-105B plans each step · every number it says must exist in the live data, or it is sent back to fix it</text>',
    ]
    # connectors
    ay1, ay2 = cy[0], cy[4]
    conn = []
    for i in range(3):
        conn.append(f'M{xs[i] + w + 4},{ay1} H{xs[i + 1] - 6}')
    conn.append(f'M{cx[3]},{r1 + h + 4} V{r2 - 6}')
    for i in range(3):
        conn.append(f'M{xs[3 - i] - 4},{ay2} H{xs[2 - i] + w + 6}')
    body.append('<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
                f'<path d="M0 0L10 5L0 10z" fill="{MUTED}"/></marker></defs>')
    for d in conn:
        body.append(f'<path d="{d}" stroke="{MUTED}" stroke-width="1.5" fill="none" marker-end="url(#ar)"/>')
    for i, ((num, name, sub), (x, y)) in enumerate(zip(nodes, pos)):
        a = arrive[i]
        k1, k2, k3 = a / T, min((a + 0.15) / T, 0.995), min((a + 1.3) / T, 0.999)
        k0 = max(k1 - 0.001, 0.0)
        glow = (f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" '
                f'values="0;0;0.22;0;0" keyTimes="0;{k0:.4f};{k2:.4f};{k3:.4f};1"/>') if k1 > 0 else (
                f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" values="0.22;0;0" keyTimes="0;{k3:.4f};1"/>')
        hi = i in (6, 7)
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#ffffff" stroke="{BLUE if hi else LINE}" stroke-width="{1.5 if hi else 1}"/>')
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{BLUE}" opacity="0">{glow}</rect>')
        body.append(f'<circle cx="{x + 22}" cy="{y + 24}" r="11" fill="{BLUE}"/><text x="{x + 22}" y="{y + 28.5}" text-anchor="middle" class="on-blue" style="font-size:12px">{num}</text>')
        body.append(f'<text x="{x + 40}" y="{y + 29}" class="lab-b">{name}</text>')
        body.append(f'<text x="{x + 16}" y="{y + 54}" class="small">{sub}</text>')
    path = f"M{cx[0]},{cy[0]} " + " ".join(f"L{cx[i]},{cy[i]}" for i in range(1, 8))
    body.append(f'<circle r="7" fill="{BLUE}" stroke="#ffffff" stroke-width="2">'
                f'<animateMotion dur="{T}s" repeatCount="indefinite" path="{path}" keyPoints="0;0;1;1" '
                f'keyTimes="0;{t0 / T:.4f};{t1 / T:.4f};1" calcMode="linear"/></circle>')
    body.append('<text x="32" y="368" class="src">Steps 2-5 call live public APIs at question time. Step 6 is ordinary code, so the arithmetic cannot be hallucinated.</text>')
    (OUT / "agent-flow.svg").write_text(frame(880, 386, "\n".join(body),
        "How Mandi-Mausam decides", "Eight steps from the farmer's question to a checked, spoken answer"))


# ---------------------------------------------------------------- 5. worked example: net price (looping)
def net_price() -> None:
    # ILLUSTRATIVE round numbers (not market data): 10 quintals, Rs 40 per km.
    qty, rate = 10, 40
    m = [("Mandi A", 5, 3900), ("Mandi B", 120, 4000)]
    T, x0, W = 10.0, 230, 520
    scale = W / 4000
    body = [
        '<text x="32" y="44" class="title">The highest price is not always the most money</text>',
        f'<text x="32" y="66" class="sub">Worked example with round numbers (not market data): {qty} quintals, transport ₹{rate} per km</text>',
    ]
    nets = []
    for i, (name, km, price) in enumerate(m):
        y = 104 + i * 86
        per_q = rate * km / qty
        net = price - per_q
        nets.append(net)
        Qw, Nw = price * scale, net * scale
        kt = "0;0.12;0.30;0.42;0.94;1"
        body.append(f'<text x="32" y="{y + 20}" class="lab-b">{name}</text>')
        body.append(f'<text x="32" y="{y + 40}" class="small">{km} km away</text>')
        body.append(f'<rect x="{x0}" y="{y}" width="{Qw:.1f}" height="34" rx="4" fill="{GRAY}">'
                    f'<animate attributeName="width" dur="{T}s" repeatCount="indefinite" values="0;{Qw:.1f};{Qw:.1f};{Qw:.1f};{Qw:.1f};0" keyTimes="{kt}"/></rect>')
        body.append(f'<rect x="{x0}" y="{y}" width="{Nw:.1f}" height="34" rx="4" fill="{BLUE}">'
                    f'<animate attributeName="width" dur="{T}s" repeatCount="indefinite" values="0;{Qw:.1f};{Qw:.1f};{Nw:.1f};{Nw:.1f};0" keyTimes="{kt}"/></rect>')
        show_q = f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" values="0;0;1;1;0;0" keyTimes="0;0.10;0.14;0.28;0.30;1"/>'
        show_n = f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" values="0;0;1;1;0" keyTimes="0;0.42;0.46;0.94;1"/>'
        body.append(f'<text x="{x0 + Qw + 12:.1f}" y="{y + 22}" class="val" opacity="0">quoted ₹{inr(price)}{show_q}</text>')
        body.append(f'<text x="{x0 + Qw + 12:.1f}" y="{y + 22}" class="val" opacity="0">you keep ₹{inr(net)}{show_n}</text>')
        body.append(f'<text x="{x0}" y="{y + 54}" class="small" opacity="0">transport ₹{rate} × {km} km ÷ {qty} quintals = ₹{inr(per_q)} a quintal{show_n}</text>')
    gain = (nets[0] - nets[1]) * qty
    win = f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" values="0;0;1;1;0" keyTimes="0;0.52;0.56;0.94;1"/>'
    body.append(f'<g opacity="0">{win}<rect x="32" y="282" width="816" height="34" rx="8" fill="#eaf6ea"/>'
                f'<text x="48" y="304" class="lab-b">✓ Mandi A leaves you ₹{inr(gain)} more for {qty} quintals, even though B quotes ₹100 more.</text></g>')
    body.append('<text x="32" y="342" class="src">Mandi-Mausam does exactly this with live prices, real road distances and the transport rate the farmer gives.</text>')
    (OUT / "net-price.svg").write_text(frame(880, 360, "\n".join(body),
        "Price after transport, worked example", "Illustrative example: a nearer mandi with a lower quote can leave the farmer more money after transport"))


# ---------------------------------------------------------------- 6. the doors we tried
def doors() -> None:
    rows = [
        ("Where today's prices come from", [
            ("✗", "Agmarknet 2.0 API", "Price report needs a captcha.", "We do not bypass captchas."),
            ("✗", "Community mirror", "Last synced 16 Oct 2026:", "16 days old on 1 Nov."),
            ("✓", "data.gov.in official API", "Feed updated 1 Nov, 11:30 AM;", "prices dated 1 Nov 2026."),
        ]),
        ("Which AI model answers", [
            ("✗", "Gemini (flash-latest)", "No reply within 40 s,", "on both API routes."),
            ("✗", "Gemini 2.5 Flash", "HTTP 404: no longer offered", "to new users."),
            ("✓", "Sarvam-105B", "Replied in 0.59 s with the", "right tool call for Lasalgaon."),
        ]),
    ]
    w, h, xs = 262, 92, [32, 309, 586]
    body = [
        '<text x="32" y="44" class="title">Six doors we knocked on, and the two that opened</text>',
        '<text x="32" y="66" class="sub">Every source was tested live from our laptop before we built on it (31 Oct - 1 Nov 2026)</text>',
    ]
    for r, (heading, cards) in enumerate(rows):
        y0 = 100 + r * 150
        body.append(f'<text x="32" y="{y0 + 4}" class="lab-b">{heading}</text>')
        for c, (mark, name, l1, l2) in enumerate(cards):
            x, y = xs[c], y0 + 18
            ok = mark == "✓"
            delay = 0.3 + 0.35 * (r * 3 + c)
            body.append(f'<g opacity="1">{fade_in(delay, 0.4)}'
                        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{"#f1f9f1" if ok else "#ffffff"}" '
                        f'stroke="{GOOD if ok else LINE}" stroke-width="{2 if ok else 1}"/>'
                        f'<text x="{x + 16}" y="{y + 28}" style="font-size:17px;font-weight:700;fill:{GOOD if ok else CRITICAL}">{mark}</text>'
                        f'<text x="{x + 38}" y="{y + 28}" class="lab-b">{name}</text>'
                        f'<text x="{x + 16}" y="{y + 54}" class="small">{l1}</text>'
                        f'<text x="{x + 16}" y="{y + 72}" class="small">{l2}</text>'
                        f'<text x="{x + w - 14}" y="{y + 28}" text-anchor="end" class="small" style="font-weight:700">{"Chosen" if ok else "Rejected"}</text></g>')
    body.append('<text x="32" y="412" class="src">Details and timings for each test are in the build log below.</text>')
    (OUT / "doors.svg").write_text(frame(880, 430, "\n".join(body),
        "Data and model sources we tested", "Of three price sources and three AI models tested, data.gov.in and Sarvam-105B worked"))


if __name__ == "__main__":
    rupee_split()
    post_harvest_loss()
    lasalgaon_drop()
    agent_flow()
    net_price()
    doors()
    print("wrote", sorted(p.name for p in OUT.glob("*.svg")))
