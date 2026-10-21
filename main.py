import os
import random
import asyncio
import json
from pathlib import Path
import discord
from discord.ext import commands

# ============================================================
# USTAWIENIA HOSTINGU
# ============================================================
# W hostingu ustaw zmienną DISCORD_TOKEN z nowym tokenem bota.
# Nie wpisuj tokena bezpośrednio w tym pliku.
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Brak zmiennej DISCORD_TOKEN w ustawieniach hostingu!")

# Te trzy osoby NIGDY nie będą celem ataku Bogina.
# Nadal mogą normalnie używać zaklęcia !Riddikulus.
EXCLUDED_USERS = {
    1558587320461164678,
    1558559995052818573,
}

# Dodatkowe wykluczenia można zarządzać z Discorda po nicku.
# Wykluczenia zapisują się w pliku i pozostają po restarcie.
EXCLUSIONS_FILE = Path(os.getenv("BOGIN_EXCLUSIONS_FILE", "bogin_wykluczeni.json"))


def load_exclusions():
    try:
        if EXCLUSIONS_FILE.exists():
            data = json.loads(EXCLUSIONS_FILE.read_text(encoding="utf-8"))
            return {int(x) for x in data if str(x).isdigit()}
    except (OSError, ValueError, TypeError) as exc:
        print(f"Nie udało się wczytać wykluczeń: {exc}")
    return set()


def save_exclusions():
    tmp = EXCLUSIONS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(extra_exclusions), indent=2), encoding="utf-8")
    tmp.replace(EXCLUSIONS_FILE)


extra_exclusions = load_exclusions()


def excluded(user_id):
    return user_id in EXCLUDED_USERS or user_id in extra_exclusions


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

# ============================================================
# DISCORD
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)

# Każdy wątek może mieć własną niezależną grę.
# thread_id -> {"task": Task, "response": asyncio.Event}
games = {}


def is_thread(channel):
    return isinstance(channel, discord.Thread)


async def get_players(thread):
    """Zwróć prawdziwych członków wątku bez wykluczonych użytkowników."""
    try:
        # discord.py: Thread.fetch_members zwraca ThreadMember, a nie Member.
        thread_members = await thread.fetch_members()
    except discord.DiscordException as exc:
        print(f"Nie udało się pobrać uczestników wątku {thread.id}: {exc}")
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
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue
        if member.bot or excluded(member.id):
            continue
        players.append(member)
    return players


async def countdown(thread, state):
    """Zwraca True po poprawnym zaklęciu, False po odliczaniu."""
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
    """Pętla gry uruchamiana osobno dla każdego wątku."""
    try:
        while True:
            players = await get_players(thread)
            if players is None:
                await thread.send("[*Nie mogę pobrać listy uczestników wątku. Sprawdź uprawnienia bota.*]")
                return
            if not players:
                await thread.send("[*Nie ma w tym wątku dostępnych osób, które Bogin może zaatakować.*]")
                return

            target = random.choice(players)
            # Dodatkowa kontrola bezpieczeństwa przed wysłaniem ataku.
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
                    await thread.send("[*Po udanej próbie obezwładnienia Bogin wrócił do szafy.*]")
                    await asyncio.sleep(5)
                    break
                attempt += 1
                if attempt == 1:
                    await thread.send(
                        "[*Niestety zaklęcie nie zadziałało, a Bogin zaczął "
                        "zbierać się do ataku. Szybko ponów zaklęcie!*]"
                    )
                elif attempt == 2:
                    await thread.send(
                        "[*Niestety zaklęcie ponownie nie zadziałało, "
                        "a Bogin jest coraz bliżej! Szybko ponów zaklęcie!*]"
                    )
                else:
                    await thread.send(
                        "[*Niestety zaklęcie nadal nie zadziałało! "
                        "Bogin szykuje się do ataku. Szybko ponów zaklęcie!*]"
                    )
    except asyncio.CancelledError:
        raise
    except discord.DiscordException as exc:
        print(f"Błąd Discord podczas gry w wątku {thread.id}: {exc}")
    except Exception as exc:
        print(f"Błąd gry w wątku {thread.id}: {exc}")
    finally:
        if games.get(thread.id) is state:
            games.pop(thread.id, None)


@bot.command(name="start")
async def start(ctx):
    if not is_thread(ctx.channel):
        await ctx.send("[*Zabawę z Boginem można rozpocząć tylko we wątku.*]")
        return
    if ctx.channel.id in games:
        await ctx.send("[*Bogin już grasuje w tym wątku!*]")
        return
    state = {"response": asyncio.Event(), "task": None}
    games[ctx.channel.id] = state
    state["task"] = asyncio.create_task(run_game(ctx.channel, state))


