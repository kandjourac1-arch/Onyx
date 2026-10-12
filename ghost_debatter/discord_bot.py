"""
DISCORD CONNECTOR FOR ONYX
Fichier : discord_bot.py
"""

import os
import discord
from dotenv import load_dotenv
from main import EliteLegalCabinetOrchestrator

# Chargement du fichier .env s'il existe
load_dotenv()

# Token de connexion Discord (lit le .env en priorité, sinon prend la valeur par défaut)
TOKEN = os.getenv(
    "DISCORD_TOKEN",
    "MTU0MTUwNDAzNzMxMTIxNzczNA.G3q0we.l83UW0ownA0EpQy_NstYi_TgLcT-zjkFfDOCkI"
)

# Configuration des permissions du bot
intents = discord.Intents.default()
intents.message_content = True  # Permet au bot de lire les messages

bot = discord.Client(intents=intents)
onyx = EliteLegalCabinetOrchestrator()


@bot.event
async def on_ready():
    print(f"✅ Onyx est en ligne sur Discord sous l'identifiant : {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    # Évite que le bot ne réponde à ses propres messages
    if message.author == bot.user:
        return

    # Répond si le bot est mentionné (@Onyx) ou en message privé (DM)
    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        # Retire la mention <@ID> pour ne garder que le texte de la question
        clean_text = (
            message.content.replace(f"<@{bot.user.id}>", "")
            .replace(f"<@!{bot.user.id}>", "")
            .strip()
        )

        if not clean_text:
            await message.channel.send("Bonjour ! En quoi puis-je vous aider aujourd'hui ?")
            return

        async with message.channel.typing():
            # Traitement de la demande via l'orchestrateur Onyx
            response = await onyx.process_request(clean_text)

        # Découpage si la réponse dépasse la limite de 2000 caractères de Discord
        if len(response) > 2000:
            chunks = [response[i:i + 1900] for i in range(0, len(response), 1900)]
            for chunk in chunks:
                await message.channel.send(chunk)
        else:
            await message.channel.send(response)


if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("❌ Le TOKEN Discord est manquant.")
    bot.run(TOKEN)