# Guilds Cog
import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import GUILD_CREATION_COST
from managers import GuildsManager, EconomyManager
from utils import currency, embedbuildthing


class GuildBrowserView(discord.ui.View):
    def __init__(self, guilds: list[tuple], bot: commands.Bot, page: int = 0):
        super().__init__(timeout=300)
        self.guilds = guilds  # List of (guild_id, guild_data) tuples
        self.bot = bot
        self.page = page
        self.items_per_page = 5
    
    def get_page_data(self) -> tuple[list[tuple], int, int]:
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        page_guilds = self.guilds[start:end]
        total_pages = (len(self.guilds) + self.items_per_page - 1) // self.items_per_page
        return page_guilds, self.page + 1, total_pages
    
    def build_embed(self) -> discord.Embed:
        page_guilds, current_page, total_pages = self.get_page_data()
        if not page_guilds:
            return embedbuildthing("Guild Browser", "No guilds found.")
        lines = []
        for idx, (guild_id, guild) in enumerate(page_guilds, start=(self.page * self.items_per_page) + 1):
            privacy_icon = "🔒" if guild["privacy"] == "password_locked" else "🌐"
            member_count = len(guild["members"])
            cap_text = f"/{guild['member_cap']}" if guild.get("member_cap") else ""
            owner = self.bot.get_user(guild["owner_id"])
            owner_name = owner.name if owner else "Unknown"
            lines.append(f"{idx}. {privacy_icon} **{guild['display_name']}** (`{guild_id}`)\n   Owner: {owner_name} • Members: {member_count}{cap_text}")
        embed = embedbuildthing("Guild Browser", "\n\n".join(lines))
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