@bot.command(name="riddikulus")
async def riddikulus(ctx):
    if not is_thread(ctx.channel):
        return
    state = games.get(ctx.channel.id)
    if state and state["task"] and not state["task"].done():
        # Nie rejestrujemy zaklęć pomiędzy rundami.
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
    await ctx.send("[*Bogin został odesłany do szafy. Zabawa została zakończona.*]")


# Komendy moderacyjne: tylko Dyrekcja (rola) lub administrator serwera.
def can_manage_exclusions(ctx):
    if not isinstance(ctx.author, discord.Member):
        return False
    return (ctx.author.guild_permissions.administrator or
            any(role.name.casefold() == "dyrekcja" for role in ctx.author.roles))


async def resolve_by_nick(ctx, query):
    """Zwraca (osoba, komunikat). Akceptuje @wzmiankę, ID lub dokładny nick."""
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
    # Najpierw dokładny nick / nazwa wyświetlana, później dokładna nazwa konta.
    members = ctx.guild.members
    matches = [m for m in members if not m.bot and
               (m.display_name.casefold() == query.casefold() or
                m.name.casefold() == query.casefold() or
                (m.global_name or "").casefold() == query.casefold())]
    if not matches:
        # Przy ograniczonej pamięci podręcznej spróbuj pobrać pełną listę członków.
        try:
            fetched = [m async for m in ctx.guild.fetch_members(limit=None)]
            matches = [m for m in fetched if not m.bot and
                       (m.display_name.casefold() == query.casefold() or
                        m.name.casefold() == query.casefold() or
                        (m.global_name or "").casefold() == query.casefold())]
        except discord.DiscordException:
            pass
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, "⚠️ Ten nick ma kilka osób. Użyj @oznaczenia lub ID Discord."
    return None, "❌ Nie znalazłam takiego nicku. Sprawdź pisownię albo użyj @oznaczenia."


@bot.command(name="wyklucz")
async def wyklucz(ctx, *, nick: str = ""):
    if not can_manage_exclusions(ctx):
        await ctx.send("❌ Tylko Dyrekcja lub administrator może wykluczać osoby.")
        return
    member, error = await resolve_by_nick(ctx, nick)
    if error:
        await ctx.send(error)
        return
    if member.bot:
        await ctx.send("❌ Boty nie są losowane.")
        return
    if excluded(member.id):
        await ctx.send(f"✅ {member.mention} już nie może zostać zaatakowany przez Bogina.")
        return
    extra_exclusions.add(member.id)
    try:
        save_exclusions()
    except OSError as exc:
        extra_exclusions.discard(member.id)
        await ctx.send(f"❌ Nie udało się zapisać wykluczenia: {exc}")
        return
    await ctx.send(f"🚫 {member.mention} nie będzie już celem ataków Bogina.")


@bot.command(name="przywroc")
async def przywroc(ctx, *, nick: str = ""):
    if not can_manage_exclusions(ctx):
        await ctx.send("❌ Tylko Dyrekcja lub administrator może przywracać osoby.")
        return
    member, error = await resolve_by_nick(ctx, nick)
    if error:
        await ctx.send(error)
        return
    if member.id in EXCLUDED_USERS:
        await ctx.send("🔒 Ta osoba ma stałe wykluczenie zapisane w kodzie.")
        return
    if member.id not in extra_exclusions:
        await ctx.send(f"ℹ️ {member.mention} nie jest wykluczoną osobą.")
        return
    extra_exclusions.remove(member.id)
    try:
        save_exclusions()
    except OSError as exc:
        extra_exclusions.add(member.id)
        await ctx.send(f"❌ Nie udało się zapisać zmiany: {exc}")
        return
    await ctx.send(f"✅ {member.mention} może znów zostać wylosowany przez Bogina.")


@bot.command(name="wykluczeni")
async def wykluczeni(ctx):
    if not can_manage_exclusions(ctx):
        await ctx.send("❌ Ta lista jest dostępna tylko dla Dyrekcji i administratorów.")
        return
    permanent = "\n".join(f"• <@{user_id}> (`{user_id}`)" for user_id in sorted(EXCLUDED_USERS))
    additional = "\n".join(f"• <@{user_id}> (`{user_id}`)" for user_id in sorted(extra_exclusions)) or "Brak"
    await ctx.send(f"🚫 **Wykluczeni z ataków Bogina**\n**Na stałe:**\n{permanent}\n\n**Dodani komendą:**\n{additional}")


@bot.command(name="rzut")
async def rzut(ctx):
    wynik = random.randint(1, 6)
    await ctx.send(
        f"🎲 {ctx.author.mention} rzuca kością K6! "
        f"Wynik: **{wynik}**"
    )


