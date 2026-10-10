import os
import random
import asyncio
import discord
from discord.ext import commands

# ============================================================
# USTAWIENIA HOSTINGU
# ============================================================

TOKEN = os.getenv("MTU1ODU3MTkxMjg0MDYxODAxNg.GpTLnF.v2JGbpMRrW5EsJhSEMP1GsFrvPvqaE4JC_BkJ8")
THREAD_ID = int(os.getenv("THREAD_ID", "0"))

if not TOKEN:
    raise RuntimeError("Brak zmiennej DISCORD_TOKEN w ustawieniach hostingu!")
if THREAD_ID == 0:
    raise RuntimeError("Ustaw prawidłową zmienną THREAD_ID w hostingu!")

EXCLUDED_USERS = {
    1558587320461164678,
    1558559995052818573,
}

BOGIN_FORMS = [
    "Klaun", "Severus Snape", "Lord Voldemort", "Pełnia",
    "Alishia Farias", "Akromantula", "Dementor", "Wąż",
    "Lilith Noir", "Smok", "Egzamin", "Śmierciotula",
    "Inferius", "Oni",
]

# ============================================================
# DISCORD I STAN GRY
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)

game_task = None
riddikulus_active = False
riddikulus_event = asyncio.Event()


def is_running():
    return game_task is not None and not game_task.done()


async def get_players(thread: discord.Thread):
    """Pobierz rzeczywistych użytkowników wątku, nie obiekty ThreadMember."""
    try:
        thread_members = await thread.fetch_members()
    except (discord.HTTPException, discord.Forbidden) as error:
        print(f"Nie udało się pobrać członków wątku: {error}")
        return []

    players = []
    for thread_member in thread_members:
        if thread_member.id in EXCLUDED_USERS:
            continue
        member = thread.guild.get_member(thread_member.id)
        if member is None:
            try:
                member = await thread.guild.fetch_member(thread_member.id)
            except (discord.HTTPException, discord.Forbidden, discord.NotFound):
                continue
        if member.bot:
            continue
        players.append(member)
    return players


async def countdown(thread):
    """Zwraca True, jeżeli ktokolwiek wpisze !riddikulus przed końcem liczenia."""
    global riddikulus_active
    riddikulus_event.clear()
    riddikulus_active = True
    try:
        for number in (3, 2, 1, 0):
            # Jeżeli zaklęcie wpłynęło pomiędzy dwiema wiadomościami:
            if riddikulus_event.is_set():
                return True
            await thread.send(str(number))
            try:
                await asyncio.wait_for(riddikulus_event.wait(), timeout=1.0)
                return True
            except asyncio.TimeoutError:
                pass
        return riddikulus_event.is_set()
    finally:
        riddikulus_active = False


async def run_game(thread):
    """Jedna pętla zamiast rekurencyjnego uruchamiania rund."""
    global game_task, riddikulus_active
    try:
        while True:
            players = await get_players(thread)
            if not players:
                await thread.send(
                    "[*W wątku nie ma żadnej dostępnej osoby, "
                    "którą Bogin mógłby zaatakować.*]"
                )
                return

            target = random.choice(players)
            form = random.choice(BOGIN_FORMS)
            await thread.send(
                f"[*Bogin przybrał formę {form} i zaczął zbliżać się "
                f"do {target.mention}. By obezwładnić Bogina, użyj "
                f"komendy !Riddikulus bez kropki.*]"
            )

            attempt = 0
            while True:
                attempt += 1
                if await countdown(thread):
                    await thread.send(
                        "[*Po udanej próbie obezwładnienia Bogin wrócił do szafy.*]"
                    )
                    break
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

            await asyncio.sleep(5)
    except asyncio.CancelledError:
        raise
    except discord.DiscordException as error:
        print(f"Błąd komunikacji z Discordem: {error}")
    except Exception as error:
        print(f"Błąd podczas gry: {error}")
        raise
    finally:
        riddikulus_active = False
        riddikulus_event.clear()
        if game_task is asyncio.current_task():
            game_task = None


@bot.command(name="start")
async def start(ctx):
    global game_task
    if ctx.channel.id != THREAD_ID:
        return
    if is_running():
        await ctx.send("[*Bogin już grasuje! Najpierw trzeba go pokonać.*]")
        return
    game_task = asyncio.create_task(run_game(ctx.channel))


@bot.command(name="riddikulus")
async def riddikulus(ctx):
    if ctx.channel.id != THREAD_ID:
        return
    if is_running() and riddikulus_active:
        riddikulus_event.set()


@bot.command(name="stop")
async def stop(ctx):
    global game_task, riddikulus_active
    if ctx.channel.id != THREAD_ID:
        return
    if not is_running():
        await ctx.send("[*Bogin aktualnie nie grasuje.*]")
        return
    task = game_task
    game_task = None
    riddikulus_active = False
    riddikulus_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await ctx.send(
        "[*Bogin został odesłany do szafy. Zabawa została zakończona.*]"
    )


@bot.event
async def on_ready():
    print("--------------------------------------")
    print(f"Zalogowano jako: {bot.user}")
    print("Bogin jest gotowy do zabawy!")
    print("--------------------------------------")


bot.run(TOKEN)
