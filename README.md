# GPTviewtrade ADV (Railway Ready)

## ENV yang WAJIB
- TOKEN       = <token BotFather>
- CHANNEL_ID  = @YourChannelUsername  (public) ATAU numeric chat id (private)

## ENV pilihan
- INTERVAL_S  = 10        # kitaran scan (s)
- COOLDOWN_S  = 120       # anti-spam alert (s)
- ZONES_JSON  = JSON config zone (contoh di bawah)

## Contoh ZONES_JSON
[
  {
    "pair": "XAUUSD",
    "side": "SELL",
    "zone_low": 3311,
    "zone_high": 3319,
    "sl": 3320,
    "tp": [3269, 3255]          // TP1, TP2
  },
  {
    "pair": "BTCUSD",
    "side": "BUY",
    "zone_low": 57000,
    "zone_high": 57400,
    "sl": 56500,
    "tp": [58500, 60000]
  }
]

---

### Nota Penting:
- `symbol` untuk feed akan diisi automatik (XAUUSD=X, BTC-USD, EURUSD=X, dll). Boleh override dengan `symbol` sendiri.
- Bot guna Yahoo Finance public quote API (tanpa API key).
- Pastikan bot **Admin** dalam channel Telegram.
- Command Telegram yang tersedia: `/start`, `/status`, `/test`
