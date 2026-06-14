# PDH/PDL Gold Signal Bot 🥇

Fully automatic trading signal bot — GitHub Actions se roz automatically run hota hai aur Telegram pe signal bhejta hai.

## Kya karta hai?
- Roz 9:15 AM IST pe morning briefing bhejta hai (PDH/PDL levels)
- Har 30 minute mein signal check karta hai
- SHORT/LONG signal aane pe turant Telegram message
- SKIP signal bhi bhejta hai (jab SL bada ho)

## Setup — 5 minute

### Step 1 — GitHub repo banao
1. github.com pe login karo
2. New repository banao — naam: `gold-signal-bot`
3. Private rakho

### Step 2 — Files upload karo
Yeh files upload karo:
- `signal.py`
- `requirements.txt`
- `.github/workflows/signal.yml` (folder structure maintain karo)

### Step 3 — Secrets set karo
Repository → Settings → Secrets and variables → Actions → New repository secret

Yeh secrets daalo:
| Secret Name | Value |
|-------------|-------|
| `TELEGRAM_TOKEN` | Tumhara Telegram bot token |
| `TELEGRAM_CHAT_ID` | `1766130094` |
| `UPSTOX_TOKEN` | Upstox access token (roz update karna hoga) |
| `INSTRUMENT_KEY` | `MCX_FO|466583` |
| `RISK_PER_TRADE` | `5000` |
| `MAX_SL_POINTS` | `80` |

### Step 4 — Test karo
Actions tab → "PDH PDL Gold Signal Bot" → "Run workflow" → Run

Telegram pe message aayega!

## Roz kya karna hoga?
Sirf ek kaam — **Upstox token update karna** (daily expire hota hai):
1. Upstox Apps pe jaao → PDH Trading → token copy karo
2. GitHub Secrets mein `UPSTOX_TOKEN` update karo

Bas! Baaki sab automatic. 🎯

## Telegram Messages
- 🌅 Morning briefing (9:15 AM)
- 🔴 SHORT signal
- 🟢 LONG signal  
- ⚠️ SKIP signal (SL bada)
- ⏳ Wait (price beech mein)
