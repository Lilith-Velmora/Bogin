import os
import random
import asyncio
from dataclasses import dataclass, field

import discord
from discord.ext import commands

# Token ustaw w zmiennej DISCORD_TOKEN w panelu hostingu.
# THREAD_ID nie jest potrzebny: Bogin działa w dowolnym wątku.
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Brak zmiennej DISCORD_TOKEN w ustawieniach hostingu!")

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

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)


@dataclass
class GameState:
    task: asyncio.Task | None = None
    riddikulus_active: bool = False
    riddikulus_event: asyncio.Event = field(default_factory=asyncio.Event)


# Niezależna gra w każdym wątku (kluczem jest ID wątku).
games: dict[int, GameState] = {}


def is_thread(ctx):
    return isinstance(ctx.channel, discord.Thread)


async def get_players(thread: discord.Thread):
    try:
        thread_members = await thread.fetch_members()
    except (discord.HTTPException, discord.Forbidden) as error:
        print(f"Nie udało się pobrać członków wątku {thread.id}: {error}")
        return []

    players = []
    for thread_member in thread_members:
        if thread_member.id in EXCLUDED_USERS:
            continue
        member = thread.guild.get_member(thread_member.id)
        if member is None:
            try:
                member = await thread.guild.fetch_member(thread_member.id)
            except (discord.HTTPException, discord.Forbidden):
                continue
        if not member.bot:
            players.append(member)
    return players


async def countdown(thread: discord.Thread, state: GameState):
    state.riddikulus_event.clear()
    state.riddikulus_active = True
    try:
        for number in (3, 2, 1, 0):
            if state.riddikulus_event.is_set():
                return True
            await thread.send(str(number))
            try:
                await asyncio.wait_for(state.riddikulus_event.wait(), timeout=1.0)
                return True
            except asyncio.TimeoutError:
                pass
        return state.riddikulus_event.is_set()
    finally:
        state.riddikulus_active = False


async def run_game(thread: discord.Thread, state: GameState):
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
                if await countdown(thread, state):
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
        print(f"Błąd komunikacji z Discordem we wątku {thread.id}: {error}")
    except Exception as error:
        print(f"Błąd Bogina we wątku {thread.id}: {error}")
        raise
    finally:
        state.riddikulus_active = False
        state.riddikulus_event.clear()
        if games.get(thread.id) is state:
            games.pop(thread.id, None)


@bot.command(name="start")
async def start(ctx):
    if not is_thread(ctx):
        await ctx.send("[*Bogina można uruchomić tylko w wątku Discorda.*]")
        return
    if ctx.channel.id in games:
        await ctx.send("[*Bogin już grasuje w tym wątku!*]")
        return
    state = GameState()
    games[ctx.channel.id] = state
    state.task = asyncio.create_task(run_game(ctx.channel, state))


@bot.command(name="riddikulus")
async def riddikulus(ctx):
    if not is_thread(ctx):
        return
    state = games.get(ctx.channel.id)
    if state and state.riddikulus_active:
        state.riddikulus_event.set()


@bot.command(name="stop")
async def stop(ctx):
    if not is_thread(ctx):
        await ctx.send("[*Komenda !stop działa tylko w wątku Discorda.*]")
        return
    state = games.get(ctx.channel.id)
    if state is None:
        await ctx.send("[*Bogin aktualnie nie grasuje w tym wątku.*]")
        return
    task = state.task
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await ctx.send("[*Bogin został odesłany do szafy. Zabawa została zakończona.*]")


@bot.event
async def on_ready():
    print("--------------------------------------")
    print(f"Zalogowano jako: {bot.user}")
    print("Bogin jest gotowy do zabawy w dowolnym wątku!")
    print("--------------------------------------")


bot.run(TOKEN)
