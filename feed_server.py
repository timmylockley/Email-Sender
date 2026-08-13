#!/usr/bin/env python3
"""
feed_server.py — Headless Feed Monitor Server
==============================================
Runs as a standalone process on any machine (VPS, Raspberry Pi, etc.).
Polls RSS/Atom feeds on configurable intervals and emails on new items.

Exposes a simple HTTP API so the desktop app can manage it remotely:
  GET  /status        — uptime, version, last-check summary
  GET  /feeds         — current feeds list
  POST /feeds         — replace feeds list (JSON body)
  GET  /smtp          — current SMTP config (password masked)
  POST /smtp          — replace SMTP config (JSON body)
  GET  /logs          — last N log lines
  POST /check         — trigger immediate check of all feeds

Authentication: every request must include the header  X-API-Key: <key>
Set the key via --api-key argument or API_KEY environment variable.

Usage:
  python feed_server.py --api-key mysecretkey --port 8642
  python feed_server.py --api-key mysecretkey --port 8642 --host 0.0.0.0

Config files (created automatically in the working directory):
  feeds_config.json   — feed list (same format as desktop app)
  smtp_config.json    — SMTP credentials
  seen_entries.json   — tracks already-seen feed item IDs
"""

import argparse
import json
import logging
import os
import smtplib
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, HTTPServer

# ── File paths ──────────────────────────────────────────────────────────────
FEEDS_FILE = "feeds_config.json"
SMTP_FILE  = "smtp_config.json"
SEEN_FILE  = "seen_entries.json"

SERVER_VERSION = "1.0.0"

# ── In-memory log ring buffer ────────────────────────────────────────────────
_log_buffer: deque = deque(maxlen=500)

class _BufferHandler(logging.Handler):
    def emit(self, record):
        _log_buffer.append(self.format(record))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        _BufferHandler(),
    ],
)
log = logging.getLogger("feed_server")

# ── Locks ────────────────────────────────────────────────────────────────────
_feeds_lock = threading.Lock()
_smtp_lock  = threading.Lock()
_seen_lock  = threading.Lock()

# ── State ────────────────────────────────────────────────────────────────────
_start_time = time.time()
_api_key: str = ""


# ════════════════════════════════════════════════════════════════════════════
# Persistence helpers
# ════════════════════════════════════════════════════════════════════════════

def _read_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"Could not read {path}: {e}")
    return default


def _write_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        log.error(f"Could not write {path}: {e}")


def load_feeds():
    with _feeds_lock:
        return _read_json(FEEDS_FILE, [])


def save_feeds(feeds):
    with _feeds_lock:
        _write_json(FEEDS_FILE, feeds)


def load_smtp():
    with _smtp_lock:
        return _read_json(SMTP_FILE, {})


def save_smtp(smtp):
    with _smtp_lock:
        _write_json(SMTP_FILE, smtp)


def load_seen():
    with _seen_lock:
        return _read_json(SEEN_FILE, {})


def save_seen(seen):
    with _seen_lock:
        _write_json(SEEN_FILE, seen)


# ════════════════════════════════════════════════════════════════════════════
# RSS / Atom fetching
# ════════════════════════════════════════════════════════════════════════════