class Guilds(commands.Cog):
    def __init__(self, bot: commands.Bot, guilds_manager: GuildsManager, economy_manager: EconomyManager):
        self.bot = bot
        self.guilds_manager = guilds_manager
        self.economy_manager = economy_manager
    
    async def cog_load(self) -> None:
        await self.guilds_manager.load()
    
    @app_commands.guild_only()
    @app_commands.command(name="createguild", description="Create a new guild")
    @app_commands.describe(
        display_name="Display name for the guild",
        image_url="Image URL for the guild icon",
        privacy="Privacy setting",
        password="Password if password locked"
    )
    @app_commands.choices(privacy=[
        app_commands.Choice(name="Public", value="public"),
        app_commands.Choice(name="Password Locked", value="password_locked"),
    ])
    async def createguild(
        self,
        interaction: discord.Interaction,
        display_name: str,
        image_url: str,
        privacy: app_commands.Choice[str],
        password: Optional[str] = None
    ) -> None:
        if not interaction.guild_id:
            return
        # Check if user is already in a guild
        current_guild = await self.guilds_manager.get_user_guild(interaction.guild_id, interaction.user.id)
        if current_guild:
            embed = embedbuildthing("Already in Guild", f"You are already in a guild. Leave it first with /guildleave.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        # Check cost
        if not await self.economy_manager.has_wallet(interaction.guild_id, interaction.user.id, GUILD_CREATION_COST):
            embed = embedbuildthing("Insufficient Funds", f"You need {currency(GUILD_CREATION_COST)} to create a guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        # Check password requirement
        if privacy.value == "password_locked" and not password:
            embed = embedbuildthing("Password Required", "Password is required for password-locked guilds.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        # Create guild
        guild_id = await self.guilds_manager.create_guild(
            interaction.guild_id, interaction.user.id, display_name, image_url, privacy.value, password
        )
        
        if not guild_id:
            embed = embedbuildthing("Creation Failed", "Failed to create guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        # Deduct cost
        await self.economy_manager.deduct_wallet(interaction.guild_id, interaction.user.id, GUILD_CREATION_COST)
        await self.economy_manager.save()
        await self.guilds_manager.save()
        
        # Check guildmaster achievement
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            if await achievements_cog.achievements_manager.unlock_achievement(interaction.guild_id, interaction.user.id, "guildmaster"):
                await achievements_cog._award_achievement(interaction.guild_id, interaction.user.id, "guildmaster")
        
        embed = embedbuildthing("Guild Created", f"Successfully created guild **{display_name}**!\nGuild ID: `{guild_id}`", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
    
    @app_commands.guild_only()
    @app_commands.command(name="browseguilds", description="Browse available guilds")
    async def browseguilds(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            return
        guilds = await self.guilds_manager.list_guilds(interaction.guild_id)
        if not guilds:
            embed = embedbuildthing("No Guilds", "No guilds are available.")
            await interaction.response.send_message(embed=embed)
            return
        
        view = GuildBrowserView(guilds, self.bot)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view)
    
    @app_commands.guild_only()
    @app_commands.command(name="joinguild", description="Join a guild")
    @app_commands.describe(guild_id="ID of the guild to join")
    async def joinguild(self, interaction: discord.Interaction, guild_id: str) -> None:
        if not interaction.guild_id:
            return
        guild_id = guild_id.upper()
        guild = await self.guilds_manager.get_guild(interaction.guild_id, guild_id)
        if not guild:
            embed = embedbuildthing("Guild Not Found", "That guild does not exist.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        if guild["privacy"] == "public":
            success, error = await self.guilds_manager.join_guild(interaction.guild_id, interaction.user.id, guild_id)
            if success:
                await self.guilds_manager.save()
                
                # Check guildeer and leaderboard achievements
                achievements_cog = self.bot.get_cog("Achievements")
                if achievements_cog:
                    await achievements_cog.check_guild_achievements(interaction.guild_id, interaction.user.id)
                
                embed = embedbuildthing("Joined Guild", f"You joined **{guild['display_name']}**!", color=discord.Color.green())
                await interaction.response.send_message(embed=embed)
            else:
                embed = embedbuildthing("Join Failed", error, color=discord.Color.red())
                await interaction.response.send_message(embed=embed)
        else:
            # Password locked - need to ask for password
            embed = embedbuildthing("Password Required", f"**{guild['display_name']}** is password locked. Reply to this message with the password.", color=discord.Color.orange())
            await interaction.response.send_message(embed=embed)
            response_message = await interaction.original_response()
            response_id = response_message.id
            
            def check(message: discord.Message) -> bool:
                return message.author.id == interaction.user.id and message.reference and message.reference.message_id == response_id
            
            try:
                message = await self.bot.wait_for("message", check=check, timeout=60.0)
                if message.content == guild.get("password"):
                    success, error = await self.guilds_manager.join_guild(interaction.guild_id, interaction.user.id, guild_id)
                    if success:
                        await self.guilds_manager.save()
                        
                        # Check guildeer and leaderboard achievements
                        achievements_cog = self.bot.get_cog("Achievements")
                        if achievements_cog:
                            await achievements_cog.check_guild_achievements(interaction.guild_id, interaction.user.id)
                        
                        embed = embedbuildthing("Joined Guild", f"You joined **{guild['display_name']}**!", color=discord.Color.green())
                        await message.reply(embed=embed)
                    else:
                        embed = embedbuildthing("Join Failed", error, color=discord.Color.red())
                        await message.reply(embed=embed)
                else:
                    embed = embedbuildthing("Wrong Password", "Incorrect password.", color=discord.Color.red())
                    await message.reply(embed=embed)
            except asyncio.TimeoutError:
                pass
    
    @app_commands.guild_only()
    @app_commands.command(name="guildview", description="View your guild's members")
    async def guildview(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            return
        guild_name = await self.guilds_manager.get_user_guild(interaction.guild_id, interaction.user.id)
        if not guild_name:
            embed = embedbuildthing("Not in Guild", "You are not in a guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        guild = await self.guilds_manager.get_guild(interaction.guild_id, guild_name)
        if not guild:
            embed = embedbuildthing("Guild Not Found", "Your guild was not found.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        lines = []
        for member_id in guild["members"]:
            member = self.bot.get_user(member_id)
            if member:
                mention = member.mention
                if member_id == guild["owner_id"]:
                    mention += " 👑"
            else:
                mention = f"<@{member_id}>"
                if member_id == guild["owner_id"]:
                    mention += " 👑"
            lines.append(mention)
        
        embed = embedbuildthing(f"Guild: {guild['display_name']}", "\n".join(lines) if lines else "No members")
        if guild.get("image_url"):
            embed.set_thumbnail(url=guild["image_url"])
        await interaction.response.send_message(embed=embed)
    
    @app_commands.guild_only()
    @app_commands.command(name="guildleaderboard", description="View your guild's leaderboard")
    async def guildleaderboard(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            return
        guild_name = await self.guilds_manager.get_user_guild(interaction.guild_id, interaction.user.id)
        if not guild_name:
            embed = embedbuildthing("Not in Guild", "You are not in a guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        standings = await self.guilds_manager.get_guild_leaderboard(interaction.guild_id, guild_name, self.economy_manager)
        if not standings:
            embed = embedbuildthing("Guild Leaderboard", "No members found.")
            await interaction.response.send_message(embed=embed)
            return
        
        lines = []
        for index, (user_id, wallet, bank, total) in enumerate(standings, start=1):
            user_obj = self.bot.get_user(user_id)
            mention = user_obj.mention if user_obj else f"<@{user_id}>"
            lines.append(f"{index}. {mention} • Wallet {currency(wallet)} • Bank {currency(bank)} • Total {currency(total)}")
        
        guild = await self.guilds_manager.get_guild(interaction.guild_id, guild_name)
        embed = embedbuildthing(f"Guild Leaderboard: {guild['display_name']}", "\n".join(lines))
        if guild.get("image_url"):
            embed.set_thumbnail(url=guild["image_url"])
        await interaction.response.send_message(embed=embed)
        
        # Check leaderboard achievement
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_guild_achievements(interaction.guild_id, interaction.user.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="guildleave", description="Leave your guild")
    async def guildleave(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            return
        left = await self.guilds_manager.leave_guild(interaction.guild_id, interaction.user.id)
        if not left:
            embed = embedbuildthing("Not in Guild", "You are not in a guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        await self.guilds_manager.save()
        embed = embedbuildthing("Left Guild", "You left your guild.", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed)
    
    @app_commands.guild_only()
    @app_commands.command(name="guildkick", description="Kick a member from your guild (owner only)")
    @app_commands.describe(user="User to kick")
    async def guildkick(self, interaction: discord.Interaction, user: discord.Member) -> None:
        if not interaction.guild_id:
            return
        guild_name = await self.guilds_manager.get_user_guild(interaction.guild_id, interaction.user.id)
        if not guild_name:
            embed = embedbuildthing("Not in Guild", "You are not in a guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        guild = await self.guilds_manager.get_guild(interaction.guild_id, guild_name)
        if not guild or guild["owner_id"] != interaction.user.id:
            embed = embedbuildthing("Not Owner", "You are not the owner of this guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        success, error = await self.guilds_manager.kick_member(interaction.guild_id, interaction.user.id, user.id)
        if success:
            await self.guilds_manager.save()
            embed = embedbuildthing("Member Kicked", f"Kicked {user.mention} from the guild.", color=discord.Color.green())
            await interaction.response.send_message(embed=embed)
        else:
            embed = embedbuildthing("Kick Failed", error, color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
    
    @app_commands.guild_only()
    @app_commands.command(name="guilddisband", description="Disband your guild (owner only)")
    async def guilddisband(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            return
        disbanded = await self.guilds_manager.disband_guild(interaction.guild_id, interaction.user.id)
        if not disbanded:
            embed = embedbuildthing("Cannot Disband", "You are not the owner of a guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        await self.guilds_manager.save()
        embed = embedbuildthing("Guild Disbanded", "Your guild has been disbanded.", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed)
    
    @app_commands.guild_only()
    @app_commands.command(name="guildrename", description="Rename your guild (owner only)")
    @app_commands.describe(new_name="New display name for the guild")
    async def guildrename(self, interaction: discord.Interaction, new_name: str) -> None:
        if not interaction.guild_id:
            return
        renamed = await self.guilds_manager.rename_guild(interaction.guild_id, interaction.user.id, new_name)
        if not renamed:
            embed = embedbuildthing("Cannot Rename", "You are not the owner of a guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        await self.guilds_manager.save()
        embed = embedbuildthing("Guild Renamed", f"Guild renamed to **{new_name}**.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
    
    @app_commands.guild_only()
    @app_commands.command(name="guildcap", description="Set member cap for your guild (owner only)")
    @app_commands.describe(cap="Member cap (0 to remove cap)")
    async def guildcap(self, interaction: discord.Interaction, cap: int) -> None:
        if cap < 0:
            embed = embedbuildthing("Invalid Cap", "Cap must be 0 or greater.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        if not interaction.guild_id:
            return
        cap_value = None if cap == 0 else cap
        set_cap = await self.guilds_manager.set_member_cap(interaction.guild_id, interaction.user.id, cap_value)
        if not set_cap:
            embed = embedbuildthing("Cannot Set Cap", "You are not the owner of a guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        await self.guilds_manager.save()
        if cap_value:
            embed = embedbuildthing("Member Cap Set", f"Member cap set to {cap}.", color=discord.Color.green())
        else:
            embed = embedbuildthing("Member Cap Removed", "Member cap removed.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
    
    @app_commands.guild_only()
    @app_commands.command(name="guildtransfer", description="Transfer ownership of your guild to another member (owner only)")
    @app_commands.describe(user="User to transfer ownership to")
    async def guildtransfer(self, interaction: discord.Interaction, user: discord.Member) -> None:
        if not interaction.guild_id:
            return
        guild_id = await self.guilds_manager.get_user_guild(interaction.guild_id, interaction.user.id)
        if not guild_id:
            embed = embedbuildthing("Not in Guild", "You are not in a guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        guild = await self.guilds_manager.get_guild(interaction.guild_id, guild_id)
        if not guild or guild["owner_id"] != interaction.user.id:
            embed = embedbuildthing("Not Owner", "You are not the owner of this guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        if user.id == interaction.user.id:
            embed = embedbuildthing("Invalid Target", "You cannot transfer ownership to yourself.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        success, error = await self.guilds_manager.transfer_ownership(interaction.guild_id, interaction.user.id, user.id)
        if success:
            await self.guilds_manager.save()
            embed = embedbuildthing("Ownership Transferred", f"Ownership of **{guild['display_name']}** has been transferred to {user.mention}. You are now a regular member.", color=discord.Color.green())
            await interaction.response.send_message(embed=embed)
        else:
            embed = embedbuildthing("Transfer Failed", error, color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
    
    @app_commands.guild_only()
    @app_commands.command(name="guildshowpass", description="Show the password of your guild (owner only)")
    async def guildshowpass(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            return
        guild_id = await self.guilds_manager.get_user_guild(interaction.guild_id, interaction.user.id)
        if not guild_id:
            embed = embedbuildthing("Not in Guild", "You are not in a guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        guild = await self.guilds_manager.get_guild(interaction.guild_id, guild_id)
        if not guild or guild["owner_id"] != interaction.user.id:
            embed = embedbuildthing("Not Owner", "You are not the owner of this guild.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        if guild["privacy"] != "password_locked":
            embed = embedbuildthing("Not Password Locked", "This guild is not password locked.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        password = guild.get("password", "No password set")
        embed = embedbuildthing("Guild Password", f"The password for **{guild['display_name']}** is: `{password}`", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

