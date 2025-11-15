# Moderation Cog
import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import DATA_FILE
from utils import embedbuildthing


def current_time() -> datetime:
    return datetime.now(timezone.utc)


class ModerationData:
    def __init__(self):
        self.case_counter = 1
        self.user_cases: Dict[int, List[dict]] = defaultdict(list)
        self.user_warns: Dict[int, List[dict]] = defaultdict(list)
        self.tempban_tasks: Dict[int, asyncio.Task] = {}
    
    def load(self) -> None:
        if not DATA_FILE.exists():
            return
        
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            
            self.case_counter = data.get('case_counter', 1)
            
            raw_cases = data.get('user_cases', {})
            self.user_cases = defaultdict(list)
            for user_id, cases in raw_cases.items():
                for case in cases:
                    case['timestamp'] = datetime.fromisoformat(case['timestamp'])
                    self.user_cases[int(user_id)].append(case)
            
            raw_warns = data.get('user_warns', {})
            self.user_warns = defaultdict(list)
            for user_id, warns in raw_warns.items():
                for warn in warns:
                    warn['issued_at'] = datetime.fromisoformat(warn['issued_at'])
                    if warn['expires_at']:
                        warn['expires_at'] = datetime.fromisoformat(warn['expires_at'])
                    self.user_warns[int(user_id)].append(warn)
            
            print(f"Loaded {len(self.user_cases)} users with cases and {len(self.user_warns)} users with warnings")
        except Exception as e:
            print(f"Error loading data: {e}")
    
    def save(self) -> None:
        try:
            serializable_cases = {}
            for user_id, cases in self.user_cases.items():
                serializable_cases[str(user_id)] = [
                    {
                        **case,
                        'timestamp': case['timestamp'].isoformat()
                    }
                    for case in cases
                ]
            
            serializable_warns = {}
            for user_id, warns in self.user_warns.items():
                serializable_warns[str(user_id)] = [
                    {
                        **warn,
                        'issued_at': warn['issued_at'].isoformat(),
                        'expires_at': warn['expires_at'].isoformat() if warn['expires_at'] else None
                    }
                    for warn in warns
                ]
            
            data = {
                'case_counter': self.case_counter,
                'user_cases': serializable_cases,
                'user_warns': serializable_warns
            }
            
            with open(DATA_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving data: {e}")
    
    def record_case(self, interaction: discord.Interaction, target: discord.abc.User, action: str, reason: Optional[str], extra: Optional[str] = None) -> dict:
        entry = {
            "case_id": self.case_counter,
            "action": action,
            "moderator_id": interaction.user.id,
            "timestamp": current_time(),
            "reason": reason,
            "extra": extra,
        }
        self.user_cases[target.id].append(entry)
        self.case_counter += 1
        self.save()
        return entry


def respond_embed(action: str, interaction: discord.Interaction, target: discord.abc.User, reason: Optional[str], extra: Optional[str] = None, *, color: discord.Color = discord.Color.blurple()) -> discord.Embed:
    reason_value = reason if reason else "No reason provided"
    embed = embedbuildthing(action, color=color)
    embed.add_field(name="Target", value=f"{target.mention} ({target.id})", inline=False)
    embed.add_field(name="Moderator", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
    embed.add_field(name="Reason", value=reason_value, inline=False)
    if extra:
        embed.add_field(name="Details", value=extra, inline=False)
    return embed


def user_dm_embed(action: str, guild: discord.Guild, reason: Optional[str], extra: Optional[str] = None, *, color: discord.Color = discord.Color.blurple()) -> discord.Embed:
    reason_value = reason if reason else "No reason provided"
    embed = embedbuildthing(f"Moderation Action: {action}", color=color)
    embed.add_field(name="Server", value=guild.name, inline=False)
    embed.add_field(name="Reason", value=reason_value, inline=False)
    if extra:
        embed.add_field(name="Details", value=extra, inline=False)
    return embed


async def notify_user(user: discord.abc.User, action: str, guild: discord.Guild, reason: Optional[str], extra: Optional[str] = None, color: discord.Color = discord.Color.blurple()) -> bool:
    """Send a DM to the user about the moderation action. Returns True if successful."""
    try:
        embed = user_dm_embed(action, guild, reason, extra, color=color)
        await user.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


async def send_interaction_embed(interaction: discord.Interaction, embed: discord.Embed) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def schedule_unban(guild: discord.Guild, user_id: int, hours: float) -> None:
    try:
        await asyncio.sleep(hours * 3600)
        await guild.unban(discord.Object(id=user_id), reason="Temporary ban expired")
    except (discord.NotFound, discord.Forbidden):
        return


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = ModerationData()
    
    async def cog_load(self) -> None:
        self.data.load()
    
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member to timeout", minutes="Duration in minutes", reason="Reason for the timeout")
    @app_commands.command(name="timeout")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[float, 1, 10080], reason: Optional[str] = None):
        duration = timedelta(minutes=minutes)
        await member.timeout(duration=duration, reason=reason or f"Timeout issued by {interaction.user}")
        extra = f"Duration: {minutes:.2f} minutes"
        self.data.record_case(interaction, member, "Timeout", reason, extra)
        
        dm_sent = await notify_user(member, "Timeout", interaction.guild, reason, extra, color=discord.Color.orange())
        
        embed = respond_embed("Timeout Applied", interaction, member, reason, extra)
        if not dm_sent:
            embed.set_footer(text="Could not DM user. DMs most likely off.")
        await send_interaction_embed(interaction, embed)
    
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member to remove from timeout", reason="Reason for removal")
    @app_commands.command(name="untimeout", description="Remove timeout from a member.")
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        await member.timeout(duration=None, reason=reason or f"Timeout removed by {interaction.user}")
        self.data.record_case(interaction, member, "Timeout Cleared", reason)
        
        dm_sent = await notify_user(member, "Timeout Cleared", interaction.guild, reason, color=discord.Color.green())
        
        embed = respond_embed("Timeout Cleared", interaction, member, reason)
        if not dm_sent:
            embed.set_footer(text="Could not DM user. DMs most likely off.")
        await send_interaction_embed(interaction, embed)
    
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member to warn", reason="Reason for the warning", expiration="Expiration date (YYYY-MM-DD). Leave blank for permanent warning.")
    @app_commands.command(name="warn", description="Warn a user.")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str, expiration: Optional[str] = None):
        expires_at: Optional[datetime] = None
        if expiration and expiration.lower() != "inf":
            try:
                expires_at = datetime.fromisoformat(expiration)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
            except ValueError:
                embed = embedbuildthing("Invalid Expiration", "Expiration date (YYYY-MM-DD). Leave blank for permanent warning.", color=discord.Color.red())
                await send_interaction_embed(interaction, embed)
                return
        entry = self.data.record_case(interaction, member, "Warning", reason, f"Expires: {expires_at.isoformat()}" if expires_at else "Expires: Never")
        warn_entry = {
            "case_id": entry["case_id"],
            "reason": reason,
            "expires_at": expires_at,
            "issued_at": entry["timestamp"],
            "moderator_id": interaction.user.id,
        }
        self.data.user_warns[member.id].append(warn_entry)
        self.data.save()
        extra = f"Expires: {expires_at.isoformat()}" if expires_at else "Expires: Never"
        dm_sent = await notify_user(member, "Warning", interaction.guild, reason, extra, color=discord.Color.yellow())
        
        embed = respond_embed("Warning Issued", interaction, member, reason, extra)
        if not dm_sent:
            embed.set_footer(text="Could not DM user. DMs most likely off.")
        await send_interaction_embed(interaction, embed)
    
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member whose warning to clear", warn_number="Warning number to clear", reason="Reason for clearing")
    @app_commands.command(name="clearwarn", description="Clear a user's warn(s).")
    async def clearwarn(self, interaction: discord.Interaction, member: discord.Member, warn_number: app_commands.Range[int, 1, 100], reason: Optional[str] = None):
        warns = self.data.user_warns.get(member.id, [])
        if warn_number > len(warns):
            embed = embedbuildthing("Warning Not Found", "Specify a valid warning number.", color=discord.Color.red())
            await send_interaction_embed(interaction, embed)
            return
        cleared = warns.pop(warn_number - 1)
        self.data.user_warns[member.id] = warns
        self.data.record_case(interaction, member, "Warning Cleared", reason, f"Cleared Case #{cleared['case_id']}")
        self.data.save()
        extra = f"Cleared warning #{warn_number} (Case #{cleared['case_id']})"
        
        dm_sent = await notify_user(member, "Warning Cleared", interaction.guild, reason, extra, color=discord.Color.green())
        
        embed = respond_embed("Warning Cleared", interaction, member, reason, extra)
        if not dm_sent:
            embed.set_footer(text="Could not DM user. DMs most likely off.")
        await send_interaction_embed(interaction, embed)
    
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member to review warnings for")
    @app_commands.command(name="listwarn", description="List a user's warnings.")
    async def listwarn(self, interaction: discord.Interaction, member: discord.Member):
        warns = self.data.user_warns.get(member.id, [])
        if not warns:
            embed = embedbuildthing("No Warnings", f"{member.mention} has no recorded warnings.")
            await send_interaction_embed(interaction, embed)
            return
        lines = []
        for idx, warn in enumerate(warns, start=1):
            expires = warn["expires_at"].isoformat() if warn["expires_at"] else "Never"
            timestamp = discord.utils.format_dt(warn["issued_at"], style="R")
            lines.append(f"**{idx}.** Case #{warn['case_id']} • {timestamp}\nReason: {warn['reason']}\nExpires: {expires}")
        embed = embedbuildthing("Warnings", "\n\n".join(lines))
        await send_interaction_embed(interaction, embed)
    
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(user="User to review cases for")
    @app_commands.command(name="cases", description="Review a members case log.")
    async def cases(self, interaction: discord.Interaction, user: discord.User):
        cases = self.data.user_cases.get(user.id, [])
        if not cases:
            embed = embedbuildthing("No Cases", f"{user.mention} has no recorded cases.")
            await send_interaction_embed(interaction, embed)
            return
        lines = []
        for entry in cases[-25:][::-1]:
            timestamp = discord.utils.format_dt(entry["timestamp"], style="R")
            reason = entry["reason"] if entry["reason"] else "No reason provided"
            details = f"Details: {entry['extra']}" if entry["extra"] else ""
            lines.append(f"**Case #{entry['case_id']}** • {entry['action']} • {timestamp}\nReason: {reason}{'\n' + details if details else ''}")
        embed = embedbuildthing("Case Log", "\n\n".join(lines))
        await send_interaction_embed(interaction, embed)
    
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(member="Member to kick", reason="Reason for kick")
    @app_commands.command(name="kick", description="Kick a member.")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        dm_sent = await notify_user(member, "Kick", interaction.guild, reason, color=discord.Color.red())
        
        await member.kick(reason=reason or f"Kicked by {interaction.user}")
        self.data.record_case(interaction, member, "Kick", reason)
        embed = respond_embed("Member Kicked", interaction, member, reason)
        if not dm_sent:
            embed.set_footer(text="Could not DM user. DMs most likely off.")
        await send_interaction_embed(interaction, embed)
    
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(member="Member to temporarily ban", hours="Duration in hours", reason="Reason for the ban")
    @app_commands.command(name="tempban", description="Temporarily ban a member.")
    async def tempban(self, interaction: discord.Interaction, member: discord.Member, hours: app_commands.Range[float, 1, 168], reason: Optional[str] = None):
        guild = interaction.guild
        if guild is None:
            return
        task = self.data.tempban_tasks.pop(member.id, None)
        if task and not task.done():
            task.cancel()
        
        extra = f"Duration: {hours:.2f} hours"
        
        dm_sent = await notify_user(member, "Temporary Ban", interaction.guild, reason, extra, color=discord.Color.red())
        
        await guild.ban(member, reason=reason or f"Tempban by {interaction.user}")
        self.data.record_case(interaction, member, "Temporary Ban", reason, extra)
        self.data.tempban_tasks[member.id] = asyncio.create_task(schedule_unban(guild, member.id, hours))
        embed = respond_embed("Temporary Ban Issued", interaction, member, reason, extra)
        if not dm_sent:
            embed.set_footer(text="Could not DM user. DMs most likely off.")
        await send_interaction_embed(interaction, embed)
    
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(member="Member to permanently ban", reason="Reason for the ban")
    @app_commands.command(name="permban", description="Permanently ban a member.")
    async def permban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        guild = interaction.guild
        if guild is None:
            return
        task = self.data.tempban_tasks.pop(member.id, None)
        if task and not task.done():
            task.cancel()
        
        dm_sent = await notify_user(member, "Permanent Ban", interaction.guild, reason, color=discord.Color.dark_red())
        
        await guild.ban(member, reason=reason or f"Permban by {interaction.user}")
        self.data.record_case(interaction, member, "Permanent Ban", reason)
        embed = respond_embed("Permanent Ban Issued", interaction, member, reason)
        if not dm_sent:
            embed.set_footer(text="Could not DM user. DMs most likely off.")
        await send_interaction_embed(interaction, embed)
    
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(member="Member whose messages to purge", message_count="Number of recent messages to check", reason="Reason for purge")
    @app_commands.command(name="purgeuser", description="Purge a users messages.")
    async def purgeuser(self, interaction: discord.Interaction, member: discord.Member, message_count: app_commands.Range[int, 1, 500], reason: Optional[str] = None):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            embed = embedbuildthing("Unsupported Channel", "This command can only be used in text channels.", color=discord.Color.red())
            await send_interaction_embed(interaction, embed)
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await channel.purge(limit=message_count, check=lambda msg: msg.author.id == member.id)
        details = f"Deleted {len(deleted)} messages in {channel.mention}"
        self.data.record_case(interaction, member, "Messages Purged", reason, f"Channel: {channel.mention}; Deleted {len(deleted)} messages")
        
        dm_sent = await notify_user(member, "Messages Purged", interaction.guild, reason, details, color=discord.Color.orange())
        
        embed = respond_embed("Messages Purged", interaction, member, reason, details)
        if not dm_sent:
            embed.set_footer(text="Could not DM user. DMs most likely off.")
        await interaction.followup.send(embed=embed, ephemeral=True)

