"""
PDH/PDL Trading Signal Bot — STRATEGY-ACCURATE VERSION
Gautam (Stock Learners) ki strategy ke hisaab se:
1. PDH/PDL mark karta hai (previous day high/low)
2. 1-MINUTE candles fetch karta hai (sirf LTP nahi)
3. Confirmation candle check karta hai:
   - SHORT: PDH break -> RED candle -> uska low break
   - LONG:  PDL break -> GREEN candle -> uska high break
4. Target = nearest SWING level (poora PDH/PDL nahi)
5. SL confirmation candle ke upar/neeche, 80/30 pts se bada -> SKIP
6. Gold + Gold Petal dono ke alag signal bhejta hai

Har 30 min chalta hai. Pichle ~35 min ki 1-min candles scan karke
jo bhi fresh signal bana, wo bhejta hai (duplicate avoid karta hai).
"""

import os
import json
import requests
from datetime import datetime, timedelta

# ─── TELEGRAM ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1766130094")
UPSTOX_TOKEN     = os.environ.get("UPSTOX_TOKEN", "")

# ─── DONO INSTRUMENTS ───────────────────────────────────────────────────────
# Har instrument ka apna key, risk, aur max-SL.
INSTRUMENTS = [
    {"name": "GOLD",  "key": "MCX_FO|466583", "risk": 5000, "max_sl": 80},   # GOLD26AUGFUT
    {"name": "PETAL", "key": "MCX_FO|552721", "risk": 1000, "max_sl": 30},   # GOLDPETAL26JULFUT
]

SWING_LOOKBACK = 3   # swing high/low confirm karne ke liye dono taraf kitni candles

# ─── FILTERS (Gautam ki strategy ke hisaab se) ──────────────────────────────
MIN_RR = 1.5                 # Isse kam R:R waale signal SKIP (1:0.6 jaise ghatiya hatao)
MAX_SIGNALS_PER_LEVEL = 2    # Ek din, ek instrument, ek level pe max itne signal

# ─── TELEGRAM SEND ──────────────────────────────────────────────────────────
def send_telegram(message):
    if not TELEGRAM_TOKEN:
        print("Telegram token nahi hai!")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            print("✅ Telegram message sent!")
            return True
        print(f"❌ Telegram error: {r.text}")
    except Exception as e:
        print(f"❌ Telegram exception: {e}")
    return False

# ─── UPSTOX ─────────────────────────────────────────────────────────────────
def headers():
    return {"Authorization": f"Bearer {UPSTOX_TOKEN}", "Accept": "application/json"}

def fetch_pdh_pdl(key):
    """Previous trading day ka high/low."""
    if not UPSTOX_TOKEN:
        return None, None
    yday = datetime.now() - timedelta(days=1)
    while yday.weekday() >= 5:        # weekend skip
        yday -= timedelta(days=1)
    d = yday.strftime("%Y-%m-%d")
    url = f"https://api.upstox.com/v2/historical-candle/{requests.utils.quote(key, safe='')}/day/{d}/{d}"
    try:
        r = requests.get(url, headers=headers(), timeout=10)
        data = r.json()
        if data.get("data") and data["data"].get("candles"):
            c = data["data"]["candles"][0]
            return float(c[2]), float(c[3])     # high, low
    except Exception as e:
        print(f"PDH/PDL error ({key}): {e}")
    return None, None

def fetch_today_1min(key):
    """
    Aaj ke 1-minute candles. Upstox 'intraday' endpoint use karta hai
    jo current day ka live data deta hai.
    Returns list of dicts: {ts, open, high, low, close}
    """
    if not UPSTOX_TOKEN:
        return []
    url = f"https://api.upstox.com/v2/historical-candle/intraday/{requests.utils.quote(key, safe='')}/1minute"
    try:
        r = requests.get(url, headers=headers(), timeout=10)
        data = r.json()
        candles = (data.get("data") or {}).get("candles") or []
        out = []
        for c in candles:
            out.append({
                "ts": c[0],
                "open": float(c[1]), "high": float(c[2]),
                "low": float(c[3]), "close": float(c[4]),
            })
        # Upstox intraday newest-first deta hai — purane se naye karo
        out.sort(key=lambda x: x["ts"])
        return out
    except Exception as e:
        print(f"1-min fetch error ({key}): {e}")
        return []

# ─── SWING DETECTION ────────────────────────────────────────────────────────
def swing_low_below(candles, start_idx, entry):
    n = len(candles)
    for i in range(start_idx, n - SWING_LOOKBACK):
        lo = candles[i]["low"]
        if lo >= entry:
            continue
        left  = all(candles[i]["low"] <= candles[i-k]["low"] for k in range(1, SWING_LOOKBACK+1) if i-k >= 0)
        right = all(candles[i]["low"] <= candles[i+k]["low"] for k in range(1, SWING_LOOKBACK+1))
        if left and right:
            return lo
    return None

def swing_high_above(candles, start_idx, entry):
    n = len(candles)
    for i in range(start_idx, n - SWING_LOOKBACK):
        hi = candles[i]["high"]
        if hi <= entry:
            continue
        left  = all(candles[i]["high"] >= candles[i-k]["high"] for k in range(1, SWING_LOOKBACK+1) if i-k >= 0)
        right = all(candles[i]["high"] >= candles[i+k]["high"] for k in range(1, SWING_LOOKBACK+1))
        if left and right:
            return hi
    return None

# ─── STRATEGY: scan candles for confirmed signals ───────────────────────────
def detect_signal(candles, pdh, pdl, max_sl):
    """
    Pure 1-minute candles pe strategy logic chalata hai.
    SHORT: kisi candle ka high PDH ke upar -> next candle RED ->
           uske agle candle ne RED ka low break kiya = ENTRY.
    LONG:  ulta, PDL ke neeche -> GREEN -> high break.
    SAARE valid signals return karta hai (chronological order mein) jo:
      - SL <= max_sl, aur
      - R:R >= MIN_RR  (ghatiya 1:0.6 jaise signal skip)
    Returns list of dicts (empty list agar kuch nahi).
    """
    if not candles or pdh is None or pdl is None:
        return []

    signals = []
    n = len(candles)

    for j in range(1, n - 1):
        prev_c = candles[j-1]
        curr_c = candles[j]
        next_c = candles[j+1]

        # ── SHORT setup ──
        if prev_c["high"] > pdh and curr_c["close"] < curr_c["open"]:   # red candle above PDH
            red_low, red_high = curr_c["low"], curr_c["high"]
            if next_c["low"] < red_low:                                # confirmation: low break
                entry  = red_low
                sl     = red_high + 2
                sl_pts = round(sl - entry, 2)
                if 0 < sl_pts <= max_sl:
                    target = swing_low_below(candles, j+2, entry)
                    if target is not None:
                        rr = round((entry - target) / sl_pts, 2)
                        if rr >= MIN_RR:                               # R:R filter
                            signals.append({
                                "side": "SHORT", "entry": round(entry, 2),
                                "sl": round(sl, 2), "sl_pts": sl_pts,
                                "target": round(target, 2), "rr": rr,
                                "candle_time": next_c["ts"],
                            })

        # ── LONG setup ──
        if prev_c["low"] < pdl and curr_c["close"] > curr_c["open"]:    # green candle below PDL
            grn_high, grn_low = curr_c["high"], curr_c["low"]
            if next_c["high"] > grn_high:                              # confirmation: high break
                entry  = grn_high
                sl     = grn_low - 2
                sl_pts = round(entry - sl, 2)
                if 0 < sl_pts <= max_sl:
                    target = swing_high_above(candles, j+2, entry)
                    if target is not None:
                        rr = round((target - entry) / sl_pts, 2)
                        if rr >= MIN_RR:                               # R:R filter
                            signals.append({
                                "side": "LONG", "entry": round(entry, 2),
                                "sl": round(sl, 2), "sl_pts": sl_pts,
                                "target": round(target, 2), "rr": rr,
                                "candle_time": next_c["ts"],
                            })

    return signals

# ─── SKIP detection (signal bana par SL bada) ───────────────────────────────
def detect_skip(candles, pdh, pdl, max_sl):
    """Agar confirmation bana lekin SL max se bada tha — user ko batao."""
    if not candles or pdh is None or pdl is None:
        return None
    n = len(candles)
    for j in range(n - 2, 0, -1):       # latest se peeche
        prev_c, curr_c, next_c = candles[j-1], candles[j], candles[j+1]
        if prev_c["high"] > pdh and curr_c["close"] < curr_c["open"] and next_c["low"] < curr_c["low"]:
            sl_pts = round((curr_c["high"] + 2) - curr_c["low"], 2)
            if sl_pts > max_sl:
                return {"side": "SHORT", "sl_pts": sl_pts}
        if prev_c["low"] < pdl and curr_c["close"] > curr_c["open"] and next_c["high"] > curr_c["high"]:
            sl_pts = round(curr_c["high"] - (curr_c["low"] - 2), 2)
            if sl_pts > max_sl:
                return {"side": "LONG", "sl_pts": sl_pts}
    return None

# ─── DEDUP: same signal baar baar na bheje ──────────────────────────────────
STATE_FILE = "last_signals.json"

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"State save error: {e}")

# ─── MESSAGES ───────────────────────────────────────────────────────────────
def msg_morning(inst, pdh, pdl, ltp):
    now = datetime.now().strftime("%d %b %Y %H:%M")
    rng = pdh - pdl
    return f"""🌅 <b>Good Morning Abhishek!</b>
📅 {now} IST | MCX {inst['name']}

━━━━━━━━━━━━━━━━━
📊 <b>Aaj ke Key Levels — {inst['name']}</b>
━━━━━━━━━━━━━━━━━
🔴 <b>PDH (Short zone):</b> ₹{pdh:,.0f}
🟢 <b>PDL (Long zone):</b>  ₹{pdl:,.0f}
📍 <b>Current price:</b>    ₹{ltp:,.0f}
📏 <b>Range:</b>            {rng:,.0f} points

━━━━━━━━━━━━━━━━━
⚡ <b>Strategy reminder:</b>
• PDH break → RED candle → uska low break = SHORT
• PDL break → GREEN candle → uska high break = LONG
• Target = nearest swing level
• SL {inst['max_sl']} pts se bada → SKIP
• Max 2 SL per level per day

💰 Risk per trade: ₹{inst['risk']:,}
⏰ Bot har 30 min 1-min candles check karta hai
<i>PDH/PDL Strategy Bot 🤖</i>"""

