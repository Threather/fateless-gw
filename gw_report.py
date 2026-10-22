"""Fateless daily Telegram reminder.

Runs once a day at 12:00 UTC (7PM Cambodia) on PythonAnywhere.
Preview without sending:  python gw_report.py --test
"""
import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

# --- Config ---
BOT_TOKEN = "YOUR_TOKEN_HERE"
CHAT_ID = "-1003652956919"          # Fateless supergroup
ADMIN_CHAT_ID = "924385557"         # Threather DM, for error alerts
IMAGE_BASE = "https://raw.githubusercontent.com/Threather/fateless-gw/main/assets"

KH = timezone(timedelta(hours=7))
CAPTION_LIMIT = 1024                # Telegram photo caption cap
PROXIES = {"http": "http://proxy.server:3128", "https": "http://proxy.server:3128"}

# --- Weekly schedule: weekday -> (title, image, [(time, event)]) ---
SCHEDULE = {
    0: ("Monday", "guild-party.png", [
        ("7:00 - 7:10 PM", "Guild Party"),
        (None, "Hero Realms - WEEKLY RESET, clear your runs"),
    ]),
    1: ("Tuesday", "breaking.png", [
        ("7:00 - 7:10 PM", "Guild Party"),
        ("7:30 - 9:30 PM", "Breaking Army"),
        (None, "Hero Realms"),
    ]),
    2: ("Wednesday", "test-skill.png", [
        ("7:00 - 7:10 PM", "Guild Party"),
        ("7:30 - 9:30 PM", "Test Your Skill"),
        (None, "Hero Realms"),
    ]),
    3: ("Thursday", "breaking.png", [
        ("7:00 - 7:10 PM", "Guild Party"),
        ("7:30 - 9:30 PM", "Breaking Army"),
        (None, "Hero Realms"),
    ]),
    4: ("Friday", "test-skill.png", [
        ("7:00 - 7:10 PM", "Guild Party"),
        ("7:30 - 9:30 PM", "Test Your Skill"),
        (None, "Hero Realms"),
    ]),
    5: ("Saturday", "gw-register.png", [
        ("7:00 - 7:10 PM", "Guild Party"),
        ("7:30 - 9:00 PM", "GUILD WAR"),
        (None, "Hero Realms"),
    ]),
    6: ("Sunday", "gw-register.png", [
        ("7:00 - 7:10 PM", "Guild Party"),
        ("7:30 - 9:00 PM", "GUILD WAR"),
        (None, "Hero Realms"),
    ]),
}


def esc(s):
    return html.escape(str(s))






def build(now):
    """Daily event schedule. GW signups live in Discord now, so no roster block."""
    day_name, image, events = SCHEDULE[now.weekday()]

    lines = [
        f"\U0001f3ee <b>{day_name.upper()}</b> — {esc(now.strftime('%d %b %Y'))}",
        "",
    ]
    for slot, event in events:
        if slot:
            lines.append(f"⏰ <b>{slot}</b> › {esc(event)}")
        else:
            lines.append(f"\U0001f538 {esc(event)}")

    return f"{IMAGE_BASE}/{image}", "\n".join(lines), ""


def api(method, payload):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, proxies=PROXIES, timeout=30)
            if r.status_code == 200:
                return True
            print(f"{method} failed: {r.status_code} {r.text[:200]}")
        except requests.exceptions.RequestException as e:
            print(f"{method} attempt {attempt + 1} failed: {e}")
        time.sleep(30)
    return False


def alert_admin(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": text},
            proxies=PROXIES,
            timeout=30,
        )
    except requests.exceptions.RequestException:
        pass


def visible_len(s):
    """Length Telegram counts: markup stripped, entities decoded."""
    return len(html.unescape(re.sub(r"<[^>]+>", "", s)))


def preview_week():
    """DM all seven days to the admin, so the whole week can be eyeballed."""
    base = datetime.now(KH)
    monday = base - timedelta(days=base.weekday())
    for i in range(7):
        day = monday + timedelta(days=i)
        photo, caption, body = build(day)
        combined = "\n\n".join(p for p in (caption, body) if p)
        one = visible_len(combined) <= CAPTION_LIMIT
        ok = api("sendPhoto", {
            "chat_id": ADMIN_CHAT_ID,
            "photo": photo,
            "caption": combined if one else caption,
            "parse_mode": "HTML",
        })
        if ok and not one:
            api("sendMessage", {
                "chat_id": ADMIN_CHAT_ID, "text": body,
                "parse_mode": "HTML", "disable_web_page_preview": True,
            })
        print(f"{day:%a %Y-%m-%d} -> {'sent' if ok else 'FAILED'}")
        time.sleep(2)


def main():
    test_mode = "--test" in sys.argv
    if "--preview-week" in sys.argv:
        preview_week()
        return
    now = datetime.now(KH)
    photo, caption, body = build(now)

    combined = "\n\n".join(p for p in (caption, body) if p)
    one_message = visible_len(combined) <= CAPTION_LIMIT

    print(photo)
    print(combined if one_message else f"{caption}\n\n[split]\n\n{body}")

    if test_mode:
        return

    sent = api("sendPhoto", {
        "chat_id": CHAT_ID,
        "photo": photo,
        "caption": combined if one_message else caption,
        "parse_mode": "HTML",
    })
    if not sent:
        alert_admin("GW bot: sendPhoto failed, falling back to text.")
        api("sendMessage", {
            "chat_id": CHAT_ID, "text": combined,
            "parse_mode": "HTML", "disable_web_page_preview": True,
        })
        return

    # Roster outgrew the caption limit, so the report follows separately.
    if not one_message and not api("sendMessage", {
        "chat_id": CHAT_ID, "text": body,
        "parse_mode": "HTML", "disable_web_page_preview": True,
    }):
        alert_admin("GW bot: report message failed to send after 3 attempts.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        alert_admin(f"GW bot crashed: {e}")
