# Achievements Cog
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import ACHIEVEMENTS
from managers import AchievementsManager, EconomyManager
from utils import currency, embedbuildthing


class AchievementsView(discord.ui.View):
    def __init__(self, unlocked: set[str], bot: commands.Bot, user_id: int, page: int = 0):
        super().__init__(timeout=300)
        self.unlocked = unlocked
        self.bot = bot
        self.user_id = user_id
        self.page = page
        self.items_per_page = 5
        self.all_achievements = list(ACHIEVEMENTS.items())
    
    def get_page_data(self) -> tuple[list[tuple], int, int]:
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        page_achievements = self.all_achievements[start:end]
        total_pages = (len(self.all_achievements) + self.items_per_page - 1) // self.items_per_page
        return page_achievements, self.page + 1, total_pages
    
    def build_embed(self) -> discord.Embed:
        page_achievements, current_page, total_pages = self.get_page_data()
        if not page_achievements:
            return embedbuildthing("Achievements", "No achievements found.")
        
        lines = []
        for key, achievement in page_achievements:
            is_unlocked = key in self.unlocked
            status = "✅" if is_unlocked else "❌"
            reward_text = f" • Reward: {currency(achievement['reward'])}"
            lines.append(f"{status} **{achievement['name']}**{reward_text}\n{achievement['description']}")
        
        embed = embedbuildthing("Achievements", "\n\n".join(lines))
        embed.set_footer(text=f"Page {current_page}/{total_pages}")
        return embed
    
    async def update_embed(self, interaction: discord.Interaction) -> None:
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.page > 0:
            self.page -= 1
        await self.update_embed(interaction)
    
    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        _, _, total_pages = self.get_page_data()
        if self.page < total_pages - 1:
            self.page += 1
        await self.update_embed(interaction)


class Achievements(commands.Cog):
    def __init__(self, bot: commands.Bot, achievements_manager: AchievementsManager, economy_manager: EconomyManager):
        self.bot = bot
        self.achievements_manager = achievements_manager
        self.economy_manager = economy_manager
    
    async def cog_load(self) -> None:
        await self.achievements_manager.load()
    
    @app_commands.guild_only()
    @app_commands.command(name="viewachievements", description="View your achievements")
    async def viewachievements(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            return
        unlocked = await self.achievements_manager.get_user_achievements(interaction.guild_id, interaction.user.id)
        view = AchievementsView(unlocked, self.bot, interaction.user.id)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view)
    
    async def check_balance_achievements(self, guild_id: int, user_id: int) -> None:
        """Check balance-based achievements"""
        total = await self.economy_manager.total_balance(guild_id, user_id)
        
        if total >= 5000:
            if await self.achievements_manager.unlock_achievement(guild_id, user_id, "money_lover"):
                await self._award_achievement(guild_id, user_id, "money_lover")
        
        if total >= 10000:
            if await self.achievements_manager.unlock_achievement(guild_id, user_id, "money_fiend"):
                await self._award_achievement(guild_id, user_id, "money_fiend")
        
        if total >= 100000:
            if await self.achievements_manager.unlock_achievement(guild_id, user_id, "money_launderer"):
                await self._award_achievement(guild_id, user_id, "money_launderer")
        
        if total >= 1000000:
            if await self.achievements_manager.unlock_achievement(guild_id, user_id, "gifted_by_god"):
                await self._award_achievement(guild_id, user_id, "gifted_by_god")
        
        if total >= 10000000:
            if await self.achievements_manager.unlock_achievement(guild_id, user_id, "savehacking"):
                await self._award_achievement(guild_id, user_id, "savehacking")
    
    async def check_inventory_achievements(self, guild_id: int, user_id: int) -> None:
        """Check inventory-based achievements"""
        inventory = await self.economy_manager.get_inventory(guild_id, user_id)
        if inventory.get("admin_itemitemitem", 0) > 0:
            if await self.achievements_manager.unlock_achievement(guild_id, user_id, "volt_prize_receiver"):
                await self._award_achievement(guild_id, user_id, "volt_prize_receiver")
    
    async def check_guild_achievements(self, guild_id: int, user_id: int) -> None:
        """Check guild-based achievements"""
        from managers import GuildsManager
        guilds_cog = self.bot.get_cog("Guilds")
        if not guilds_cog:
            return
        
        guilds_manager = guilds_cog.guilds_manager
        player_guild_id = await guilds_manager.get_user_guild(guild_id, user_id)
        
        if player_guild_id:
            if await self.achievements_manager.unlock_achievement(guild_id, user_id, "guildeer"):
                await self._award_achievement(guild_id, user_id, "guildeer")
            
            # Check leaderboard achievement
            guild_standings = await guilds_manager.get_guild_leaderboard_all(guild_id, self.economy_manager)
            for index, (gid, _) in enumerate(guild_standings[:5], start=1):
                if gid == player_guild_id:
                    if await self.achievements_manager.unlock_achievement(guild_id, user_id, "leaderboard"):
                        await self._award_achievement(guild_id, user_id, "leaderboard")
                    break
    
    async def _award_achievement(self, guild_id: int, user_id: int, achievement_key: str) -> None:
        """Award an achievement and give the reward"""
        achievement = ACHIEVEMENTS.get(achievement_key)
        if not achievement:
            return
        
        reward = achievement["reward"]
        await self.economy_manager.add_wallet(guild_id, user_id, reward)
        await self.economy_manager.save()
        await self.achievements_manager.save()
        
        # Try to notify user
        user = self.bot.get_user(user_id)
        if user:
            try:
                embed = embedbuildthing(
                    "Achievement Unlocked!",
                    f"**{achievement['name']}**\n{achievement['description']}\n\nReward: {currency(reward)}",
                    color=discord.Color.gold()
                )
                await user.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass