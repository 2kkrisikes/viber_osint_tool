"""Flask + Cloudflare Quick Tunnel + Viber webhook and contact-message CLI.

Requires: pip install flask requests; cloudflared executable on PATH.
Uses existing config.json with {"token": "...", "uid": "..."}.
"""
import argparse
import hashlib
import hmac
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import requests
from flask import Flask, request
from werkzeug.serving import make_server

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
PORT = 5000
CONFIG = {}
app = Flask(__name__)


@app.get("/")
def home():
    return "Webhook server is running!", 200


@app.post("/webhook")
def webhook():
    body = request.get_data()
    signature = request.headers.get("X-Viber-Content-Signature", "")
    expected = hmac.new(CONFIG["token"].encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return "Invalid signature", 403
    event = request.get_json(silent=True)
    if not isinstance(event, dict):
        return "Invalid JSON", 400
    print("Viber event:", event.get("event"), flush=True)
    return "", 200


class FlaskServer(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.server = make_server("127.0.0.1", PORT, app)

    def run(self):
        self.server.serve_forever()

    def stop(self):
        self.server.shutdown()


def start_cloudflare(timeout=45):
    if not shutil.which("cloudflared"):
        raise RuntimeError("cloudflared not found on PATH. Install it and reopen the terminal.")
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{PORT}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    lines = queue.Queue()

    def reader():
        for line in proc.stdout:
            lines.put(line)

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + timeout
    pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=0.5)
        except queue.Empty:
            if proc.poll() is not None:
                raise RuntimeError(f"cloudflared exited with code {proc.returncode}")
            continue
        match = pattern.search(line)
        if match:
            return proc, match.group(0)
        if "ERR" in line or "error" in line.lower():
            print("Cloudflare:", line.strip(), flush=True)
    proc.terminate()
    raise TimeoutError("Cloudflare did not provide a Quick Tunnel URL within 45 seconds")


def api_post(endpoint, payload):
    response = requests.post(
        f"https://chatapi.viber.com/pa/{endpoint}", json=payload, timeout=20
    )
    response.raise_for_status()
    data = response.json()
    return data


def set_webhook(url):
    data = api_post("set_webhook", {
        "auth_token": CONFIG["token"],
        "url": url,
        "event_types": ["failed"],
        "send_name": False,
        "send_photo": False,
    })
    if data.get("status") != 0:
        raise RuntimeError(f"Viber webhook setup failed: {data}")
    print("Webhook configured:", url)


def get_account_info():
    data = api_post("get_account_info", {"auth_token": CONFIG["token"]})
    if data.get("status") != 0:
        raise RuntimeError(f"Viber account lookup failed: {data}")
    members = data.get("members", [])
    if not members:
        raise RuntimeError("Viber account has no members to use as sender")
    return members[0]["id"]


def send_contact_message(phone):
    payload = {
        "auth_token": CONFIG["token"],
        "from": CONFIG["uid"],
        "type": "contact",
        "contact": {"name": "ITT Nyisd meg a profilt!", "phone_number": phone},
    }
    data = api_post("post", payload)
    if data.get("status") == 0:
        print(f"Contact message accepted for {phone}; token={data.get('message_token')}")
        return True
    print(f"Contact message failed for {phone}: {data}")
    return False


def load_config():
    global CONFIG
    with CONFIG_FILE.open(encoding="utf-8") as f:
        CONFIG = json.load(f)
    if not CONFIG.get("token"):
        raise RuntimeError("Missing Viber token in config.json")
    if not CONFIG.get("uid"):
        CONFIG["uid"] = get_account_info()
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(CONFIG, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Run Flask, Cloudflare and Viber webhook")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-p", "--phone", help="Send a contact card containing this phone number")
    group.add_argument("-l", "--list", help="Text file of phone numbers, one per line")
    args = parser.parse_args()
    load_config()
    server = FlaskServer()
    server.start()
    proc = None
    try:
        print(f"Flask started on http://127.0.0.1:{PORT}")
        proc, cloudflare_url = start_cloudflare()
        webhook_url = f"{cloudflare_url}/webhook"
        print("Cloudflare URL:", cloudflare_url)
        # A Quick Tunnel URL appearing in the log may precede edge readiness.
        # Retry transient setup failures briefly before giving up.
        for attempt in range(5):
            try:
                set_webhook(webhook_url)
                break
            except (requests.RequestException, RuntimeError):
                if attempt == 4:
                    raise
                time.sleep(3)
        if args.phone:
            send_contact_message(args.phone)
        elif args.list:
            with open(args.list, encoding="utf-8") as f:
                for phone in map(str.strip, f):
                    if phone:
                        send_contact_message(phone)
        print("Server is running. Press Ctrl+C to stop.")
        while True:
            if proc.poll() is not None:
                raise RuntimeError("Cloudflare tunnel unexpectedly stopped")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        server.stop()
        server.join(timeout=5)


if __name__ == "__main__":
    main()