@bot.command(name="wyczyść")
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

    nazwy = [n.strip().lstrip("#") for n in nazwy_kanalow.split(",")]
    wyniki = []

    for nazwa in nazwy:
        kanal = discord.utils.find(
            lambda c: isinstance(c, discord.TextChannel)
            and c.name.casefold() == nazwa.casefold(),
            ctx.guild.text_channels
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
        except discord.HTTPException:
            wyniki.append(
                f"⚠️ Wystąpił błąd przy czyszczeniu {kanal.mention}."
            )

    await ctx.send("\n".join(wyniki)


@wyczysc.error
async def wyczysc_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("⛔ Ta komenda wymaga uprawnień administratora.")

@bot.command(name="usun_watki")
@commands.has_permissions(administrator=True)
async def usun_watki(ctx, kanal: discord.TextChannel = None):
    if kanal is None:
        await ctx.send(
            "❗ Podaj kanał, np. `!usuń_wątki #nazwa-kanału`."
        )
        return

    # Zbierz aktywne i zarchiwizowane wątki
    watki = {}

    for watek in kanal.threads:
        watki[watek.id] = watek

    try:
        async for watek in kanal.archived_threads(limit=None):
            watki[watek.id] = watek

        # Dodaj dostępne zarchiwizowane wątki prywatne
        async for watek in kanal.archived_threads(
            private=True, limit=None
        ):
            watki[watek.id] = watek

    except discord.Forbidden:
        await ctx.send(
            "❌ Brak uprawnień do odczytu wątków na tym kanale."
        )
        return
    except discord.HTTPException as e:
        await ctx.send(f"❌ Błąd podczas pobierania wątków: {e}")
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

    def sprawdz(m):
        return (
            m.author.id == ctx.author.id
            and m.channel.id == ctx.channel.id
            and m.content.upper() == "TAK"
        )

    try:
        await bot.wait_for(
            "message", check=sprawdz, timeout=30.0
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
        except (discord.Forbidden, discord.HTTPException):
            bledy += 1

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

import discord
from discord.ext import commands

import sqlite3
import discord
from discord.ext import commands

# --- KONFIGURACJA BAZY DANYCH ---
def init_db():
    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
    # Tabela do przechowywania ID wiadomości oraz jej treści
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY,
            content TEXT,
            author_id INTEGER,
            channel_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- KONFIGURACJA BOTA ---
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ID kanału logów (zmień na swoje)
LOG_CHANNEL_ID = 1562477162882269315

@bot.event
async def on_ready():
    print(f'Zalogowano jako {bot.user.name} (ID: {bot.user.id})')
    print('Bot z bazą danych SQLite jest gotowy!')

# Zapisywanie każdej nowej wiadomości do bazy danych
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
   cursor.execute('''
        INSERT OR IGNORE INTO messages (message_id, content, author_id, channel_id)
        VALUES (?, ?, ?, ?)
    ''', (message.id, message.content, message.author.id, message.channel.id))

    conn.commit()
    conn.close()

    # Ważne: pozwala botowi przetwarzać również inne eventy/komendy
    await bot.process_commands(message)

# Event: Usunięta wiadomość (pobiera treść z bazy danych)
@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return

    # Pobieranie treści z bazy danych
    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
    cursor.execute('SELECT content FROM messages WHERE message_id = ?', (message.id,))
    row = cursor.fetchone()
    conn.close()

    # Jeśli wiadomość była w bazie, bierzemy jej treść, w przeciwnym razie fallback
    content = row[0] if row and row[0] else (message.content if message.content else "Brak treści tekstowej / załącznik")

    embed = discord.Embed(
        title="🗑️ Usunięto wiadomość",
        color=discord.Color.red(),
        timestamp=message.created_at
    )
    embed.add_field(name="Autor", value=f"{message.author} (ID: {message.author.id})", inline=False)
    embed.add_field(name="Kanał", value=message.channel.mention, inline=False)
    embed.add_field(name="Treść", value=content, inline=False)
    
    await log_channel.send(embed=embed)

# Event: Edytowana wiadomość
@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return

    embed = discord.Embed(
        title="✏️ Edytowano wiadomość",
        color=discord.Color.orange(),
        timestamp=after.edited_at if after.edited_at else discord.utils.utcnow()
    )
    embed.add_field(name="Autor", value=f"{before.author} (ID: {before.author.id})", inline=False)
    embed.add_field(name="Kanał", value=before.channel.mention, inline=False)
    embed.add_field(name="Przed edycją", value=before.content if before.content else "Brak", inline=False)
    embed.add_field(name="Po edycji", value=after.content if after.content else "Brak", inline=False)
    embed.add_field(name="Link", value=f"[Przejdź do wiadomości]({after.jump_url})", inline=False)

    await log_channel.send(embed=embed)
@bot.event
async def on_ready():
    print("--------------------------------------")
    print(f"Zalogowano jako: {bot.user}")
    print("Bogin jest gotowy do zabawy w dowolnym wątku!")
    print("--------------------------------------")


bot.run(TOKEN)
