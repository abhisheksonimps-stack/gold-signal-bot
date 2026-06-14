"""
PDH/PDL Gold Trading Signal Bot
Roz automatically:
1. Upstox se PDH/PDL fetch karta hai
2. Signal detect karta hai
3. Telegram pe message bhejta hai
"""

import os
import requests
from datetime import datetime, timedelta

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1766130094")
UPSTOX_TOKEN     = os.environ.get("UPSTOX_TOKEN", "")
INSTRUMENT_KEY   = os.environ.get("INSTRUMENT_KEY", "MCX_FO|466583")
RISK_PER_TRADE   = int(os.environ.get("RISK_PER_TRADE", "5000"))
MAX_SL_POINTS    = int(os.environ.get("MAX_SL_POINTS", "80"))

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────
def send_telegram(message):
    if not TELEGRAM_TOKEN:
        print("Telegram token nahi hai!")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    r = requests.post(url, data=data, timeout=10)
    if r.status_code == 200:
        print("✅ Telegram message sent!")
        return True
    print(f"❌ Telegram error: {r.text}")
    return False

# ─── UPSTOX API ───────────────────────────────────────────────────────────────
def get_upstox_headers():
    return {
        "Authorization": f"Bearer {UPSTOX_TOKEN}",
        "Accept": "application/json"
    }

def fetch_pdh_pdl():
    if not UPSTOX_TOKEN:
        return None, None
    yday = datetime.now() - timedelta(days=1)
    while yday.weekday() >= 5:
        yday -= timedelta(days=1)
    date_str = yday.strftime("%Y-%m-%d")
    url = f"https://api.upstox.com/v2/historical-candle/{requests.utils.quote(INSTRUMENT_KEY, safe='')}/day/{date_str}/{date_str}"
    try:
        r = requests.get(url, headers=get_upstox_headers(), timeout=10)
        data = r.json()
        if data.get("data") and data["data"].get("candles"):
            candle = data["data"]["candles"][0]
            pdh = float(candle[2])
            pdl = float(candle[3])
            print(f"PDH: {pdh} | PDL: {pdl}")
            return pdh, pdl
    except Exception as e:
        print(f"PDH/PDL fetch error: {e}")
    return None, None

def fetch_ltp():
    if not UPSTOX_TOKEN:
        return None
    url = f"https://api.upstox.com/v2/market-quote/ltp?instrument_key={requests.utils.quote(INSTRUMENT_KEY, safe='')}"
    try:
        r = requests.get(url, headers=get_upstox_headers(), timeout=10)
        data = r.json()
        if data.get("data"):
            for k, v in data["data"].items():
                ltp = float(v.get("last_price", 0))
                if ltp > 0:
                    return ltp
    except Exception as e:
        print(f"LTP fetch error: {e}")
    return None

# ─── SIGNAL DETECTION ─────────────────────────────────────────────────────────
def detect_signal(pdh, pdl, ltp):
    if not pdh or not pdl or not ltp:
        return None, {}
    day_range = pdh - pdl
    if ltp > pdh:
        poke   = ltp - pdh
        entry  = round(pdh + poke * 0.4, 2)
        sl     = round(ltp + day_range * 0.04, 2)
        sl_pts = round(sl - entry, 2)
        t1     = pdl
        rr     = round((entry - t1) / sl_pts, 2) if sl_pts > 0 else 0
        qty    = max(1, int(RISK_PER_TRADE / sl_pts)) if sl_pts > 0 else 1
        valid  = sl_pts < MAX_SL_POINTS
        return ("SHORT" if valid else "SKIP"), {
            "side": "SHORT", "entry": entry, "sl": sl,
            "sl_pts": sl_pts, "target": t1, "rr": rr,
            "qty": qty, "valid": valid, "ltp": ltp, "pdh": pdh, "pdl": pdl
        }
    elif ltp < pdl:
        dip    = pdl - ltp
        entry  = round(pdl - dip * 0.4, 2)
        sl     = round(ltp - day_range * 0.04, 2)
        sl_pts = round(entry - sl, 2)
        t1     = pdh
        rr     = round((t1 - entry) / sl_pts, 2) if sl_pts > 0 else 0
        qty    = max(1, int(RISK_PER_TRADE / sl_pts)) if sl_pts > 0 else 1
        valid  = sl_pts < MAX_SL_POINTS
        return ("LONG" if valid else "SKIP"), {
            "side": "LONG", "entry": entry, "sl": sl,
            "sl_pts": sl_pts, "target": t1, "rr": rr,
            "qty": qty, "valid": valid, "ltp": ltp, "pdh": pdh, "pdl": pdl
        }
    return "WAIT", {"ltp": ltp, "pdh": pdh, "pdl": pdl}

