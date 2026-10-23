import os
import random
import asyncio
import json
import sqlite3
from pathlib import Path

import discord
from discord.ext import commands


# ============================================================
# USTAWIENIA HOSTINGU
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "Brak zmiennej DISCORD_TOKEN w ustawieniach hostingu!"
    )


# ============================================================
# USTAWIENIA BOGINA
# ============================================================

EXCLUDED_USERS = {
    1558587320461164678,
    1558559995052818573,
}

EXCLUSIONS_FILE = Path(
    os.getenv("BOGIN_EXCLUSIONS_FILE", "bogin_wykluczeni.json")
)

BOGIN_FORMS = [
    "Klaun",
    "Severus Snape",
    "Lord Voldemort",
    "Pełnia",
    "Alishia Farias",
    "Akromantula",
    "Dementor",
    "Wąż",
    "Lilith Noir",
    "Smok",
    "Egzamin",
    "Śmierciotula",
    "Inferius",
    "Oni",
]


def load_exclusions():
    try:
        if EXCLUSIONS_FILE.exists():
            data = json.loads(
                EXCLUSIONS_FILE.read_text(encoding="utf-8")
            )
            return {
                int(x) for x in data if str(x).isdigit()
            }
    except (OSError, ValueError, TypeError) as exc:
        print(f"Nie udało się wczytać wykluczeń: {exc}")

    return set()


extra_exclusions = load_exclusions()


def save_exclusions():
    tmp = EXCLUSIONS_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(sorted(extra_exclusions), indent=2),
        encoding="utf-8",
    )
    tmp.replace(EXCLUSIONS_FILE)


def excluded(user_id):
    return (
        user_id in EXCLUDED_USERS
        or user_id in extra_exclusions
    )


# ============================================================
# KONFIGURACJA DISCORDA — TYLKO JEDEN BOT
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    case_insensitive=True,
)

# thread_id -> {"task": Task, "response": Event, ...}
games = {}


# ============================================================
# BAZA DANYCH I LOGI WIADOMOŚCI
# ============================================================

LOG_CHANNEL_ID = 1562477162882269315
DB_FILE = Path("messages.db")


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY,
                content TEXT,
                author_id INTEGER,
                channel_id INTEGER
            )
        """)


init_db()


async def get_log_channel():
    """Pobiera kanał logów z pamięci lub bezpośrednio z Discorda."""
    channel = bot.get_channel(LOG_CHANNEL_ID)

    if channel is None:
        try:
            channel = await bot.fetch_channel(LOG_CHANNEL_ID)
        except (discord.NotFound, discord.Forbidden,
                discord.HTTPException) as exc:
            print(f"Nie można pobrać kanału logów: {exc}")
            return None

    if not hasattr(channel, "send"):
        print("Podane ID nie wskazuje kanału, na którym można wysyłać wiadomości.")
        return None

    return channel


async def send_log(embed):
    """Wysyła log i zapisuje ewentualny błąd w konsoli."""
    channel = await get_log_channel()

    if channel is None:
        return

    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"Nie udało się wysłać logu: {exc}")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Błąd bazy nie może zatrzymać obsługi komend.
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("""
                INSERT OR IGNORE INTO messages
                (message_id, content, author_id, channel_id)
                VALUES (?, ?, ?, ?)
            """, (
                message.id,
                message.content,
                message.author.id,
                message.channel.id,
            ))
    except sqlite3.Error as exc:
        print(f"Błąd zapisu wiadomości do bazy: {exc}")

    # KONIECZNIE przetwarzamy komendy tekstowe.
    await bot.process_commands(message)


@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return

    try:
        with sqlite3.connect(DB_FILE) as conn:
            row = conn.execute(
                "SELECT content FROM messages WHERE message_id = ?",
                (message.id,),
            ).fetchone()
    except sqlite3.Error as exc:
        print(f"Błąd odczytu usuniętej wiadomości: {exc}")
        row = None

    content = (
        row[0] if row and row[0]
        else message.content or "Brak treści tekstowej / załącznik"
    )

    embed = discord.Embed(
        title="🗑️ Usunięto wiadomość",
        color=discord.Color.red(),
        timestamp=message.created_at,
    )
    embed.add_field(
        name="Autor",
        value=f"{message.author} (ID: {message.author.id})",
        inline=False,
    )
    embed.add_field(
        name="Kanał",
        value=f"#{message.channel.name}",
        inline=False,
    )
    embed.add_field(
        name="Treść",
        value=content[:1024],
        inline=False,
    )

    await send_log(embed)


@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return

    embed = discord.Embed(
        title="✏️ Edytowano wiadomość",
        color=discord.Color.orange(),
        timestamp=after.edited_at or discord.utils.utcnow(),
    )
    embed.add_field(
        name="Autor",
        value=f"{before.author} (ID: {before.author.id})",
        inline=False,
    )
    embed.add_field(
        name="Kanał",
        value=f"#{before.channel.name}",
        inline=False,
    )
    embed.add_field(
        name="Przed edycją",
        value=(before.content or "Brak")[:1024],
        inline=False,
    )
    embed.add_field(
        name="Po edycji",
        value=(after.content or "Brak")[:1024],
        inline=False,
    )
    embed.add_field(
        name="Link",
        value=after.jump_url,
        inline=False,
    )

    await send_log(embed)


# ============================================================
# GOTOWOŚĆ BOTA
# ============================================================

@bot.event
async def on_ready():
    print("--------------------------------------")
    print(f"Zalogowano jako: {bot.user} (ID: {bot.user.id})")
    print("Bogin jest gotowy do zabawy w dowolnym wątku!")
    print("Archiwizowanie wiadomości jest włączone.")
    print("--------------------------------------")


# ============================================================
# BOGIN — FUNKCJE POMOCNICZE
# ============================================================

def is_thread(channel):
    return isinstance(channel, discord.Thread)


async def get_players(thread):
    """Pobiera członków wątku i pomija wykluczone osoby."""
    try:
        thread_members = await thread.fetch_members()
    except discord.DiscordException as exc:
        print(
            f"Nie udało się pobrać uczestników wątku "
            f"{thread.id}: {exc}"
        )
        return None

    players = []

    for thread_member in thread_members:
        user_id = thread_member.id

        if excluded(user_id):
            continue

        member = thread.guild.get_member(user_id)

        if member is None:
            try:
                member = await thread.guild.fetch_member(user_id)
            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ):
                continue

        if member.bot or excluded(member.id):
            continue

        players.append(member)

    return players


async def countdown(thread, state):
    """Zwraca True po zaklęciu, False po zakończeniu odliczania."""
    event = state["response"]
    event.clear()
    state["waiting"] = True

    try:
        for number in (3, 2, 1, 0):
            await thread.send(str(number))

            try:
                await asyncio.wait_for(event.wait(), timeout=1.0)
                return True
            except asyncio.TimeoutError:
                continue

        return False
    finally:
        state["waiting"] = False


async def run_game(thread, state):
    """Pętla gry niezależna dla każdego wątku."""
    try:
        while True:
            players = await get_players(thread)

            if players is None:
                await thread.send(
                    "[*Nie mogę pobrać listy uczestników wątku. "
                    "Sprawdź uprawnienia bota.*]"
                )
                return

            if not players:
                await thread.send(
                    "[*Nie ma w tym wątku dostępnych osób, "
                    "które Bogin może zaatakować.*]"
                )
                return

            target = random.choice(players)

            if excluded(target.id):
                continue

            form = random.choice(BOGIN_FORMS)

            await thread.send(
                f"[*Bogin przybrał formę {form} i zaczął zbliżać się do "
                f"{target.mention}. By obezwładnić Bogina użyj komendy "
                "!Riddikulus bez kropki.*]"
            )

            attempt = 0

            while True:
                success = await countdown(thread, state)

                if success:
                    await thread.send(
                        "[*Po udanej próbie obezwładnienia Bogin "
                        "wrócił do szafy.*]"
                    )
                    await asyncio.sleep(5)
                    break

                attempt += 1

                if attempt == 1:
                    text = (
                        "[*Niestety zaklęcie nie zadziałało, a Bogin "
                        "zaczął zbierać się do ataku. Szybko ponów zaklęcie!*]"
                    )
                elif attempt == 2:
                    text = (
                        "[*Niestety zaklęcie ponownie nie zadziałało, "
                        "a Bogin jest coraz bliżej! Szybko ponów zaklęcie!*]"
                    )
                else:
                    text = (
                        "[*Niestety zaklęcie nadal nie zadziałało! "
                        "Bogin szykuje się do ataku. Szybko ponów zaklęcie!*]"
                    )

                await thread.send(text)

    except asyncio.CancelledError:
        raise
    except discord.DiscordException as exc:
        print(f"Błąd Discord w wątku {thread.id}: {exc}")
    except Exception as exc:
        print(f"Błąd gry w wątku {thread.id}: {exc}")
    finally:
        if games.get(thread.id) is state:
            games.pop(thread.id, None)


# ============================================================
# KOMENDY BOGINA
# ============================================================

@bot.command(name="start")
async def start(ctx):
    if not is_thread(ctx.channel):
        await ctx.send(
            "[*Zabawę z Boginem można rozpocząć tylko we wątku.*]"
        )
        return

    if ctx.channel.id in games:
        await ctx.send("[*Bogin już grasuje w tym wątku!*]")
        return

    state = {
        "response": asyncio.Event(),
        "task": None,
        "waiting": False,
    }

    games[ctx.channel.id] = state
    state["task"] = asyncio.create_task(
        run_game(ctx.channel, state)
    )


@bot.command(name="riddikulus")
async def riddikulus(ctx):
    if not is_thread(ctx.channel):
        return

    state = games.get(ctx.channel.id)

    if state and state["task"] and not state["task"].done():
        if state.get("waiting", False):
            state["response"].set()


@bot.command(name="stop")
async def stop(ctx):
    if not is_thread(ctx.channel):
        await ctx.send("[*Komenda !stop działa we wątku zabawy.*]")
        return

    state = games.pop(ctx.channel.id, None)

    if state is None:
        await ctx.send("[*Bogin aktualnie nie grasuje w tym wątku.*]")
        return

    task = state["task"]

    if task:
        task.cancel()

    await ctx.send(
        "[*Bogin został odesłany do szafy. Zabawa została zakończona.*]"
    )


# ============================================================
# WYKLUCZENIA — FUNKCJE POMOCNICZE
# ============================================================

def can_manage_exclusions(ctx):
    if not isinstance(ctx.author, discord.Member):
        return False

    return (
        ctx.author.guild_permissions.administrator
        or any(
            role.name.casefold() == "dyrekcja"
            for role in ctx.author.roles
        )
    )


async def resolve_by_nick(ctx, query):
    """Zwraca (osoba, komunikat błędu)."""
    query = query.strip()

    if not query:
        return None, "❌ Podaj nick, np. `!wyklucz Lilith Noir`."

    if query.startswith("<@") and query.endswith(">"):
        query = query[2:-1].lstrip("!")

    if query.isdigit():
        try:
            member = await ctx.guild.fetch_member(int(query))
            return member, None
        except discord.DiscordException:
            return None, "❌ Nie znaleziono osoby o takim ID na serwerze."

    def matches_query(member):
        return (
            member.display_name.casefold() == query.casefold()
            or member.name.casefold() == query.casefold()
            or (member.global_name or "").casefold() == query.casefold()
        )

    matches = [
        member for member in ctx.guild.members
        if not member.bot and matches_query(member)
    ]

    if not matches:
        try:
            fetched = [
                member
                async for member in ctx.guild.fetch_members(limit=None)
            ]
            matches = [
                member for member in fetched
                if not member.bot and matches_query(member)
            ]
        except discord.DiscordException:
            pass

    if len(matches) == 1:
        return matches[0], None

    if len(matches) > 1:
        return (
            None,
            "⚠️ Ten nick ma kilka osób. Użyj @oznaczenia lub ID Discord.",
        )

    return (
        None,
        "❌ Nie znalazłam takiego nicku. Sprawdź pisownię "
        "albo użyj @oznaczenia.",
    )


# ============================================================
# KOMENDA !wyklucz
# ============================================================

@bot.command(name="wyklucz")
async def wyklucz(ctx, *, nick: str = ""):
    if not can_manage_exclusions(ctx):
        await ctx.send(
            "❌ Tylko Dyrekcja lub administrator może wykluczać osoby."
        )
        return

    member, error = await resolve_by_nick(ctx, nick)

    if error:
        await ctx.send(error)
        return

    if member.bot:
        await ctx.send("❌ Boty nie są losowane.")
        return

    if excluded(member.id):
        await ctx.send(
            f"✅ {member.mention} już nie może zostać zaatakowany przez Bogina."
        )
        return

    extra_exclusions.add(member.id)

    try:
        save_exclusions()
    except OSError as exc:
        extra_exclusions.discard(member.id)
        await ctx.send(f"❌ Nie udało się zapisać wykluczenia: {exc}")
        return

    await ctx.send(
        f"🚫 {member.mention} nie będzie już celem ataków Bogina."
    )


# ============================================================
# KOMENDA !przywroc
# ============================================================

@bot.command(name="przywroc")
async def przywroc(ctx, *, nick: str = ""):
    if not can_manage_exclusions(ctx):
        await ctx.send(
            "❌ Tylko Dyrekcja lub administrator może przywracać osoby."
        )
        return

    member, error = await resolve_by_nick(ctx, nick)

    if error:
        await ctx.send(error)
        return

    if member.id in EXCLUDED_USERS:
        await ctx.send(
            "🔒 Ta osoba ma stałe wykluczenie zapisane w kodzie."
        )
        return

    if member.id not in extra_exclusions:
        await ctx.send(
            f"ℹ️ {member.mention} nie jest wykluczoną osobą."
        )
        return

    extra_exclusions.remove(member.id)

    try:
        save_exclusions()
    except OSError as exc:
        extra_exclusions.add(member.id)
        await ctx.send(f"❌ Nie udało się zapisać zmiany: {exc}")
        return

    await ctx.send(
        f"✅ {member.mention} może znów zostać wylosowany przez Bogina."
    )


# ============================================================
# KOMENDA !wykluczeni
# ============================================================

@bot.command(name="wykluczeni")
async def wykluczeni(ctx):
    if not can_manage_exclusions(ctx):
        await ctx.send(
            "❌ Ta lista jest dostępna tylko dla Dyrekcji i administratorów."
        )
        return

    permanent = "\n".join(
        f"• <@{user_id}> (`{user_id}`)"
        for user_id in sorted(EXCLUDED_USERS)
    )

    additional = "\n".join(
        f"• <@{user_id}> (`{user_id}`)"
        for user_id in sorted(extra_exclusions)
    ) or "Brak"

    await ctx.send(
        f"🚫 **Wykluczeni z ataków Bogina**\n"
        f"**Na stałe:**\n{permanent}\n\n"
        f"**Dodani komendą:**\n{additional}"
    )


# ============================================================
# KOMENDA !rzut
# ============================================================

@bot.command(name="rzut")
async def rzut(ctx):
    wynik = random.randint(1, 6)

    await ctx.send(
        f"🎲 {ctx.author.mention} rzuca kością K6! "
        f"Wynik: **{wynik}**"
    )


# ============================================================
# KOMENDA !wyczyść
# ============================================================

@bot.command(name="wyczyść", aliases=["wyczysc"])
@commands.has_permissions(administrator=True)
async def wyczysc(ctx, *, nazwy_kanalow: str = None):
    if not nazwy_kanalow:
        await ctx.send(
            "Podaj nazwy kanałów oddzielone przecinkami, "
            "np. `!wyczyść ogłoszenia, pogaduchy`."
        )
        return

    if ctx.guild is None:
        return

    nazwy = [
        nazwa.strip().lstrip("#")
        for nazwa in nazwy_kanalow.split(",")
        if nazwa.strip()
    ]

    wyniki = []

    for nazwa in nazwy:
        kanal = discord.utils.find(
            lambda channel: (
                isinstance(channel, discord.TextChannel)
                and channel.name.casefold() == nazwa.casefold()
            ),
            ctx.guild.text_channels,
        )

        if kanal is None:
            wyniki.append(f"❌ Nie znaleziono kanału: `{nazwa}`")
            continue

        try:
            usuniete = await kanal.purge(limit=None, bulk=False)
            wyniki.append(
                f"✅ Wyczyściłam {kanal.mention} "
                f"({len(usuniete)} wiadomości)."
            )
        except discord.Forbidden:
            wyniki.append(
                f"⛔ Nie mam uprawnień do czyszczenia {kanal.mention}."
            )
        except discord.HTTPException as exc:
            wyniki.append(
                f"⚠️ Błąd przy czyszczeniu {kanal.mention}: {exc}"
            )

    await ctx.send("\n".join(wyniki))


@wyczysc.error
async def wyczysc_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "⛔ Ta komenda wymaga uprawnień administratora."
        )


# ============================================================
# KOMENDA !usun_watki / !usuń_wątki
# ============================================================

@bot.command(
    name="usun_watki",
    aliases=["usuń_wątki"],
)
@commands.has_permissions(administrator=True)
async def usun_watki(
    ctx,
    kanal: discord.TextChannel = None,
):
    if kanal is None:
        await ctx.send(
            "❗ Podaj kanał, np. `!usuń_wątki #nazwa-kanału`."
        )
        return

    watki = {}

    for watek in kanal.threads:
        watki[watek.id] = watek

    try:
        async for watek in kanal.archived_threads(limit=None):
            watki[watek.id] = watek

        async for watek in kanal.archived_threads(
            private=True,
            limit=None,
        ):
            watki[watek.id] = watek

    except discord.Forbidden:
        await ctx.send(
            "❌ Brak uprawnień do odczytu wątków na tym kanale."
        )
        return
    except discord.HTTPException as exc:
        await ctx.send(
            f"❌ Błąd podczas pobierania wątków: {exc}"
        )
        return

    if not watki:
        await ctx.send(
            f"📂 Nie znaleziono wątków na kanale {kanal.mention}."
        )
        return

    await ctx.send(
        f"⚠️ Znaleziono **{len(watki)}** wątków na "
        f"{kanal.mention}.\n"
        "Aby je usunąć, wpisz `TAK` w ciągu 30 sekund."
    )

    def sprawdz(message):
        return (
            message.author.id == ctx.author.id
            and message.channel.id == ctx.channel.id
            and message.content.upper() == "TAK"
        )

    try:
        await bot.wait_for(
            "message",
            check=sprawdz,
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        await ctx.send("⌛ Anulowano usuwanie wątków.")
        return

    usuniete = 0
    bledy = 0

    for watek in watki.values():
        try:
            await watek.delete(
                reason=f"Usunięcie wątków przez {ctx.author}"
            )
            usuniete += 1
        except (discord.Forbidden, discord.HTTPException) as exc:
            bledy += 1
            print(f"Nie udało się usunąć wątku {watek.id}: {exc}")

    await ctx.send(
        "🗑️ **Zakończono usuwanie wątków!**\n"
        f"✅ Usunięto: **{usuniete}**\n"
        f"❌ Nie udało się usunąć: **{bledy}**"
    )


@usun_watki.error
async def usun_watki_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "⛔ Ta komenda jest tylko dla administratorów."
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            "❗ Nie rozpoznaję kanału. Oznacz go przez #."
        )
    else:
        raise error

# ============================================================
# DODATKOWE LOGI ADMINISTRACYJNE UH
# Odejścia, wyrzucenia, bany, timeouty, nicki i rangi
# Wklej przed bot.run(TOKEN)
# ============================================================

async def uh_log_admin(guild, title, description, color, fields=None):
    """Wysyła log administracyjny na istniejący kanał logów."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )

    if fields:
        for name, value in fields:
            embed.add_field(
                name=name,
                value=str(value)[:1024],
                inline=False
            )

    embed.set_footer(text=f"Serwer: {guild.name}")

    # Korzystamy z istniejącej funkcji wysyłającej logi.
    await send_log(embed)


