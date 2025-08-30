import os, time, json, sys, traceback
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CHANNEL_ID    = os.getenv("CHANNEL_ID", "").strip()

# mindestens WEBHOOK_1 erforderlich; WEBHOOK_2 optional
WEBHOOK_1 = os.getenv("WEBHOOK_1", "").strip()
WEBHOOK_2 = os.getenv("WEBHOOK_2", "").strip()

# Exakte Taktung: alle 5 Min + 5 Sek (standard)
POLL_BASE   = int(os.getenv("POLL_BASE_SECONDS", "300"))   # 5 min
POLL_OFFSET = int(os.getenv("POLL_OFFSET_SECONDS", "5"))   # +5 sec

STATE_FILE = Path("state.json")

if not DISCORD_TOKEN or not CHANNEL_ID or not WEBHOOK_1:
    print("Bitte ENV Variablen setzen: DISCORD_TOKEN, CHANNEL_ID, WEBHOOK_1.")
    sys.exit(1)

HEADERS = {
    "Authorization": DISCORD_TOKEN,
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
}

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_id": None}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")

def fetch_latest_messages(channel_id, limit=5):
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages?limit={limit}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code == 429:
        retry = 5
        try:
            retry = r.json().get("retry_after", 5)
        except Exception:
            pass
        time.sleep(retry + 1)
        r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    data_sorted = sorted(data, key=lambda m: int(m["id"]))
    return data_sorted

def forward_to_webhooks(msg):
    payload = {
        "channel_id": msg.get("channel_id"),
        "message_id": msg.get("id"),
        "content": msg.get("content", ""),
        "timestamp": msg.get("timestamp"),
        "author": {
            "id": msg.get("author", {}).get("id"),
            "username": msg.get("author", {}).get("username"),
            "discriminator": msg.get("author", {}).get("discriminator"),
            "global_name": msg.get("author", {}).get("global_name"),
        },
        "attachments": msg.get("attachments", []),
        "embeds": msg.get("embeds", []),
    }

    urls = [WEBHOOK_1] + ([WEBHOOK_2] if WEBHOOK_2 else [])
    for idx, url in enumerate(urls, start=1):
        try:
            r = requests.post(url, json=payload, timeout=15)
            r.raise_for_status()
            print(f"[→ Webhook{idx}] {msg.get('id')} OK | {payload['content'][:80]!r}")
        except Exception as ex:
            print(f"[→ Webhook{idx}] FAIL: {ex}")

def sleep_until_next_tick():
    """
    Schläft exakt bis zum nächsten (n*POLL_BASE + POLL_OFFSET)-Zeitpunkt,
    basierend auf Unix-Zeit (Serverzeit).
    """
    now = time.time()
    period_start = (now // POLL_BASE) * POLL_BASE  # Start dieses Blocks
    next_tick = period_start + POLL_BASE + POLL_OFFSET
    # Falls wir vor dem ersten Offset im aktuellen Block sind:
    if now < period_start + POLL_OFFSET:
        next_tick = period_start + POLL_OFFSET
    sleep_s = max(0, next_tick - now)
    time.sleep(sleep_s)

def main():
    print(f"Getaktet: alle {POLL_BASE}s, jeweils +{POLL_OFFSET}s Offset (z. B. 10:00:05, 10:05:05, …)")
    state = load_state()
    last_id = state.get("last_id")

    # Auf ersten exakten Tick ausrichten
    sleep_until_next_tick()

    while True:
        try:
            msgs = fetch_latest_messages(CHANNEL_ID, limit=5)

            new_msgs = []
            for m in msgs:
                mid = m.get("id")
                if last_id is None or int(mid) > int(last_id):
                    new_msgs.append(m)

            if new_msgs:
                for m in new_msgs:  # älteste zuerst
                    forward_to_webhooks(m)
                last_id = new_msgs[-1]["id"]
                state["last_id"] = last_id
                save_state(state)
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"[{ts}] {len(new_msgs)} neue Nachricht(en) verarbeitet.")
            else:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"[{ts}] Keine neuen Nachrichten.")

        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except requests.HTTPError as http_err:
            print("[HTTP ERROR]", http_err.response.status_code, http_err.response.text[:200])
        except Exception:
            print("[ERROR]")
            traceback.print_exc()

        sleep_until_next_tick()

if __name__ == "__main__":
    main()
