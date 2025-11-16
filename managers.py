# Data managers
import asyncio
import json
import random
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from config import ITEM_DATA, ECONOMY_FILE, JOBS_FILE, GUILDS_FILE

class EconomyManager:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lock = asyncio.Lock()
        # Structure: {guild_id: {user_id: data}}
        self.guilds: Dict[int, Dict[str, Dict[str, object]]] = {}
    
    def _ensure_user(self, guild_id: int, user_id: int) -> Dict[str, object]:
        if guild_id not in self.guilds:
            self.guilds[guild_id] = {}
        guild_users = self.guilds[guild_id]
        key = str(user_id)
        if key not in guild_users:
            guild_users[key] = {"wallet": 0, "bank": 0, "inventory": {}}
        return guild_users[key]
    
    async def load(self) -> None:
        async with self.lock:
            if not self.file_path.exists():
                self.guilds = {}
                return
            try:
                with open(self.file_path, "r") as f:
                    data = json.load(f)
                # Support both old format (migration) and new format
                if "guilds" in data:
                    # New format: {guilds: {guild_id: {users: {user_id: data}}}}
                    self.guilds = {}
                    for guild_id_str, guild_data in data["guilds"].items():
                        guild_id = int(guild_id_str)
                        self.guilds[guild_id] = {}
                        raw_users = guild_data.get("users", {})
                        for user_id, payload in raw_users.items():
                            wallet = max(0, int(payload.get("wallet", 0)))
                            bank = max(0, int(payload.get("bank", 0)))
                            inventory_data = {}
                            raw_inventory = payload.get("inventory", {})
                            for item_key, amount in raw_inventory.items():
                                if item_key in ITEM_DATA:
                                    inventory_data[item_key] = max(0, int(amount))
                            self.guilds[guild_id][user_id] = {"wallet": wallet, "bank": bank, "inventory": inventory_data}
                else:
                    # Old format migration: convert to per-guild structure
                    self.guilds = {}
            except Exception:
                self.guilds = {}
    
    async def save(self) -> None:
        async with self.lock:
            data = {
                "guilds": {
                    str(guild_id): {"users": users}
                    for guild_id, users in self.guilds.items()
                }
            }
            with open(self.file_path, "w") as f:
                json.dump(data, f, indent=2)
    
    async def ensure_user(self, guild_id: int, user_id: int) -> None:
        async with self.lock:
            self._ensure_user(guild_id, user_id)
    
    async def get_balances(self, guild_id: int, user_id: int) -> Tuple[int, int]:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            return user["wallet"], user["bank"]
    
    async def total_balance(self, guild_id: int, user_id: int) -> int:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            return user["wallet"] + user["bank"]
    
    async def deposit(self, guild_id: int, user_id: int, amount: Optional[int]) -> int:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            if user["wallet"] <= 0:
                return 0
            if amount is None or amount > user["wallet"]:
                deposit_amount = user["wallet"]
            else:
                deposit_amount = amount
            if deposit_amount <= 0:
                return 0
            user["wallet"] -= deposit_amount
            user["bank"] += deposit_amount
            return deposit_amount
    
    async def withdraw(self, guild_id: int, user_id: int, amount: Optional[int]) -> int:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            if user["bank"] <= 0:
                return 0
            if amount is None or amount > user["bank"]:
                withdraw_amount = user["bank"]
            else:
                withdraw_amount = amount
            if withdraw_amount <= 0:
                return 0
            user["bank"] -= withdraw_amount
            user["wallet"] += withdraw_amount
            return withdraw_amount
    
    async def add_wallet(self, guild_id: int, user_id: int, amount: int) -> int:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            user["wallet"] += max(0, amount)
            return user["wallet"]
    
    async def add_bank(self, guild_id: int, user_id: int, amount: int) -> int:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            user["bank"] += max(0, amount)
            return user["bank"]
    
    async def deduct_wallet(self, guild_id: int, user_id: int, amount: int) -> bool:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            if amount <= 0 or user["wallet"] < amount:
                return False
            user["wallet"] -= amount
            return True
    
    async def has_wallet(self, guild_id: int, user_id: int, amount: int) -> bool:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            return user["wallet"] >= amount
    
    async def get_inventory(self, guild_id: int, user_id: int) -> Dict[str, int]:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            return dict(user["inventory"])
    
    async def add_item(self, guild_id: int, user_id: int, item_key: str, amount: int = 1) -> None:
        async with self.lock:
            if item_key not in ITEM_DATA:
                return
            user = self._ensure_user(guild_id, user_id)
            inventory = user["inventory"]
            inventory[item_key] = inventory.get(item_key, 0) + max(0, amount)
    
    async def sell_items(self, guild_id: int, user_id: int, item_key: Optional[str], quantity: Optional[int]) -> Tuple[List[Tuple[str, int, int]], int]:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            inventory = user["inventory"]
            if not inventory:
                return [], 0
            details: List[Tuple[str, int, int]] = []
            total_value = 0
            
            def sell_specific(key: str, qty: int) -> None:
                nonlocal total_value
                if key not in ITEM_DATA or qty <= 0:
                    return
                value_data = ITEM_DATA[key]
                if not value_data.get("sellable", True):
                    return
                sold_value = 0
                for _ in range(qty):
                    sold_value += random.randint(value_data["min_value"], value_data["max_value"])
                inventory[key] -= qty
                if inventory[key] <= 0:
                    inventory.pop(key, None)
                details.append((key, qty, sold_value))
                total_value += sold_value
            
            if item_key is None:
                for key, count in list(inventory.items()):
                    sell_specific(key, count)
            else:
                if item_key not in inventory or inventory[item_key] <= 0:
                    return [], 0
                available = inventory[item_key]
                sell_quantity = available if quantity is None else min(quantity, available)
                if sell_quantity <= 0:
                    return [], 0
                sell_specific(item_key, sell_quantity)
            
            if total_value > 0:
                user["wallet"] += total_value
            return details, total_value
    
    async def leaderboard(self, guild_id: int, limit: int = 10) -> List[Tuple[int, int, int, int]]:
        async with self.lock:
            standings: List[Tuple[int, int, int, int]] = []
            if guild_id not in self.guilds:
                return []
            for user_id, payload in self.guilds[guild_id].items():
                wallet = payload.get("wallet", 0)
                bank = payload.get("bank", 0)
                total = wallet + bank
                standings.append((int(user_id), wallet, bank, total))
            standings.sort(key=lambda item: item[3], reverse=True)
            return standings[:limit]
    
    async def has_item(self, guild_id: int, user_id: int, item_key: str) -> bool:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            return user["inventory"].get(item_key, 0) > 0
    
    async def has_items(self, guild_id: int, user_id: int, item_keys: List[str]) -> bool:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            inventory = user["inventory"]
            return all(inventory.get(key, 0) > 0 for key in item_keys)
    
    async def seize_all_items(self, guild_id: int, user_id: int) -> Dict[str, int]:
        async with self.lock:
            user = self._ensure_user(guild_id, user_id)
            seized = dict(user["inventory"])
            user["inventory"] = {}
            return seized