async def uh_audit(guild, action, target_id, seconds=20):
    """Próbuje ustalić sprawcę działania z Audit Log."""
    now = discord.utils.utcnow()

    try:
        async for entry in guild.audit_logs(limit=15, action=action):
            if getattr(entry.target, "id", None) != target_id:
                continue

            if (now - entry.created_at).total_seconds() > seconds:
                continue

            return entry

    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"[UH LOGI] Nie można odczytać Audit Log: {exc}")

    return None


def uh_actor(entry):
    if entry is None or entry.user is None:
        return "Nie udało się ustalić"

    return f"{entry.user} (`{entry.user.id}`)"


# ------------------------------------------------------------
# ODEJŚCIE LUB WYRZUCENIE
# ------------------------------------------------------------

@bot.listen("on_member_remove")
async def uh_member_leave(member):
    await asyncio.sleep(1.5)

    entry = await uh_audit(
        member.guild,
        discord.AuditLogAction.kick,
        member.id
    )

    if entry:
        await uh_log_admin(
            member.guild,
            "👢 Wyrzucenie z serwera",
            f"**Użytkownik:** {member} (`{member.id}`)\n"
            f"**Wyrzucił:** {uh_actor(entry)}\n"
            f"**Powód:** {entry.reason or 'Nie podano'}",
            discord.Color.orange()
        )
    else:
        await uh_log_admin(
            member.guild,
            "📤 Użytkownik opuścił serwer",
            f"**Użytkownik:** {member} (`{member.id}`)",
            discord.Color.dark_red()
        )


