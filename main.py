import discord
import base64
from discord.ext import commands
from config import ECONOMY_FILE, JOBS_FILE, GUILDS_FILE, ACHIEVEMENTS_FILE
from managers import EconomyManager, JobsManager, GuildsManager, AchievementsManager
from cogs.economy import Economy
from cogs.moderation import Moderation
from cogs.jobs import Jobs
from cogs.guilds import Guilds
from cogs.achievements import Achievements
from dotenv import load_dotenv
import os

load_dotenv()
encoded = os.getenv("TOKEN_B64")
TOKEN = base64.b64decode(encoded).decode()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

economy_manager = EconomyManager(ECONOMY_FILE)
jobs_manager = JobsManager(JOBS_FILE)
guilds_manager = GuildsManager(GUILDS_FILE)
achievements_manager = AchievementsManager(ACHIEVEMENTS_FILE)

@bot.event
async def setup_hook():
    await bot.add_cog(Economy(bot, economy_manager))
    await bot.add_cog(Moderation(bot))
    await bot.add_cog(Jobs(bot, jobs_manager, economy_manager))
    await bot.add_cog(Guilds(bot, guilds_manager, economy_manager))
    await bot.add_cog(Achievements(bot, achievements_manager, economy_manager))

@bot.event
async def on_ready():
    try:
        await economy_manager.load()
        print("Logged in")
        synced = await bot.tree.sync()
        print(f"Locked in and synced {len(synced)} command{'s' if len(synced) != 1 else ''}")
    except Exception as e:
        print(f"Error syncing commands: {e}")

bot.run(TOKEN)
