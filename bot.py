"""Fateless Register — Discord bot for Guild War registration.

Saves to the same Firebase path the website used:
guild_wars/<monday YYYY-MM-DD>/registrations
"""
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
import requests
import firebase_admin
from firebase_admin import credentials, db

HERE = Path(__file__).parent
DATABASE_URL = "https://ascendantkh-gw-default-rtdb.asia-southeast1.firebasedatabase.app"
CAMBODIA = timezone(timedelta(hours=7))

REGISTER_CHANNEL = "guild-war-register"

DAY_MAX, RESERVE_MAX, JUNGLE_MAX = 30, 60, 8

WEAPONS = [
    "Nameless Sword", "Nameless Spear", "Stormbreaker Spear", "Thundercry Blade",
    "Infernal Twinblades", "Mortal Rope Dart", "Vernal Umbrella", "Inkwell Fan",
    "Panacea Fan", "Soulshade Umbrella", "Heavenquaker Spear", "Strategic Sword",
    "Snowparting Blade", "Phalanxbane Blade", "Everspring Umbrella", "Unfettered Rope Dart",
    "Heavenwill Gauntlets", "Skygrasp Rope Dart",
]


def read_env(key):
    for line in (HERE / ".env").read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"{key} missing from .env")


CLIENT_ID = "1561639617776590889"
API = "https://discord.com/api/v10"


def handle_activity_login(event):
    """The dashboard writes an OAuth code to activity_auth/<id>; answer with the member's nickname."""
    if event.path == "/":
        requests_ = (event.data or {}).items()
    else:
        requests_ = [(event.path.strip("/").split("/")[0], event.data)]
    for key, req in requests_:
        if not isinstance(req, dict) or "code" not in req or "name" in req or "error" in req:
            continue
        ref = db.reference(f"activity_auth/{key}")
        try:
            tok = requests.post(f"{API}/oauth2/token", timeout=15, data={
                "client_id": CLIENT_ID, "client_secret": read_env("DISCORD_CLIENT_SECRET"),
                "grant_type": "authorization_code", "code": req["code"],
                "redirect_uri": "https://127.0.0.1"}).json()
            headers = {"Authorization": f"Bearer {tok['access_token']}"}
            member = requests.get(f"{API}/users/@me/guilds/{req.get('guild')}/member",
                                  headers=headers, timeout=15).json()
            user = member.get("user") or requests.get(f"{API}/users/@me", headers=headers, timeout=15).json()
            name = member.get("nick") or user.get("global_name") or user["username"]
            avatar = (f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png?size=64"
                      if user.get("avatar") else None)
            ref.set({"name": name, "avatar": avatar, "at": int(time.time() * 1000)})
            threading.Timer(60, ref.delete).start()  # tidy up
        except Exception as e:
            print("Dashboard sign-in failed:", e)
            ref.set({"error": "Sign-in failed, please reopen the dashboard."})


def week_key():
    now = datetime.now(CAMBODIA)
    monday = now - timedelta(days=now.weekday())
    return monday.strftime("%Y-%m-%d")


def regs_ref():
    return db.reference(f"guild_wars/{week_key()}/registrations")


def plays_sat(p): return p.get("avail") in ("Saturday", "Sat & Sun")
def plays_sun(p): return p.get("avail") in ("Sunday", "Sat & Sun")


def register_player(name, w1, w2, role, team, avail, jungle):
    """Same rules as the website. Returns (ok, message_or_record)."""
    if w1 == w2:
        return False, "Weapon 1 and 2 must be different."
    players = list((regs_ref().get() or {}).values())
    if any(p.get("name", "").lower() == name.lower() for p in players):
        return False, f'"{name}" is already registered.'

    main = [p for p in players if not p.get("isReserve")]
    reserves = [p for p in players if p.get("isReserve")]
    sat = sum(plays_sat(p) for p in main)
    sun = sum(plays_sun(p) for p in main)
    is_reserve = ((avail == "Saturday" and sat >= DAY_MAX) or
                  (avail == "Sunday" and sun >= DAY_MAX) or
                  (avail == "Sat & Sun" and sat >= DAY_MAX and sun >= DAY_MAX))
    if is_reserve and len(reserves) >= RESERVE_MAX:
        return False, "All slots including reserve are full!"

    jungle_side = None
    jungle = jungle and not is_reserve
    if jungle:
        jung = [p for p in main if p.get("jungle")]
        if avail in ("Saturday", "Sat & Sun") and sum(plays_sat(p) for p in jung) >= JUNGLE_MAX:
            return False, "Saturday jungle is full (8/8)!"
        if avail in ("Sunday", "Sat & Sun") and sum(plays_sun(p) for p in jung) >= JUNGLE_MAX:
            return False, "Sunday jungle is full (8/8)!"
        top = [p for p in jung if p.get("jungleSide") == "Top"]
        bot = [p for p in jung if p.get("jungleSide") == "Bottom"]
        if role == "heal":
            top_heal = any(p.get("role") == "heal" for p in top)
            bot_heal = any(p.get("role") == "heal" for p in bot)
            if top_heal and bot_heal:
                return False, "Both jungle sides already have a healer."
            jungle_side = "Bottom" if top_heal else "Top"
        else:
            jungle_side = ("Bottom" if len(top) >= 4 else "Top" if len(bot) >= 4
                           else "Top" if len(top) <= len(bot) else "Bottom")

    record = {
        "name": name, "weapon1": w1, "weapon2": w2, "role": role, "team": team,
        "avail": avail, "jungle": jungle, "jungleSide": jungle_side,
        "isReserve": is_reserve, "registeredAt": int(time.time() * 1000),
    }
    regs_ref().push(record)
    record["slot"] = (len(reserves) if is_reserve else len(main)) + 1
    return True, record


firebase_admin.initialize_app(credentials.Certificate(str(HERE / "firebase-key.json")),
                              {"databaseURL": DATABASE_URL})

INTRO_TITLE = "⚔️ GUILD WAR REGISTRATION"
BANNER = HERE / "assets" / "gw-register.png"
TEAM_NAMES = {"attack": "⚔️ Attack", "defend": "🛡️ Defend"}
DAY_EMOJI = {"Saturday": "📅", "Sunday": "📆", "Sat & Sun": "🔥"}
GOLD = 0xD4A24C


def weapon_emoji(weapon):
    for word, emoji in [("Sword", "⚔️"), ("Spear", "🔱"), ("Twinblades", "🌀"), ("Blade", "🗡️"),
                        ("Umbrella", "☂️"), ("Fan", "🪭"), ("Rope Dart", "🪢"), ("Gauntlets", "🥊")]:
        if word in weapon:
            return emoji
    return "⚔️"


client = discord.Client(intents=discord.Intents.default())
intro_messages = []  # register messages to refresh after each signup


def bar(count, total, width=10):
    filled = round(width * min(count, total) / total)
    return "▰" * filled + "▱" * (width - filled)


def build_intro():
    players = list((regs_ref().get() or {}).values())
    main = [p for p in players if not p.get("isReserve")]
    sat = sum(plays_sat(p) for p in main)
    sun = sum(plays_sun(p) for p in main)
    reserves = len(players) - len(main)
    embed = discord.Embed(title=INTRO_TITLE, color=GOLD, description=(
        "The battlefield awaits, **Fateless**.\n"
        "Press **Register** below, pick your weapons, team and day — done in 10 seconds.\n​"))
    embed.add_field(name="📅 Saturday", value=f"{bar(sat, DAY_MAX)}\n**{sat}** / {DAY_MAX}")
    embed.add_field(name="📆 Sunday", value=f"{bar(sun, DAY_MAX)}\n**{sun}** / {DAY_MAX}")
    embed.add_field(name="🪑 Reserve", value=f"​\n**{reserves}**")
    embed.set_image(url="attachment://gw-register.png")
    embed.set_footer(text=f"Week of {week_key()} • Resets every Monday • Name = your server nickname")
    return embed


async def refresh_intros():
    embed = build_intro()
    for msg in intro_messages:
        try:
            await msg.edit(embed=embed)
        except discord.HTTPException:
            pass


