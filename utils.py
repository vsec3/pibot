# Utility functions
from typing import Optional
import discord

def currency(amount: int) -> str:
    return f"${amount:,}"

def resolve_item_key(name: str) -> Optional[str]:
    from config import ITEM_DATA
    normalized = name.lower().replace(" ", "_").replace("-", "_")
    return normalized if normalized in ITEM_DATA else None

def embedbuildthing(title: str, description: Optional[str] = None, *, color: discord.Color = discord.Color.blurple()) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
    return embed

def is_admin(user: discord.Member) -> bool:
    """Check if user is in admin whitelist or has admin permissions"""
    from config import ADMIN_WHITELIST
    if user.id in ADMIN_WHITELIST:
        return True
    return user.guild_permissions.manage_messages and user.guild_permissions.ban_members

