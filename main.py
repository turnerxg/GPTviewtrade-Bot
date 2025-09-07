import os, asyncio, time, json, math
from datetime import datetime, timezone
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ========= ENV =========
TOKEN       = os.getenv("TOKEN")            # BotFather token
CHANNEL_ID  = os.getenv("CHANNEL_ID")       # @ChannelUsername atau chat id numeric
INTERVAL_S  = int(os.getenv("INTERVAL_S", "10"))  # kitaran semakan harga (s)
COOLDOWN_S  = int(os.getenv("COOLDOWN_S", "120")) # anti-spam alert (s)

# ZONES: JSON (lihat contoh di bawah). Jika kosong, akan guna default XAUUSD.
ZONES_JSON  = os.getenv("ZONES_JSON", "").strip()

# ========= DEFAULT ZONE (kalau ENV kosong) =========
DEFAULT_ZONES = [
    {
        "pair": "XAUUSD",
        "side": "SELL",               # SELL atau BUY
        "zone_low": 3311.0,
        "zone_high": 3319.0,
        "sl": 3320.0,
        "tp": [3269.0],               # boleh letak banyak TP: [TP1, TP2, ...]
        "symbol": "XAUUSD=X"          # Yahoo symbol utk fetch harga
    }
]

# ========= FETCH HARGA via Yahoo Finance =========
YF_SYMBOLS = {
    "XAUUSD": "XAUUSD=X",
    "BTCUSD": "BTC-USD",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X"
}

def fetch_price_yf(symbol: str) -> float | None:
    """
    Fetch last price dari Yahoo Finance quote API (tanpa API key).
    """
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        quote = data["quoteResponse"]["result"][0]
        # Cuba ambil regularMarketPrice, fallback ke post/ pre/ ask
        for k in ("regularMarketPrice", "postMarketPrice", "ask", "bid"):
            if k in quote and quote[k] is not None:
                return float(quote[k])
    except Exception as e:
        print("fetch_price_yf error:", e)
    return None

# ========= UTIL =========
def now_utc_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def load_zones():
    if ZONES_JSON:
        try:
            zones = json.loads(ZONES_JSON)
            # auto isi symbol kalau tak diberi
            for z in zones:
                if "symbol" not in z or not z["symbol"]:
                    sym = YF_SYMBOLS.get(z["pair"].upper(), None)
                    if sym: z["symbol"] = sym
            return zones
        except Exception as e:
            print("ZONES_JSON parse error:", e)
    # default
    return DEFAULT_ZONES

# simpan state untuk anti-duplikasi alert
LAST_ALERT = {}  # key: <pair>_<type>, value: timestamp

def should_alert(key: str) -> bool:
    now = time.time()
    last = LAST_ALERT.get(key, 0)
    if (now - last) >= COOLDOWN_S:
        LAST_ALERT[key] = now
        return True
    return False

# ========= BOT HANDLERS =========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "GPTviewtrade ADV bot is alive ✅\n"
        "Commands: /test, /status\n"
        "Saya akan scan zones setiap "
        f"{INTERVAL_S}s dan alert ke channel."
    )

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_channel(context, "🔔 TEST SIGNAL 🔔\nIni mesej ujian dari bot.")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    zones = load_zones()
    lines = ["⚙️ <b>Status</b>",
             f"Time: {now_utc_iso()}",
             f"Interval: {INTERVAL_S}s  |  Cooldown: {COOLDOWN_S}s",
             f"Channel: <code>{CHANNEL_ID}</code>",
             f"Zones: {len(zones)}"]
    for i, z in enumerate(zones, 1):
        lines.append(
            f"\n<b>{i}. {z['pair']} {z['side']}</b>\n"
            f"Zone: {z['zone_low']} – {z['zone_high']}\n"
            f"SL: {z['sl']}  |  TP: {', '.join(map(str, z['tp']))}\n"
            f"Feed: <code>{z.get('symbol','?')}</code>"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def send_channel(context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text,
                                       parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        print("send_channel error:", e)

# ========= CORE LOGIC =========
def check_events_for_zone(pair: str, side: str, price: float, zl: float, zh: float, sl: float, tps: list[float]):
    """
    Return list of (event_type, message) untuk dihantar.
    Event_type contoh: enter, sl, tp1, tp2, exit
    """
    evts = []
    in_zone = (zl <= price <= zh)
    key_enter = f"{pair}_enter"
    key_exit  = f"{pair}_exit"
    key_sl    = f"{pair}_sl"

    # ENTER zone
    if in_zone and should_alert(key_enter):
        evts.append(("enter",
                     f"⚠️ <b>{pair}</b> price <b>{price}</b> MASUK <b>{side} ZONE</b> "
                     f"({zl}–{zh})\nSL: <code>{sl}</code> | TP: <code>{', '.join(map(str,tps))}</code>"))

    # EXIT zone
    if not in_zone and should_alert(key_exit):
        evts.append(("exit", f"ℹ️ <b>{pair}</b> price {price} KELUAR dari zone ({zl}–{zh})."))

    # SL & TPs (ikut side)
    if side.upper() == "SELL":
        # SL (break atas)
        if price >= sl and should_alert(key_sl):
            evts.append(("sl", f"🟥 <b>{pair}</b> SL HIT at <b>{price}</b> (SL: {sl})"))
        # TP (turun)
        for i, tp in enumerate(tps, 1):
            key_tp = f"{pair}_tp{i}"
            if price <= tp and should_alert(key_tp):
                evts.append((f"tp{i}", f"🟩 <b>{pair}</b> TP{i} HIT at <b>{price}</b> (TP{i}: {tp})"))
    else:  # BUY
        if price <= sl and should_alert(key_sl):
            evts.append(("sl", f"🟥 <b>{pair}</b> SL HIT at <b>{price}</b> (SL: {sl})"))
        for i, tp in enumerate(tps, 1):
            key_tp = f"{pair}_tp{i}"
            if price >= tp and should_alert(key_tp):
                evts.append((f"tp{i}", f"🟩 <b>{pair}</b> TP{i} HIT at <b>{price}</b> (TP{i}: {tp})"))

    return evts

async def job_scan(context: ContextTypes.DEFAULT_TYPE):
    zones = load_zones()
    for z in zones:
        pair   = z["pair"].upper()
        side   = z["side"].upper()
        zl, zh = float(z["zone_low"]), float(z["zone_high"])
        sl     = float(z["sl"])
        tps    = [float(x) for x in z.get("tp", [])]

        # tentukan symbol feed
        symbol = z.get("symbol") or YF_SYMBOLS.get(pair)
        if not symbol:
            print(f"[{pair}] missing feed symbol")
            continue

        price = fetch_price_yf(symbol)
        if price is None or math.isnan(price):
            print(f"[{pair}] price fetch failed")
            continue

        events = check_events_for_zone(pair, side, price, zl, zh, sl, tps)
        for _, msg in events:
            await send_channel(context, msg)

async def job_heartbeat(context: ContextTypes.DEFAULT_TYPE):
    await send_channel(context, f"✅ Bot running… {now_utc_iso()} (interval {INTERVAL_S}s)")

async def main():
    if not TOKEN or not CHANNEL_ID:
        raise RuntimeError("Missing TOKEN or CHANNEL_ID env")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("test",    cmd_test))
    app.add_handler(CommandHandler("status",  cmd_status))

    jq = app.job_queue
    jq.run_repeating(job_scan, interval=INTERVAL_S, first=5)
    jq.run_repeating(job_heartbeat, interval=3600, first=10)  # heartbeat sejam sekali

    print("Starting bot polling…")
    await app.initialize()
    await app.start()
    try:
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
