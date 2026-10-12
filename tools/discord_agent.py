# tools/discord_agent.py
import asyncio
import threading
import discord


class OnyxDiscordBot(discord.Client):

    def __init__(self, synapse_engine, authorized_user_id: int | None = None):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.synapse = synapse_engine
        self.authorized_user_id = (
            authorized_user_id  # Sécurité : répond uniquement à ton ID Discord
        )

    async def on_ready(self):
        print(
            f"🟢 [ONYX Discord Agent] Connecté avec succès en tant que : {self.user.name}"
        )

    async def on_message(self, message: discord.Message):
        # Ignore ses propres messages
        if message.author == self.user:
            return

        # Sécurité : filtre uniquement tes messages si un ID est spécifié
        if (
            self.authorized_user_id
            and message.author.id != self.authorized_user_id
        ):
            return

        # Indique qu'ONYX écrit dans le salon Discord
        async with message.channel.typing():
            loop = asyncio.get_event_loop()
            # Inférence SYNAPSE exécutée dans un thread pour ne pas geler Discord
            response = await loop.run_in_executor(
                None, self.synapse.generate_response, message.content
            )

            # Découpage si la réponse dépasse la limite Discord (2000 caractères)
            if len(response) > 2000:
                for chunk in [
                    response[i : i + 1900]
                    for i in range(0, len(response), 1900)
                ]:
                    await message.channel.send(chunk)
            else:
                await message.channel.send(response)


def launch_discord_bridge(
    synapse_engine, token: str, authorized_user_id: int | None = None
):
    """Démarre le bot Discord en arrière-plan dans un thread dédié."""
    bot = OnyxDiscordBot(
        synapse_engine, authorized_user_id=authorized_user_id
    )
    bot_thread = threading.Thread(
        target=bot.run, args=(token,), daemon=True
    )
    bot_thread.start()
    return bot