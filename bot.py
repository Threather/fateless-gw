"""Fateless Register — Discord bot for Guild War registration.

Saves to the same Firebase path the website used:
guild_wars/<monday YYYY-MM-DD>/registrations
"""
import asyncio
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
# Discord user IDs allowed to use the leaders-only Jungle page: Threather (owner), XingYun
LEADER_IDS = {"1456963082302525493", "499764537076088852"}
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
                "grant_type": "authorization_code", "code": req["code"]}).json()
            headers = {"Authorization": f"Bearer {tok['access_token']}"}
            member = requests.get(f"{API}/users/@me/guilds/{req.get('guild')}/member",
                                  headers=headers, timeout=15).json()
            user = member.get("user") or requests.get(f"{API}/users/@me", headers=headers, timeout=15).json()
            name = member.get("nick") or user.get("global_name") or user["username"]
            avatar = (f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png?size=64"
                      if user.get("avatar") else None)
            ref.set({"name": name, "avatar": avatar, "id": user["id"],
                     "admin": user["id"] in LEADER_IDS, "at": int(time.time() * 1000)})
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


# Same person, different names (old website name -> Discord nickname).
ALIASES = {"rasmach": "xspear", "polpot": "xspear", "xinagtiandi": "xiangtuchh"}


def same_player(a, b):
    a, b = a.strip().lower(), b.strip().lower()
    return ALIASES.get(a, a) == ALIASES.get(b, b)


def last_registration(name, weeks_back=8):
    """This member's most recent entry from an earlier week, or None."""
    weeks = sorted((db.reference("guild_wars").get(shallow=True) or {}), reverse=True)
    for wk in [w for w in weeks if w < week_key()][:weeks_back]:
        regs = db.reference(f"guild_wars/{wk}/registrations").get() or {}
        for p in regs.values():
            if same_player(p.get("name", ""), name) and p.get("team") in ("attack", "defend"):
                return p
    return None


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

LOGO = HERE / "assets" / "fateless-logo.png"
INTRO_TITLE = "GUILD WAR REGISTRATION"
TEAM_NAMES = {"attack": "Attack", "defend": "Defend"}
DAYS = ["Saturday", "Sunday", "Sat & Sun"]
GOLD = 0xD4A24C


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
        "Press **Register**, pick your weapons, team and day."))
    embed.add_field(name="Saturday", value=f"{bar(sat, DAY_MAX)}\n**{sat}** / {DAY_MAX}")
    embed.add_field(name="Sunday", value=f"{bar(sun, DAY_MAX)}\n**{sun}** / {DAY_MAX}")
    embed.add_field(name="Reserve", value=f"​\n**{reserves}**")
    embed.set_thumbnail(url="attachment://logo.png")
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
    """The private form: weapon dropdowns, one-tap buttons for team and day."""

    def __init__(self, name, last=None):
        super().__init__(timeout=600)
        self.name = name
        self.answers = {k: last[k] for k in ("weapon1", "weapon2", "team", "avail")} if last else {}
        self.add_select("weapon1", "Main weapon", 0)
        self.add_select("weapon2", "Second weapon", 1)
        self.choice_buttons = {"team": [], "avail": []}
        for value, label in TEAM_NAMES.items():
            self.add_choice("team", value, label, 2)
        for day in DAYS:
            self.add_choice("avail", day, day, 3)

    def add_select(self, key, placeholder, row):
        opts = [discord.SelectOption(label=w, value=w, default=w == self.answers.get(key))
                for w in sorted(WEAPONS)]
        select = discord.ui.Select(placeholder=placeholder, options=opts, row=row)

        async def picked(interaction):
            self.answers[key] = select.values[0]
            for opt in select.options:  # keep the choice visible
                opt.default = opt.value == select.values[0]
            await interaction.response.edit_message(view=self)
        select.callback = picked
        self.add_item(select)

    def add_choice(self, key, value, label, row):
        button = discord.ui.Button(label=label, row=row)
        button.value = value

        async def clicked(interaction):
            self.answers[key] = value
            self.paint()
            await interaction.response.edit_message(view=self)
        button.callback = clicked
        self.choice_buttons[key].append(button)
        self.add_item(button)
        self.paint()

    def paint(self):
        for key, buttons in self.choice_buttons.items():
            for b in buttons:
                b.style = (discord.ButtonStyle.primary if self.answers.get(key) == b.value
                           else discord.ButtonStyle.secondary)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, row=4)
    async def submit(self, interaction, button):
        labels = {"weapon1": "Main weapon", "weapon2": "Second weapon", "team": "Team", "avail": "Day"}
        missing = [labels[k] for k in labels if k not in self.answers]
        if missing:
            await interaction.response.send_message(
                "Still need: **" + "**, **".join(missing) + "**", ephemeral=True)
            return
        a = self.answers
        ok, r = register_player(self.name, a["weapon1"], a["weapon2"], None,
                                a["team"], a["avail"], False)
        if not ok:
            await interaction.response.send_message(r, ephemeral=True)
            return
        await interaction.response.edit_message(content="You're registered.", embed=None, view=None)

        slot = f"{'Reserve' if r['isReserve'] else 'Main roster'} #{r['slot']}"
        embed = discord.Embed(color=0xE67E22 if r["isReserve"] else 0x2ECC71, description=(
            f"**{r['name']}** registered\n{r['weapon1']} / {r['weapon2']}"))
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Team", value=TEAM_NAMES[r["team"]])
        embed.add_field(name="Day", value=r["avail"])
        embed.add_field(name="Slot", value=slot)
        await interaction.channel.send(embed=embed)
        await refresh_intros()


class RegisterButton(discord.ui.View):
    """The permanent buttons under the register message."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Register", style=discord.ButtonStyle.success, custom_id="gw_register")
    async def open_form(self, interaction, button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        name = interaction.user.display_name
        last = await asyncio.to_thread(last_registration, name)
        text = f"Registering as **{name}**"
        text += ("\nLast week's picks are filled in. Press **Confirm**, or change something first."
                 if last else "\nPick your weapons, team and day, then press **Confirm**.")
        embed = discord.Embed(color=GOLD, description=text)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed, view=RegisterForm(name, last), ephemeral=True)

    @discord.ui.button(label="Open Dashboard", style=discord.ButtonStyle.secondary,
                       custom_id="gw_dashboard")
    async def open_dashboard(self, interaction, button):
        await interaction.response.launch_activity()


listening = False


@client.event
async def on_ready():
    global listening
    client.add_view(RegisterButton())
    if client.user.avatar is None:  # use the guild logo as the bot's picture
        await client.user.edit(avatar=LOGO.read_bytes())
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
                                 file=discord.File(LOGO, filename="logo.png"))
        intro_messages.append(msg)
    print(f"Logged in as {client.user} — Register button is ready")


client.run(read_env("DISCORD_TOKEN"))
