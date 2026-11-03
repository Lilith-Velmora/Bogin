for rdzen in NORMALNE_PRZEKLENSTWA:
        if rdzen and rdzen in normalny:
            return True

    # Dodatkowe sprawdzanie słów oddzielonych spacjami,
    # np. "q w a" albo "k u r w a".
    slowa = re.findall(r"[^\W_]+", tekst.casefold(), flags=re.UNICODE)

    if len(slowa) >= 3:
        for dlugosc in range(3, min(len(slowa), 12) + 1):
            for start in range(len(slowa) - dlugosc + 1):
                fragment = "".join(slowa[start:start + dlugosc])
                fragment = normalizuj_tekst(fragment)

                if fragment in NORMALNE_PRZEKLENSTWA:
                    return True

    return False


# Komunikat wysyłany po usunięciu wiadomości
KOMUNIKAT_HUNCWOTKA = (
    "Huncwotek wyłonił się z mroku i spryskał "
    "{osoba} wodą. Co to za słownictwo?! "
    "Proszę zwracać uwagę na używany język! 💦"
)


@bot.listen("on_message")
async def huncwotek_straznik_jezyka(message: discord.Message):
    # Ignorujemy boty
    if message.author.bot:
        return

    # Ignorujemy wiadomości prywatne
    if message.guild is None:
        return

    # Sprawdzamy, czy autor ma rangę odporną na filtr
    role_uzytkownika = {
        role.name.casefold()
        for role in getattr(message.author, "roles", [])
    }

    if role_uzytkownika & ROLE_IMMUNITETU_HUNCWOTKA:
        return

    # Puste wiadomości i wiadomości bez tekstu pomijamy
    if not message.content:
        return

    # Jeśli nie wykryto przekleństwa, nic nie robimy
    if not zawiera_przeklenstwo(message.content):
        return

    # Usuwamy wiadomość
    try:
        await message.delete()

    except discord.Forbidden:
        print("[HUNCWOTEK] Brak uprawnienia Manage Messages.")
        return

    except discord.NotFound:
        return

    except discord.HTTPException as error:
        print(f"[HUNCWOTEK] Błąd usuwania wiadomości: {error}")
        return

    # Wysyłamy ostrzeżenie na tym samym kanale
    try:
        await message.channel.send(
            KOMUNIKAT_HUNCWOTKA.format(
                osoba=message.author.mention
            ),
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
            ),
        )

    except discord.HTTPException as error:
        print(f"[HUNCWOTEK] Błąd wysyłania ostrzeżenia: {error}")

@bot.command(name="Cerber")
async def cerber(ctx):
    await ctx.send(
        "[*Huncwotek spuścił Cerbera ze smyczy, a ten od razu zaczął gonić Lillianę*]"
    )

# Dodatkowe komendy korzystają z tego samego obiektu `bot`,
# utworzonego na początku pliku. Nie tworzymy drugiego bota.

@bot.command()
async def uratujucz(ctx):
    odpowiedzi = [
        "*Lecisz już na hipogryfie, niestety lądujesz w złej części Azkabanu i łapią Cię dementorzy.* **Otrzymujesz 5 punktów - za dobre chęci.**",
        "*Przylatuje po Ciebie hipogryf, wsiadasz na niego i lecisz do Azkabanu.* **Otrzymujesz 10 punktów!**"
    ]
    await ctx.send(random.choice(odpowiedzi))

@bot.command()
async def uratujprof(ctx):
    odpowiedzi = [
        "*Lecisz już na hipogryfie, niestety lądujesz w złej części Azkabanu i łapią Cię dementorzy.* **Otrzymujesz 3 punkty - za dobre chęci.**",
        "*Przylatuje po Ciebie hipogryf, wsiadasz na niego i lecisz do Azkabanu.* **Otrzymujesz 6 punktów!**"
    ]
    await ctx.send(random.choice(odpowiedzi))

@bot.command()
async def labirynt(ctx):
    await ctx.send("*[Podbiega szybko i staje obok, wręczając Ci po cichu kawałek [pergaminu](https://jpcdn.it/img/small/928a8cb8722b65fa9bb59856cf15e0e7.webp)].* **Oto dzisiejszy labirynt! Nie zapomnij tylko odesłać wypełnionego poprzez formularz!** *[Podaje mu następny [pergamin](https://tiny.pl/dx98w) i zadowolony wraca do swojej wcześniejszej zabawy.]*")

@bot.command()
async def zagadka(ctx):
    await ctx.send("*[Podbiega szybko i staje przed tobą, kaszląc dwa razy.]* ***Czekasz na zagadkę? No dobrze… Oto dzisiejsza!***\n`Pokazuje każdy zakamarek Hogwartu, w tym tajne przejścia oraz to, gdzie aktualnie znajduje się każdy człowiek w szkole. Można ją aktywować tylko za pomocą specjalnych słów, a po użyciu trzeba ją odpowiednimi słowami zamknąć. Co to?`\n***Nie zapomnij o odpowiedzi! Masz tu jeszcze formularz na to.*** *[Podaje szybko części [pergaminu](https://tiny.pl/dxp66)].*")

# Korzystamy z pierwszego on_ready() zdefiniowanego wyżej.

# ============================================================
# URUCHOMIENIE — TYLKO RAZ, NA KOŃCU PLIKU
# ============================================================

bot.run(TOKEN)
