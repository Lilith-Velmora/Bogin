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


@bot.event
async def on_ready():
    print("--------------------------------------")
    print(f"Zalogowano jako: {bot.user}")
    print("Bogin jest gotowy do zabawy w dowolnym wątku!")
    print("--------------------------------------")


bot.run(TOKEN)
