"""Fateless daily Telegram reminder.

Runs once a day at 12:00 UTC (7PM Cambodia) on PythonAnywhere.
Preview without sending:  python gw_report.py --test
"""
import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import firebase_admin
import requests
from firebase_admin import credentials, db

# --- Config ---
BOT_TOKEN = "YOUR_TOKEN_HERE"
CHAT_ID = "-1003652956919"          # Fateless supergroup
ADMIN_CHAT_ID = "924385557"         # Threather DM, for error alerts
SERVICE_ACCOUNT = "/home/Threather/ascendantkh-gw-firebase-adminsdk-fbsvc-1772fb34c9.json"
DATABASE_URL = "https://ascendantkh-gw-default-rtdb.asia-southeast1.firebasedatabase.app"
SITE_URL = "https://threather.github.io/fateless-gw/"
IMAGE_BASE = "https://raw.githubusercontent.com/Threather/fateless-gw/main/assets"

KH = timezone(timedelta(hours=7))
CAPTION_LIMIT = 1024                # Telegram photo caption cap
ROSTER_START = "2026-08-17"          # roster ignores weeks before this Monday
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

firebase_admin.initialize_app(
    credentials.Certificate(SERVICE_ACCOUNT), {"databaseURL": DATABASE_URL}
)


def week_key(when):
    """Monday of the given date, matching getMonthKey() in index.html."""
    monday = when - timedelta(days=when.weekday())
    return monday.strftime("%Y-%m-%d")


def esc(s):
    return html.escape(str(s))


def expandable(label, names):
    """Collapsed blockquote the group can tap to expand."""
    if not names:
        return f"<blockquote><b>{esc(label)}</b>\nnone</blockquote>"
    body = "\n".join(esc(n) for n in sorted(names, key=str.lower))
    return f"<blockquote expandable><b>{esc(label)}</b>\n{body}</blockquote>"


def load_data(now):
    guild_wars = db.reference("/guild_wars").get() or {}
    # Keys are percent-encoded (Firebase rejects "." and friends), so the
    # authoritative name is the stored value.
    blocked = {
        str(v).strip().lower()
        for v in (db.reference("/roster_blocklist").get() or {}).values()
    }

    this_week = week_key(now)

    # The roster accumulates from ROSTER_START onward, so old members and dead
    # spellings never come back. Names leave it only via roster_blocklist.
    roster = {}       # lowercase -> display name, most recent spelling wins
    for wk in sorted(k for k in guild_wars if k >= ROSTER_START):
        for player in (guild_wars[wk].get("registrations") or {}).values():
            name = (player.get("name") or "").strip()
            if name and name.lower() not in blocked:
                roster[name.lower()] = name

    current = (guild_wars.get(this_week, {}) or {}).get("registrations") or {}
    return this_week, roster, current


def registration_block(this_week, roster, current):
    """Mon-Fri view: who has signed up, who has not."""
    registered = {}
    for player in current.values():
        name = (player.get("name") or "").strip()
        if name:
            registered[name.lower()] = name

    missing = [roster[k] for k in roster if k not in registered]
    total = len(registered) + len(missing)

    return (
        f"⚔️ <b>GW Registration</b> | week of {esc(this_week)}\n"
        f"✅ Registered: <b>{len(registered)}</b> / {total}\n"
        f"❌ Not yet: <b>{len(missing)}</b>\n\n"
        f"{expandable(f'Registered ({len(registered)})', registered.values())}"
        f"{expandable(f'Not registered ({len(missing)})', missing)}\n"
        f"\U0001f4dd Register: {SITE_URL}"
    )


def lineup_block(this_week, current):
    """Sat-Sun view: the actual roster going into the war."""
    sat = {"roles": [], "team": [], "top": 0, "bot": 0}
    sun = {"roles": [], "team": [], "top": 0, "bot": 0}
    reserves = []

    for player in current.values():
        role = player.get("role", "unknown")
        if player.get("isReserve", False):
            reserves.append(role)
            continue
        avail = player.get("avail", "")
        for day, tag in ((sat, "Saturday"), (sun, "Sunday")):
            if avail in ("Sat & Sun", tag):
                day["roles"].append(role)
                day["team"].append(player.get("team", ""))
                if player.get("jungle", False):
                    if player.get("jungleSide") == "Top":
                        day["top"] += 1
                    elif player.get("jungleSide") == "Bottom":
                        day["bot"] += 1

    def line(day):
        r = day["roles"]
        return (
            f"{len(r)} players [H:{r.count('heal')} T:{r.count('tank')} D:{r.count('dps')}]\n"
            f"   ⚔️ Attack: {day['team'].count('attack')} | "
            f"\U0001f6e1 Defend: {day['team'].count('defend')}\n"
            f"   \U0001f33f Jungle: Top:{day['top']} | Bot:{day['bot']}"
        )

    main_total = sum(1 for p in current.values() if not p.get("isReserve", False))
    return (
        f"⚔️ <b>GW Lineup</b> | week of {esc(this_week)}\n"
        f"\U0001f5d3 <b>SAT</b> › {line(sat)}\n\n"
        f"\U0001f5d3 <b>SUN</b> › {line(sun)}\n\n"
        f"\U0001f465 Total: {main_total} | \U0001f512 Reserve: {len(reserves)} "
        f"[H:{reserves.count('heal')} T:{reserves.count('tank')} D:{reserves.count('dps')}]\n"
        f"\U0001f4dd {SITE_URL}"
    )


def build(now):
    day_name, image, events = SCHEDULE[now.weekday()]
    this_week, roster, current = load_data(now)

    lines = [
        f"\U0001f3ee <b>{day_name.upper()}</b> — {esc(now.strftime('%d %b %Y'))}",
        "",
    ]
    for slot, event in events:
        if slot:
            lines.append(f"⏰ <b>{slot}</b> › {esc(event)}")
        else:
            lines.append(f"\U0001f538 {esc(event)}")

    caption = "\n".join(lines)

    if now.weekday() >= 5:
        body = lineup_block(this_week, current)
    else:
        body = registration_block(this_week, roster, current)

    return f"{IMAGE_BASE}/{image}", caption, body


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
        combined = f"{caption}\n\n{body}"
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

    combined = f"{caption}\n\n{body}"
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