# ─── MESSAGE FORMAT ───────────────────────────────────────────────────────────
def format_morning_message(pdh, pdl, ltp):
    now = datetime.now().strftime("%d %b %Y %H:%M")
    range_pts = pdh - pdl
    msg = f"""🌅 <b>Good Morning Abhishek!</b>
📅 {now} IST | MCX Gold

━━━━━━━━━━━━━━━━━
📊 <b>Aaj ke Key Levels</b>
━━━━━━━━━━━━━━━━━
🔴 <b>PDH (Short zone):</b> ₹{pdh:,.0f}
🟢 <b>PDL (Long zone):</b>  ₹{pdl:,.0f}
📍 <b>Current LTP:</b>      ₹{ltp:,.0f}
📏 <b>Range:</b>            {range_pts:,.0f} points

━━━━━━━━━━━━━━━━━
⚡ <b>Strategy:</b>
• Price ₹{pdh:,.0f} ke UPAR → SHORT wait karo
• Price ₹{pdl:,.0f} ke NEECHE → LONG wait karo
• SL {MAX_SL_POINTS} pts se zyada → SKIP karo
• Max 2 SL per level per day

━━━━━━━━━━━━━━━━━
💰 Risk per trade: ₹{RISK_PER_TRADE:,}
⏰ Bot har 30 min check karta hai
━━━━━━━━━━━━━━━━━
<i>PDH/PDL Auto Signal Bot 🤖</i>"""
    return msg

def format_signal_message(signal, data):
    if signal == "SHORT":
        emoji = "🔴"
        action = "SHORT (SELL)"
    elif signal == "LONG":
        emoji = "🟢"
        action = "LONG (BUY)"
    elif signal == "SKIP":
        return f"""⚠️ <b>Signal mila lekin SKIP karo!</b>

❌ SL bahut bada: {data.get('sl_pts', 0):.0f} points
📏 Max allowed: {MAX_SL_POINTS} points
📍 LTP: ₹{data.get('ltp', 0):,.0f}

<i>Is trade mein mat jao!</i>"""

    return f"""{emoji} <b>SIGNAL ALERT! — {action}</b>
━━━━━━━━━━━━━━━━━
<b>MCX GOLD FUTURES</b>
━━━━━━━━━━━━━━━━━
💰 <b>Entry:</b>    ₹{data['entry']:,.0f}
🛑 <b>Stop Loss:</b> ₹{data['sl']:,.0f} ({data['sl_pts']:.0f} pts)
🎯 <b>Target:</b>   ₹{data['target']:,.0f}
📊 <b>R:R:</b>      1:{data['rr']:.1f}
📦 <b>Qty:</b>      {data['qty']} lot
━━━━━━━━━━━━━━━━━
📍 LTP: ₹{data['ltp']:,.0f}
📍 PDH: ₹{data['pdh']:,.0f}
📍 PDL: ₹{data['pdl']:,.0f}
━━━━━━━━━━━━━━━━━
⚡ Confirmation candle wait karo!
<i>PDH/PDL Auto Signal Bot 🤖</i>"""

def format_wait_message(pdh, pdl, ltp):
    return f"""⏳ <b>Status Update — MCX Gold</b>

📍 LTP: ₹{ltp:,.0f}
🔴 PDH: ₹{pdh:,.0f}  {'← Price yahaan hai! Alert!' if ltp > pdh * 0.999 else ''}
🟢 PDL: ₹{pdl:,.0f}  {'← Price yahaan hai! Alert!' if ltp < pdl * 1.001 else ''}

⏰ Price abhi beech mein hai — wait karo
<i>Next check 30 min mein</i>"""

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    now  = datetime.now()
    hour = now.hour
    min_ = now.minute
    print(f"Running at {now.strftime('%H:%M:%S')} UTC (IST = UTC+5:30)")

    # PDH/PDL fetch
    pdh, pdl = fetch_pdh_pdl()
    if not pdh or not pdl:
        pdh, pdl = 151053.0, 149498.0  # fallback from last run
        print(f"Fallback values: PDH={pdh} PDL={pdl}")

    # LTP fetch
    ltp = fetch_ltp()
    if not ltp:
        ltp = 150675.0
        print(f"Fallback LTP: {ltp}")

    print(f"PDH: {pdh} | PDL: {pdl} | LTP: {ltp}")

    # Signal detect
    signal, data = detect_signal(pdh, pdl, ltp)
    print(f"Signal: {signal}")

    # Morning briefing — 9:15 AM IST = 3:45 UTC
    is_morning = (hour == 3 and 45 <= min_ <= 59) or (hour == 4 and min_ == 0)

    if signal in ["SHORT", "LONG", "SKIP"]:
        # Signal aaya — turant bhejo!
        msg = format_signal_message(signal, data)
        send_telegram(msg)
    elif is_morning:
        # Morning briefing
        msg = format_morning_message(pdh, pdl, ltp)
        send_telegram(msg)
    else:
        # Har run pe status update bhejo
        msg = format_wait_message(pdh, pdl, ltp)
        send_telegram(msg)

    print("Done!")

if __name__ == "__main__":
    main()
