import asyncio
import json
from configparser import ConfigParser
from os import listdir
from time import monotonic

import asyncpg
import discord
from aiohttp import ClientSession
from discord.ext import commands

from utils import basic, cache, settings

print("Starting TTS Bot!")

start_time = monotonic()
config = ConfigParser()
config.read("config.ini")
t = config["Main"]["Token"]
config_channels = config["Channels"]

cache_key_str = config["Main"]["key"][2:-1]
cache_key_bytes = cache_key_str.encode()

# Define bot and remove overwritten commands
activity = discord.Activity(name=config["Activity"]["name"], type=getattr(discord.ActivityType, config["Activity"]["type"]))
intents = discord.Intents(voice_states=True, messages=True, guilds=True, members=True)
status = getattr(discord.Status, config["Activity"]["status"])


async def prefix(client: discord.Client, message: discord.Message) -> str:
    """
    gets the prefix for a guild based on the passed message object
    """
    return await client.settings.get(message.guild, "prefix")


bot = commands.AutoShardedBot(
    status=status,
    intents=intents,
    help_command=None, # Replaced by FancyHelpCommand by FancyHelpCommandCog
    activity=activity,
    command_prefix=prefix,
    case_insensitive=True,
    chunk_guilds_at_startup=False,
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False)
)

pool = bot.loop.run_until_complete(
    asyncpg.create_pool(
        host=config["PostgreSQL Info"]["ip"],
        user=config["PostgreSQL Info"]["name"],
        database=config["PostgreSQL Info"]["db"],
        password=config["PostgreSQL Info"]["pass"]
    )
)

bot.queue = dict()
bot.channels = dict()
bot.should_return = dict()
bot.message_locks = dict()
bot.currently_playing = dict()
bot.session = ClientSession()
bot.settings = settings.settings_class(pool)
bot.setlangs = settings.setlangs_class(pool)
bot.nicknames = settings.nickname_class(pool)
bot.cache = cache.cache(cache_key_bytes, pool)
bot.blocked_users = settings.blocked_users_class(pool)
bot.trusted = basic.remove_chars(config["Main"]["trusted_ids"], "[", "]", "'").split(", ")

with open("patreon_users.json") as f:
    bot.patreon_json = json.load(f) 

for cog in listdir("cogs"):
    if cog.endswith(".py"):
        bot.load_extension(f"cogs.{cog[:-3]}")
        print(f"Successfully loaded: {cog}")

@bot.check
async def premium_check(ctx):
    if not ctx.guild:
        return True

    if str(ctx.author.id) in bot.trusted:
        return True

    if str(ctx.command) == "donate":
        return True

    premium_user_for_guild = bot.patreon_json.get(str(ctx.guild.id))
    if premium_user_for_guild in (member.id for member in bot.patreon_role.members):
        return True

    permissions = ctx.channel.permissions_for(ctx.guild.me)
    if permissions.send_messages:
        if permissions.embed_links:
            embed = discord.Embed(
                title="TTS Bot Premium",
                description=f"Hey! This server isn't premium! Please purchase TTS Bot Premium via Patreon! (`{ctx.prefix}donate`)",
            )
            embed.set_footer(text="If this is an error, please contact Gnome!#6669.")
            embed.set_thumbnail(url=bot.user.avatar_url)

            await ctx.send(embed=embed)
        else:
            await ctx.send(f"Hey! This server isn't premium! Please purchase TTS Bot premium via Patreon! (`{ctx.prefix}donate`)\n*If this is an error, please contact Gnome!#6669.*")

@bot.event
async def on_ready():
    await bot.wait_until_ready()

    support_server_id = int(config["Main"]["main_server"])
    bot.supportserver = bot.get_guild(support_server_id)

    while bot.supportserver is None:
        print("Waiting 5 seconds")
        await asyncio.sleep(5)
        bot.supportserver = bot.get_guild(support_server_id)

    for channel_name in config_channels:
        channel_id = int(config_channels[channel_name])
        channel_object = bot.supportserver.get_channel(channel_id)
        bot.channels[channel_name] = channel_object

    try:
        await bot.starting_message.edit(content=f"~~{bot.starting_message.content}~~")
        bot.starting_message = await bot.channels["logs"].send(f"Restarted as {bot.user.name}!")
    except AttributeError:
        print(f"Logged into Discord as {bot.user.name}!")
        bot.starting_message = await bot.channels["logs"].send(f"Started and ready! Took `{monotonic() - start_time:.2f} seconds`")

        await bot.supportserver.chunk(cache=True)
        bot.patreon_role = discord.utils.get(bot.supportserver.roles, name="Patreon!")

print("\nLogging into Discord...")
bot.run(t)