# ------------------------------------------------------------
# BAN
# ------------------------------------------------------------

@bot.listen("on_member_ban")
async def uh_member_ban(guild, user):
    await asyncio.sleep(0.7)

    entry = await uh_audit(
        guild, discord.AuditLogAction.ban, user.id
    )

    await uh_log_admin(
        guild,
        "🔨 Ban użytkownika",
        f"**Użytkownik:** {user} (`{user.id}`)\n"
        f"**Zbanował:** {uh_actor(entry)}\n"
        f"**Powód:** {entry.reason if entry and entry.reason else 'Nie podano'}",
        discord.Color.red()
    )


# ------------------------------------------------------------
# ODBANOWANIE
# ------------------------------------------------------------

@bot.listen("on_member_unban")
async def uh_member_unban(guild, user):
    await asyncio.sleep(0.7)

    entry = await uh_audit(
        guild, discord.AuditLogAction.unban, user.id
    )

    await uh_log_admin(
        guild,
        "🔓 Odbanowanie użytkownika",
        f"**Użytkownik:** {user} (`{user.id}`)\n"
        f"**Odbanował:** {uh_actor(entry)}",
        discord.Color.green()
    )


# ------------------------------------------------------------
# ZMIANA NICKU, RANGI I TIMEOUTU
# ------------------------------------------------------------

@bot.listen("on_member_update")
async def uh_member_update(before, after):
    guild = after.guild
    user_id = after.id

    # ZMIANA NICKU
    if before.nick != after.nick:
        entry = await uh_audit(
            guild,
            discord.AuditLogAction.member_update,
            user_id
        )

        await uh_log_admin(
            guild,
            "✏️ Zmiana nicku",
            f"**Użytkownik:** {after.mention} (`{user_id}`)\n"
            f"**Poprzedni nick:** {before.nick or before.name}\n"
            f"**Nowy nick:** {after.nick or after.name}\n"
            f"**Zmienił:** {uh_actor(entry)}",
            discord.Color.blue()
        )

    # NADANIE I ZDJĘCIE RANG
    old_roles = {r.id: r for r in before.roles}
    new_roles = {r.id: r for r in after.roles}

    added_roles = [
        r for rid, r in new_roles.items()
        if rid not in old_roles and not r.is_default()
    ]

    removed_roles = [
        r for rid, r in old_roles.items()
        if rid not in new_roles and not r.is_default()
    ]

    if added_roles or removed_roles:
        entry = await uh_audit(
            guild,
            discord.AuditLogAction.member_role_update,
            user_id
        )

        for role in added_roles:
            await uh_log_admin(
                guild,
                "🎭 Nadanie rangi",
                f"**Komu:** {after.mention} (`{user_id}`)\n"
                f"**Ranga:** {role.name}\n"
                f"**Nadał:** {uh_actor(entry)}",
                discord.Color.green()
            )

        for role in removed_roles:
            await uh_log_admin(
                guild,
                "🗑️ Zdjęcie rangi",
                f"**Komu:** {after.mention} (`{user_id}`)\n"
                f"**Ranga:** {role.name}\n"
                f"**Zdjął:** {uh_actor(entry)}",
                discord.Color.orange()
            )

    # TIMEOUT / WYCISZENIE CZASOWE
    old_timeout = before.timed_out_until
    new_timeout = after.timed_out_until

    if old_timeout != new_timeout:
        entry = await uh_audit(
            guild,
            discord.AuditLogAction.member_update,
            user_id
        )

        if new_timeout is not None:
            await uh_log_admin(
                guild,
                "🔇 Wyciszenie czasowe",
                f"**Komu:** {after.mention} (`{user_id}`)\n"
                f"**Do:** {discord.utils.format_dt(new_timeout, style='F')}\n"
                f"**Sprawca:** {uh_actor(entry)}\n"
                f"**Powód:** {entry.reason if entry and entry.reason else 'Nie podano'}",
                discord.Color.orange()
            )
        else:
            await uh_log_admin(
                guild,
                "🔊 Zdjęcie wyciszenia czasowego",
                f"**Komu:** {after.mention} (`{user_id}`)\n"
                f"**Zdjął:** {uh_actor(entry)}",
                discord.Color.green()
            )


# ============================================================
# URUCHOMIENIE — TYLKO RAZ, NA KOŃCU PLIKU
# ============================================================

bot.run(TOKEN)