def msg_signal(inst, d):
    emoji = "🔴" if d["side"] == "SHORT" else "🟢"
    action = "SHORT (SELL)" if d["side"] == "SHORT" else "LONG (BUY)"
    ctime = str(d.get("candle_time", ""))[11:16]
    return f"""{emoji} <b>SIGNAL — {action}</b>
━━━━━━━━━━━━━━━━━
<b>MCX {inst['name']}</b>  (confirmation {ctime})
━━━━━━━━━━━━━━━━━
💰 <b>Entry:</b>     ₹{d['entry']:,.0f}
🛑 <b>Stop Loss:</b> ₹{d['sl']:,.0f}  ({d['sl_pts']:.0f} pts)
🎯 <b>Target (T1):</b> ₹{d['target']:,.0f}  (swing level)
📊 <b>R:R:</b>       1:{d['rr']:.1f}
━━━━━━━━━━━━━━━━━
💰 Risk: ₹{inst['risk']:,}
📝 Paper trade note karo!
<i>PDH/PDL Strategy Bot 🤖</i>"""

def msg_skip(inst, d):
    return f"""⚠️ <b>SKIP — {inst['name']}</b>

Signal bana ({d['side']}) lekin SL bahut bada:
❌ SL: {d['sl_pts']:.0f} points
📏 Max allowed: {inst['max_sl']} points

<i>Is trade mein mat jao.</i>"""

# ─── MAIN ───────────────────────────────────────────────────────────────────
def main():
    now  = datetime.now()
    hour, minute = now.hour, now.minute
    # Morning briefing window: 9:15 IST = 3:45 UTC
    is_morning = (hour == 3 and 45 <= minute <= 59) or (hour == 4 and minute == 0)
    print(f"Running {now.strftime('%H:%M')} UTC | morning={is_morning}")

    state = load_state()
    today = now.strftime("%Y-%m-%d")

    for inst in INSTRUMENTS:
        name = inst["name"]
        print(f"\n── {name} ──")
        pdh, pdl = fetch_pdh_pdl(inst["key"])
        candles  = fetch_today_1min(inst["key"])

        if pdh is None or pdl is None:
            print(f"{name}: PDH/PDL nahi mila, skip.")
            continue

        ltp = candles[-1]["close"] if candles else pdh
        print(f"{name}: PDH={pdh} PDL={pdl} LTP={ltp} candles={len(candles)}")

        # Morning briefing (per instrument)
        morning_key = f"{name}_morning_{today}"
        if is_morning and not state.get(morning_key):
            send_telegram(msg_morning(inst, pdh, pdl, ltp))
            state[morning_key] = True

        # Signal detection — ab list aati hai (R:R filter already laga hua)
        signals = detect_signal(candles, pdh, pdl, inst["max_sl"])

        if signals:
            sent_any = False
            for sig in signals:
                # "level" = SHORT (PDH side) ya LONG (PDL side)
                level = sig["side"]

                # Is din, is instrument, is level pe ab tak kitne bheje?
                count_key = f"{name}_{today}_count_{level}"
                sent_count = state.get(count_key, 0)

                # Daily limit cross? -> us level pe ruko
                if sent_count >= MAX_SIGNALS_PER_LEVEL:
                    continue

                # Dedup: ek confirmation candle pe ek hi baar
                sig_id = f"{name}_{today}_{level}_{sig['candle_time']}"
                if state.get(sig_id):
                    continue

                # Bhejo
                send_telegram(msg_signal(inst, sig))
                state[sig_id] = True
                state[count_key] = sent_count + 1
                sent_any = True
                print(f"{name}: {level} signal bheja "
                      f"(#{sent_count+1}/{MAX_SIGNALS_PER_LEVEL}, R:R 1:{sig['rr']}).")

            if not sent_any:
                print(f"{name}: naye signal nahi (limit/dup ya R:R<{MIN_RR}).")
        else:
            # SKIP check (sirf tab jab koi valid signal nahi tha)
            skip = detect_skip(candles, pdh, pdl, inst["max_sl"])
            if skip:
                skip_id = f"{name}_{today}_skip_{skip['side']}"
                if not state.get(skip_id):
                    send_telegram(msg_skip(inst, skip))
                    state[skip_id] = True
                    print(f"{name}: SKIP bheja.")
            else:
                print(f"{name}: koi valid signal nahi (R:R<{MIN_RR} ya confirmation nahi).")

    save_state(state)
    print("\nDone!")

if __name__ == "__main__":
    main()