class JobsManager:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lock = asyncio.Lock()
        # Structure: {guild_id: {user_id: job_key or None}}
        self.guild_jobs: Dict[int, Dict[int, Optional[str]]] = {}
        # Structure: {guild_id: {user_id: cooldown_end}}
        self.decline_cooldowns: Dict[int, Dict[int, datetime]] = {}
        self.job_tasks: Dict[int, asyncio.Task] = {}  # user_id -> payout task
    
    async def load(self) -> None:
        async with self.lock:
            if not self.file_path.exists():
                self.guild_jobs = {}
                self.decline_cooldowns = {}
                return
            try:
                with open(self.file_path, "r") as f:
                    data = json.load(f)
                # Support both old format (migration) and new format
                if "guilds" in data:
                    # New format: {guilds: {guild_id: {user_jobs: {...}, decline_cooldowns: {...}}}}
                    self.guild_jobs = {}
                    self.decline_cooldowns = {}
                    for guild_id_str, guild_data in data["guilds"].items():
                        guild_id = int(guild_id_str)
                        self.guild_jobs[guild_id] = {int(k): v for k, v in guild_data.get("user_jobs", {}).items()}
                        raw_cooldowns = guild_data.get("decline_cooldowns", {})
                        self.decline_cooldowns[guild_id] = {}
                        for user_id, cooldown_str in raw_cooldowns.items():
                            if cooldown_str:
                                self.decline_cooldowns[guild_id][int(user_id)] = datetime.fromisoformat(cooldown_str)
                else:
                    # Old format migration: convert to per-guild structure
                    self.guild_jobs = {}
                    self.decline_cooldowns = {}
            except Exception:
                self.guild_jobs = {}
                self.decline_cooldowns = {}
    
    async def save(self) -> None:
        async with self.lock:
            data = {
                "guilds": {
                    str(guild_id): {
                        "user_jobs": {str(k): v for k, v in guild_jobs.items()},
                        "decline_cooldowns": {
                            str(k): v.isoformat() if v else None
                            for k, v in self.decline_cooldowns.get(guild_id, {}).items()
                        }
                    }
                    for guild_id, guild_jobs in self.guild_jobs.items()
                }
            }
            with open(self.file_path, "w") as f:
                json.dump(data, f, indent=2)
    
    async def get_job(self, guild_id: int, user_id: int) -> Optional[str]:
        async with self.lock:
            if guild_id not in self.guild_jobs:
                return None
            return self.guild_jobs[guild_id].get(user_id)
    
    async def set_job(self, guild_id: int, user_id: int, job_key: Optional[str]) -> None:
        async with self.lock:
            if guild_id not in self.guild_jobs:
                self.guild_jobs[guild_id] = {}
            if job_key is None:
                self.guild_jobs[guild_id].pop(user_id, None)
            else:
                self.guild_jobs[guild_id][user_id] = job_key
    
    async def can_apply(self, guild_id: int, user_id: int) -> Tuple[bool, Optional[str]]:
        """Returns (can_apply, reason)"""
        async with self.lock:
            if guild_id in self.guild_jobs and user_id in self.guild_jobs[guild_id] and self.guild_jobs[guild_id][user_id] is not None:
                return False, "You already have a job. Use /quitjob first."
            
            if guild_id in self.decline_cooldowns and user_id in self.decline_cooldowns[guild_id]:
                cooldown_end = self.decline_cooldowns[guild_id][user_id]
                if cooldown_end > datetime.now(timezone.utc):
                    remaining = (cooldown_end - datetime.now(timezone.utc)).total_seconds()
                    minutes = int(remaining / 60)
                    seconds = int(remaining % 60)
                    return False, f"You must wait {minutes}m {seconds}s before applying again."
            
            return True, None
    
    async def set_decline_cooldown(self, guild_id: int, user_id: int) -> None:
        async with self.lock:
            if guild_id not in self.decline_cooldowns:
                self.decline_cooldowns[guild_id] = {}
            cooldown_end = datetime.now(timezone.utc) + timedelta(minutes=10)
            self.decline_cooldowns[guild_id][user_id] = cooldown_end
    
    async def clear_cooldown(self, guild_id: int, user_id: int) -> None:
        async with self.lock:
            if guild_id in self.decline_cooldowns:
                self.decline_cooldowns[guild_id].pop(user_id, None)