def fetch_rss_items(url: str) -> list:
    """Fetch an RSS/Atom feed and return a list of item dicts."""
    req = urllib.request.Request(url, headers={"User-Agent": "FeedServer/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()

    root = ET.fromstring(data)
    items = []
    tag = root.tag

    if "feed" in tag.lower():
        # Atom
        atom_ns = tag[1:tag.index("}")] if "}" in tag else ""
        p = f"{{{atom_ns}}}" if atom_ns else ""
        for entry in root.findall(f"{p}entry"):
            title_el     = entry.find(f"{p}title")
            link_el      = entry.find(f"{p}link")
            pub_el       = entry.find(f"{p}published")
            if pub_el is None:
                pub_el = entry.find(f"{p}updated")
            summary_el   = entry.find(f"{p}summary")
            if summary_el is None:
                summary_el = entry.find(f"{p}content")
            id_el        = entry.find(f"{p}id")

            link = ""
            if link_el is not None:
                link = link_el.get("href", link_el.text or "")

            entry_id = (id_el.text if id_el is not None else None) or link
            items.append({
                "id":        entry_id,
                "title":     title_el.text   if title_el   is not None else "No title",
                "link":      link,
                "published": pub_el.text     if pub_el     is not None else "",
                "summary":   summary_el.text if summary_el is not None else "",
            })
    else:
        # RSS 2.0
        channel = root.find("channel")
        if channel is None:
            channel = root
        for item in channel.findall("item"):
            title_el = item.find("title")
            link_el  = item.find("link")
            pub_el   = item.find("pubDate")
            desc_el  = item.find("description")
            guid_el  = item.find("guid")

            link     = link_el.text  if link_el  is not None else ""
            entry_id = (guid_el.text if guid_el  is not None else None) or link
            items.append({
                "id":        entry_id,
                "title":     title_el.text if title_el is not None else "No title",
                "link":      link,
                "published": pub_el.text   if pub_el  is not None else "",
                "summary":   desc_el.text  if desc_el is not None else "",
            })

    return items


# ════════════════════════════════════════════════════════════════════════════
# SMTP email sending
# ════════════════════════════════════════════════════════════════════════════

def build_smtp_connection(smtp_cfg: dict):
    host     = smtp_cfg.get("host", "").strip()
    port     = int(smtp_cfg.get("port", 587))
    user     = smtp_cfg.get("user", "").strip()
    password = smtp_cfg.get("password", "").strip()
    use_tls  = smtp_cfg.get("tls", True)

    if not host or not user or not password:
        raise ValueError("SMTP config incomplete — need host, user, and password.")

    if use_tls:
        server = smtplib.SMTP(host, port, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
    else:
        server = smtplib.SMTP_SSL(host, port, timeout=15)

    server.login(user, password)
    return server, user


def send_feed_email(smtp_cfg: dict, feed: dict, item: dict) -> bool:
    def repl(template: str) -> str:
        return (template
                .replace("{title}",     item.get("title",     ""))
                .replace("{link}",      item.get("link",      ""))
                .replace("{published}", item.get("published", ""))
                .replace("{summary}",   item.get("summary",   "")))

    subject = repl(feed.get("subject", "New feed item: {title}"))
    body    = repl(feed.get("text",    "New item:\n\nTitle: {title}\nLink: {link}"))

    try:
        server, from_addr = build_smtp_connection(smtp_cfg)
        msg = EmailMessage()
        msg["From"]    = from_addr
        msg["To"]      = feed["to"]
        msg["Subject"] = subject
        msg.set_content(body)
        server.send_message(msg)
        server.quit()
        log.info(f"Email sent to {feed['to']!r} — {subject!r}")
        return True
    except Exception as e:
        log.error(f"Email send failed: {e}")
        return False


# ════════════════════════════════════════════════════════════════════════════
# Feed checking logic
# ════════════════════════════════════════════════════════════════════════════

def check_single_feed(feed: dict, smtp_cfg: dict, seen: dict) -> dict:
    """
    Check one feed. Mutates `seen` and `feed` (last_checked / next_check).
    Returns the updated `seen` dict.
    """
    url = feed["source"]
    log.info(f"Checking feed: {url}")

    try:
        items = fetch_rss_items(url)
    except Exception as e:
        log.error(f"Fetch error for {url}: {e}")
        feed["last_checked"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        feed["next_check"]   = time.time() + feed.get("interval", 15) * 60
        return seen

    seen_key = url
    if seen_key not in seen:
        # First time — record all current IDs, send nothing
        seen[seen_key] = [item["id"] for item in items]
        log.info(f"First check for {url} — recorded {len(items)} existing item(s), no emails sent.")
    else:
        known  = set(seen[seen_key])
        new_items = [i for i in items if i["id"] not in known]
        log.info(f"Found {len(new_items)} new item(s) for {url}")
        for item in new_items:
            if not smtp_cfg:
                log.warning("No SMTP config — will retry this item on the next check.")
                continue

            sent = send_feed_email(smtp_cfg, feed, item)
            if sent:
                seen[seen_key].append(item["id"])
            else:
                log.warning(
                    f"Keeping item {item.get('id', '')!r} unseen so the email will be retried."
                )

    feed["last_checked"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    feed["next_check"]   = time.time() + feed.get("interval", 15) * 60
    return seen


def check_all_feeds():
    """Load feeds + SMTP from disk, check all due feeds, persist results."""
    feeds    = load_feeds()
    smtp_cfg = load_smtp()
    seen     = load_seen()
    now      = time.time()
    changed  = False

    for feed in feeds:
        if now >= feed.get("next_check", 0):
            seen    = check_single_feed(feed, smtp_cfg, seen)
            changed = True

    if changed:
        save_feeds(feeds)
        save_seen(seen)


# ════════════════════════════════════════════════════════════════════════════
# Background polling thread
# ════════════════════════════════════════════════════════════════════════════

def polling_loop():
    log.info("Polling thread started.")
    while True:
        try:
            check_all_feeds()
        except Exception:
            log.error(f"Unhandled error in polling loop:\n{traceback.format_exc()}")
        time.sleep(30)


# ════════════════════════════════════════════════════════════════════════════
# HTTP API
# ════════════════════════════════════════════════════════════════════════════

def _json_response(handler, code: int, data):
    body = json.dumps(data, indent=2).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode())


class APIHandler(BaseHTTPRequestHandler):

    # Silence default request logging (we use our own)
    def log_message(self, fmt, *args):
        log.debug(f"HTTP {self.address_string()} — {fmt % args}")

    def _auth(self) -> bool:
        key = self.headers.get("X-API-Key", "")
        if key != _api_key:
            _json_response(self, 401, {"error": "Unauthorized — invalid or missing X-API-Key header."})
            return False
        return True

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        if not self._auth():
            return

        path = self.path.split("?")[0].rstrip("/")

        if path == "/status":
            uptime_s = int(time.time() - _start_time)
            h, rem   = divmod(uptime_s, 3600)
            m, s     = divmod(rem, 60)
            feeds    = load_feeds()
            _json_response(self, 200, {
                "version":    SERVER_VERSION,
                "uptime":     f"{h}h {m}m {s}s",
                "uptime_sec": uptime_s,
                "feed_count": len(feeds),
                "feeds_summary": [
                    {
                        "source":       f["source"],
                        "to":           f["to"],
                        "last_checked": f.get("last_checked") or "Never",
                    }
                    for f in feeds
                ],
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        elif path == "/feeds":
            _json_response(self, 200, load_feeds())

        elif path == "/smtp":
            cfg  = load_smtp()
            safe = {k: ("*" * 8 if k == "password" else v) for k, v in cfg.items()}
            _json_response(self, 200, safe)

        elif path == "/logs":
            _json_response(self, 200, {"logs": list(_log_buffer)})

        else:
            _json_response(self, 404, {"error": f"Unknown endpoint: {path}"})

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self):
        if not self._auth():
            return

        path = self.path.split("?")[0].rstrip("/")

        if path == "/feeds":
            try:
                data = _read_body(self)
                if not isinstance(data, list):
                    _json_response(self, 400, {"error": "Body must be a JSON array of feed objects."})
                    return
                # Ensure required scheduling keys are present
                for feed in data:
                    feed.setdefault("next_check", 0)
                    feed.setdefault("last_checked", None)
                save_feeds(data)
                log.info(f"Feeds updated via API — {len(data)} feed(s).")
                _json_response(self, 200, {"ok": True, "count": len(data)})
            except Exception as e:
                _json_response(self, 400, {"error": str(e)})

        elif path == "/smtp":
            try:
                data = _read_body(self)
                required = {"host", "port", "user", "password"}
                missing  = required - set(data.keys())
                if missing:
                    _json_response(self, 400, {"error": f"Missing fields: {missing}"})
                    return
                save_smtp(data)
                log.info(f"SMTP config updated via API — host={data['host']}, user={data['user']}")
                _json_response(self, 200, {"ok": True})
            except Exception as e:
                _json_response(self, 400, {"error": str(e)})

        elif path == "/check":
            log.info("Immediate feed check triggered via API.")
            def _run():
                feeds    = load_feeds()
                smtp_cfg = load_smtp()
                seen     = load_seen()
                for feed in feeds:
                    feed["next_check"] = 0   # force due
                    seen = check_single_feed(feed, smtp_cfg, seen)
                save_feeds(feeds)
                save_seen(seen)
                log.info("Immediate feed check complete.")
            threading.Thread(target=_run, daemon=True).start()
            _json_response(self, 200, {"ok": True, "message": "Feed check started."})

        else:
            _json_response(self, 404, {"error": f"Unknown endpoint: {path}"})


# ════════════════════════════════════════════════════════════════════════════
# Entry point
# ════════════════════════════════════════════════════════════════════════════

def main():
    global _api_key

    parser = argparse.ArgumentParser(description="Headless Feed Monitor Server")
    parser.add_argument("--host",    default="0.0.0.0",   help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port",    default=8642,  type=int, help="Port to listen on (default: 8642)")
    parser.add_argument("--api-key", default="",           help="API key for authentication")
    args = parser.parse_args()

    _api_key = args.api_key or os.environ.get("API_KEY", "")
    if not _api_key:
        print("ERROR: No API key set. Use --api-key <key> or set the API_KEY environment variable.")
        sys.exit(1)

    # Write initial empty config files if they don't exist
    if not os.path.exists(FEEDS_FILE):
        save_feeds([])
    if not os.path.exists(SMTP_FILE):
        save_smtp({})
    if not os.path.exists(SEEN_FILE):
        save_seen({})

    # Start polling thread
    t = threading.Thread(target=polling_loop, daemon=True)
    t.start()

    # Start HTTP server
    httpd = HTTPServer((args.host, args.port), APIHandler)
    log.info(f"Feed Server v{SERVER_VERSION} listening on {args.host}:{args.port}")
    log.info(f"API key set: {'yes' if _api_key else 'NO — unauthenticated!'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("Server stopped.")


if __name__ == "__main__":
    main()
