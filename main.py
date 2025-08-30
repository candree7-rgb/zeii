import os, time, json, sys, traceback
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
ZAPIER_WEBHOOK = os.getenv("ZAPIER_WEBHOOK", "").strip()
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "305"))

STATE_FILE = Path("state.json")

if not DISCORD_TOKEN or not CHANNEL_ID or not ZAPIER_WEBHOOK:
    print("Bitte ENV Variablen setzen: DISCORD_TOKEN, CHANNEL_ID, ZAPIER_WEBHOOK.")
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
        try:
            retry = r.json().get("retry_after", 5)
        except Exception:
            retry = 5
        time.sleep(retry + 1)
        r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    data_sorted = sorted(data, key=lambda m: int(m["id"]))
    return data_sorted

def forward_to_zapier(msg):
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
    requests.post(ZAPIER_WEBHOOK, json=payload, timeout=15)
    print(f"[→ Zapier] {msg.get('id')} | {payload['content'][:100]!r}")

def main():
    print(f"Polling Channel {CHANNEL_ID} alle {POLL_INTERVAL}s …")
    state = load_state()
    last_id = state.get("last_id")

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
                    forward_to_zapier(m)
                last_id = new_msgs[-1]["id"]
                state["last_id"] = last_id
                save_state(state)
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Keine neuen Nachrichten.")

        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except requests.HTTPError as http_err:
            print("[HTTP ERROR]", http_err.response.status_code, http_err.response.text[:200])
        except Exception:
            print("[ERROR]")
            traceback.print_exc()

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