def generate_guild_id() -> str:
    """Generate a random 6 character alphanumeric ID"""
    import string
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


class GuildsManager:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lock = asyncio.Lock()
        # Structure: {discord_guild_id: {player_guild_id: guild_data}}
        self.server_guilds: Dict[int, Dict[str, Dict[str, Any]]] = {}
        # Structure: {discord_guild_id: {user_id: player_guild_id or None}}
        self.user_guilds: Dict[int, Dict[int, Optional[str]]] = {}
    
    async def load(self) -> None:
        async with self.lock:
            if not self.file_path.exists():
                self.server_guilds = {}
                self.user_guilds = {}
                return
            try:
                with open(self.file_path, "r") as f:
                    data = json.load(f)
                # Support both old format (migration) and new format
                if "servers" in data:
                    # New format: {servers: {discord_guild_id: {guilds: {...}, user_guilds: {...}}}}
                    self.server_guilds = {}
                    self.user_guilds = {}
                    for server_id_str, server_data in data["servers"].items():
                        server_id = int(server_id_str)
                        self.server_guilds[server_id] = server_data.get("guilds", {})
                        self.user_guilds[server_id] = {int(k): v for k, v in server_data.get("user_guilds", {}).items()}
                else:
                    # Old format migration: convert to per-server structure
                    self.server_guilds = {}
                    self.user_guilds = {}
            except Exception:
                self.server_guilds = {}
                self.user_guilds = {}
    
    async def save(self) -> None:
        async with self.lock:
            data = {
                "servers": {
                    str(server_id): {
                        "guilds": guilds,
                        "user_guilds": {str(k): v for k, v in self.user_guilds.get(server_id, {}).items()}
                    }
                    for server_id, guilds in self.server_guilds.items()
                }
            }
            with open(self.file_path, "w") as f:
                json.dump(data, f, indent=2)
    
    def _get_guilds(self, discord_guild_id: int) -> Dict[str, Dict[str, Any]]:
        """Get guilds dict for a Discord server"""
        if discord_guild_id not in self.server_guilds:
            self.server_guilds[discord_guild_id] = {}
        return self.server_guilds[discord_guild_id]
    
    def _get_user_guilds(self, discord_guild_id: int) -> Dict[int, Optional[str]]:
        """Get user_guilds dict for a Discord server"""
        if discord_guild_id not in self.user_guilds:
            self.user_guilds[discord_guild_id] = {}
        return self.user_guilds[discord_guild_id]
    
    async def create_guild(self, discord_guild_id: int, owner_id: int, display_name: str, image_url: str, privacy: str, password: Optional[str] = None) -> Optional[str]:
        """Returns guild_id if created, None if failed"""
        async with self.lock:
            guilds = self._get_guilds(discord_guild_id)
            user_guilds = self._get_user_guilds(discord_guild_id)
            # Generate unique ID
            guild_id = generate_guild_id()
            while guild_id in guilds:
                guild_id = generate_guild_id()
            
            guilds[guild_id] = {
                "owner_id": owner_id,
                "display_name": display_name,
                "image_url": image_url,
                "privacy": privacy,
                "password": password,
                "members": [owner_id],
                "member_cap": None,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            user_guilds[owner_id] = guild_id
            return guild_id
    
    async def get_guild(self, discord_guild_id: int, guild_id: str) -> Optional[Dict[str, Any]]:
        async with self.lock:
            guilds = self._get_guilds(discord_guild_id)
            return guilds.get(guild_id)
    
    async def get_user_guild(self, discord_guild_id: int, user_id: int) -> Optional[str]:
        async with self.lock:
            user_guilds = self._get_user_guilds(discord_guild_id)
            return user_guilds.get(user_id)
    
    async def join_guild(self, discord_guild_id: int, user_id: int, guild_id: str) -> Tuple[bool, Optional[str]]:
        """Returns (success, error_message)"""
        async with self.lock:
            guilds = self._get_guilds(discord_guild_id)
            user_guilds = self._get_user_guilds(discord_guild_id)
            if user_id in user_guilds and user_guilds[user_id] is not None:
                return False, "You are already in a guild."
            
            guild = guilds.get(guild_id)
            if not guild:
                return False, "Guild not found."
            
            if user_id in guild["members"]:
                return False, "You are already a member of this guild."
            
            if guild["member_cap"] and len(guild["members"]) >= guild["member_cap"]:
                return False, "This guild is full."
            
            guild["members"].append(user_id)
            user_guilds[user_id] = guild_id
            return True, None
    
    async def leave_guild(self, discord_guild_id: int, user_id: int) -> bool:
        """Returns True if left, False if not in a guild"""
        async with self.lock:
            guilds = self._get_guilds(discord_guild_id)
            user_guilds = self._get_user_guilds(discord_guild_id)
            guild_id = user_guilds.get(user_id)
            if not guild_id:
                return False
            
            guild = guilds.get(guild_id)
            if guild:
                if user_id in guild["members"]:
                    guild["members"].remove(user_id)
                if guild["owner_id"] == user_id:
                    # Owner left, disband guild
                    for member_id in guild["members"]:
                        user_guilds.pop(member_id, None)
                    guilds.pop(guild_id, None)
                else:
                    user_guilds.pop(user_id, None)
            else:
                user_guilds.pop(user_id, None)
            return True
    
    async def kick_member(self, discord_guild_id: int, owner_id: int, target_id: int) -> Tuple[bool, Optional[str]]:
        """Returns (success, error_message)"""
        async with self.lock:
            guilds = self._get_guilds(discord_guild_id)
            user_guilds = self._get_user_guilds(discord_guild_id)
            guild_id = user_guilds.get(owner_id)
            if not guild_id:
                return False, "You are not in a guild."
            
            guild = guilds.get(guild_id)
            if not guild or guild["owner_id"] != owner_id:
                return False, "You are not the owner of this guild."
            
            if target_id not in guild["members"]:
                return False, "User is not a member of this guild."
            
            if target_id == owner_id:
                return False, "You cannot kick yourself."
            
            guild["members"].remove(target_id)
            user_guilds.pop(target_id, None)
            return True, None
    
    async def transfer_ownership(self, discord_guild_id: int, owner_id: int, new_owner_id: int) -> Tuple[bool, Optional[str]]:
        """Returns (success, error_message)"""
        async with self.lock:
            guilds = self._get_guilds(discord_guild_id)
            user_guilds = self._get_user_guilds(discord_guild_id)
            guild_id = user_guilds.get(owner_id)
            if not guild_id:
                return False, "You are not in a guild."
            
            guild = guilds.get(guild_id)
            if not guild or guild["owner_id"] != owner_id:
                return False, "You are not the owner of this guild."
            
            if new_owner_id not in guild["members"]:
                return False, "User is not a member of this guild."
            
            if new_owner_id == owner_id:
                return False, "You are already the owner."
            
            guild["owner_id"] = new_owner_id
            return True, None
    
    async def disband_guild(self, discord_guild_id: int, owner_id: int) -> bool:
        """Returns True if disbanded"""
        async with self.lock:
            guilds = self._get_guilds(discord_guild_id)
            user_guilds = self._get_user_guilds(discord_guild_id)
            guild_id = user_guilds.get(owner_id)
            if not guild_id:
                return False
            
            guild = guilds.get(guild_id)
            if not guild or guild["owner_id"] != owner_id:
                return False
            
            for member_id in guild["members"]:
                user_guilds.pop(member_id, None)
            guilds.pop(guild_id, None)
            return True
    
    async def rename_guild(self, discord_guild_id: int, owner_id: int, new_display_name: str) -> bool:
        """Returns True if renamed"""
        async with self.lock:
            guilds = self._get_guilds(discord_guild_id)
            user_guilds = self._get_user_guilds(discord_guild_id)
            guild_id = user_guilds.get(owner_id)
            if not guild_id:
                return False
            
            guild = guilds.get(guild_id)
            if not guild or guild["owner_id"] != owner_id:
                return False
            
            guild["display_name"] = new_display_name
            return True
    
    async def set_member_cap(self, discord_guild_id: int, owner_id: int, cap: Optional[int]) -> bool:
        """Returns True if set"""
        async with self.lock:
            guilds = self._get_guilds(discord_guild_id)
            user_guilds = self._get_user_guilds(discord_guild_id)
            guild_id = user_guilds.get(owner_id)
            if not guild_id:
                return False
            
            guild = guilds.get(guild_id)
            if not guild or guild["owner_id"] != owner_id:
                return False
            
            guild["member_cap"] = cap
            return True
    
    async def list_guilds(self, discord_guild_id: int) -> List[Tuple[str, Dict[str, Any]]]:
        """Returns list of (guild_id, guild_data) tuples"""
        async with self.lock:
            guilds = self._get_guilds(discord_guild_id)
            return [(gid, gdata) for gid, gdata in guilds.items()]
    
    async def get_guild_leaderboard(self, discord_guild_id: int, guild_id: str, economy_manager: 'EconomyManager') -> List[Tuple[int, int, int, int]]:
        """Returns list of (user_id, wallet, bank, total) sorted by total"""
        async with self.lock:
            guilds = self._get_guilds(discord_guild_id)
            guild = guilds.get(guild_id)
            if not guild:
                return []
            
            standings = []
            for user_id in guild["members"]:
                wallet, bank = await economy_manager.get_balances(discord_guild_id, user_id)
                total = wallet + bank
                standings.append((user_id, wallet, bank, total))
            
            standings.sort(key=lambda x: x[3], reverse=True)
            return standings
    
    async def get_guild_leaderboard_all(self, discord_guild_id: int, economy_manager: 'EconomyManager') -> List[Tuple[str, int]]:
        """Returns list of (guild_id, total_wealth) sorted by total_wealth"""
        async with self.lock:
            guilds = self._get_guilds(discord_guild_id)
            guild_totals = []
            for guild_id, guild_data in guilds.items():
                total_wealth = 0
                for user_id in guild_data["members"]:
                    wallet, bank = await economy_manager.get_balances(discord_guild_id, user_id)
                    total_wealth += wallet + bank
                guild_totals.append((guild_id, total_wealth))
            
            guild_totals.sort(key=lambda x: x[1], reverse=True)
            return guild_totals


class AchievementsManager:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lock = asyncio.Lock()
        # Structure: {guild_id: {user_id: set of achievement keys}}
        self.guild_achievements: Dict[int, Dict[int, set[str]]] = {}
    
    async def load(self) -> None:
        async with self.lock:
            if not self.file_path.exists():
                self.guild_achievements = {}
                return
            try:
                with open(self.file_path, "r") as f:
                    data = json.load(f)
                # Support both old format (migration) and new format
                if "guilds" in data:
                    # New format: {guilds: {guild_id: {user_achievements: {...}}}}
                    self.guild_achievements = {}
                    for guild_id_str, guild_data in data["guilds"].items():
                        guild_id = int(guild_id_str)
                        self.guild_achievements[guild_id] = {
                            int(user_id): set(achievements)
                            for user_id, achievements in guild_data.get("user_achievements", {}).items()
                        }
                else:
                    # Old format migration: convert to per-guild structure
                    self.guild_achievements = {}
            except Exception:
                self.guild_achievements = {}
    
    async def save(self) -> None:
        async with self.lock:
            data = {
                "guilds": {
                    str(guild_id): {
                        "user_achievements": {
                            str(user_id): list(achievements)
                            for user_id, achievements in user_achievements.items()
                        }
                    }
                    for guild_id, user_achievements in self.guild_achievements.items()
                }
            }
            with open(self.file_path, "w") as f:
                json.dump(data, f, indent=2)
    
    async def has_achievement(self, guild_id: int, user_id: int, achievement_key: str) -> bool:
        async with self.lock:
            if guild_id not in self.guild_achievements:
                return False
            return achievement_key in self.guild_achievements[guild_id].get(user_id, set())
    
    async def unlock_achievement(self, guild_id: int, user_id: int, achievement_key: str) -> bool:
        """Returns True if newly unlocked, False if already had it"""
        async with self.lock:
            if guild_id not in self.guild_achievements:
                self.guild_achievements[guild_id] = {}
            if user_id not in self.guild_achievements[guild_id]:
                self.guild_achievements[guild_id][user_id] = set()
            
            if achievement_key in self.guild_achievements[guild_id][user_id]:
                return False
            
            self.guild_achievements[guild_id][user_id].add(achievement_key)
            return True
    
    async def get_user_achievements(self, guild_id: int, user_id: int) -> set[str]:
        async with self.lock:
            if guild_id not in self.guild_achievements:
                return set()
            return self.guild_achievements[guild_id].get(user_id, set()).copy()