class RegisterForm(discord.ui.View):
    """The private form a member sees after clicking Register."""

    def __init__(self, name):
        super().__init__(timeout=600)
        self.name = name
        self.answers = {}
        weapons = [(w, w, weapon_emoji(w)) for w in WEAPONS]
        self.add_select("weapon1", "🗡️  Choose your main weapon", weapons, 0)
        self.add_select("weapon2", "🗡️  Choose your second weapon", weapons, 1)
        self.add_select("team", "🚩  Attack or Defend?",
                        [(v[3:], k, v[:2]) for k, v in TEAM_NAMES.items()], 2)
        self.add_select("avail", "📅  Which day can you play?",
                        [(d, d, e) for d, e in DAY_EMOJI.items()], 3)

    def add_select(self, key, placeholder, choices, row):
        opts = [discord.SelectOption(label=label, value=value, emoji=emoji)
                for label, value, emoji in choices]
        select = discord.ui.Select(placeholder=placeholder, options=opts, row=row)

        async def picked(interaction):
            self.answers[key] = select.values[0]
            for opt in select.options:  # keep the choice visible
                opt.default = opt.value == select.values[0]
            await interaction.response.edit_message(view=self)
        select.callback = picked
        self.add_item(select)

    @discord.ui.button(label="Confirm Registration", emoji="✅",
                       style=discord.ButtonStyle.success, row=4)
    async def submit(self, interaction, button):
        labels = {"weapon1": "Weapon 1", "weapon2": "Weapon 2", "team": "Team", "avail": "Day"}
        missing = [labels[k] for k in labels if k not in self.answers]
        if missing:
            await interaction.response.send_message(
                "⚠️ Still need: **" + "**, **".join(missing) + "**", ephemeral=True)
            return
        a = self.answers
        ok, r = register_player(self.name, a["weapon1"], a["weapon2"], None,
                                a["team"], a["avail"], False)
        if not ok:
            await interaction.response.send_message(f"❌ {r}", ephemeral=True)
            return
        await interaction.response.edit_message(
            content="✅ **You're in!** See you on the battlefield.", view=None)

        slot = f"{'🪑 Reserve' if r['isReserve'] else '🏆 Main Roster'} #{r['slot']}"
        embed = discord.Embed(color=0xE67E22 if r["isReserve"] else 0x2ECC71, description=(
            f"### {r['name']} has joined the war\n"
            f"{weapon_emoji(r['weapon1'])} **{r['weapon1']}**  ·  "
            f"{weapon_emoji(r['weapon2'])} **{r['weapon2']}**"))
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Team", value=TEAM_NAMES[r["team"]])
        embed.add_field(name="Day", value=f"{DAY_EMOJI[r['avail']]} {r['avail']}")
        embed.add_field(name="Slot", value=slot)
        await interaction.channel.send(embed=embed)
        await refresh_intros()


class RegisterButton(discord.ui.View):
    """The permanent button under the register message."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Register", emoji="⚔️", style=discord.ButtonStyle.danger,
                       custom_id="gw_register")
    async def open_form(self, interaction, button):
        name = interaction.user.display_name
        embed = discord.Embed(color=GOLD, description=(
            f"Registering as **{name}**\nPick all four, then press **Confirm Registration**."))
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, view=RegisterForm(name),
                                                ephemeral=True)

    @discord.ui.button(label="Open Dashboard", emoji="📊", style=discord.ButtonStyle.primary,
                       custom_id="gw_dashboard")
    async def open_dashboard(self, interaction, button):
        await interaction.response.launch_activity()


listening = False


@client.event
async def on_ready():
    global listening
    client.add_view(RegisterButton())
    if not listening:
        listening = True
        db.reference("activity_auth").listen(handle_activity_login)
    intro_messages.clear()
    for guild in client.guilds:
        channel = next((c for c in guild.text_channels if c.name.endswith(REGISTER_CHANNEL)), None)
        if channel is None:
            print(f"#{REGISTER_CHANNEL} not found in {guild.name}")
            continue
        old = [m async for m in channel.history(limit=50)
               if m.author == client.user and m.components]
        for m in old:  # replace earlier versions with one fresh message
            await m.delete()
        msg = await channel.send(embed=build_intro(), view=RegisterButton(),
                                 file=discord.File(BANNER, filename="gw-register.png"))
        intro_messages.append(msg)
    print(f"Logged in as {client.user} — Register button is ready")


client.run(read_env("DISCORD_TOKEN"))
