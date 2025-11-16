# Economy Cog
import asyncio
import random
from typing import List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from config import ITEM_DATA, SHOP_ITEMS
from managers import EconomyManager
from utils import currency, resolve_item_key, embedbuildthing


def describe_items(items: List[Tuple[str, int, int]]) -> List[str]:
    lines = []
    for key, qty, value in items:
        item_name = ITEM_DATA[key]["name"]
        lines.append(f"{item_name} x{qty} • {currency(value)}")
    return lines


class CoinflipView(discord.ui.View):
    def __init__(self, manager: EconomyManager, challenger_id: int, target_id: int, amount: int, bot: commands.Bot):
        super().__init__(timeout=60)
        self.manager = manager
        self.challenger_id = challenger_id
        self.target_id = target_id
        self.amount = amount
        self.message: Optional[discord.Message] = None
        self.bot = bot
    
    def _disable_controls(self) -> None:
        for child in self.children:
            child.disabled = True
    
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.target_id:
            await interaction.response.defer()
            return
        challenger_has = await self.manager.has_wallet(self.challenger_id, self.amount)
        target_has = await self.manager.has_wallet(self.target_id, self.amount)
        if not challenger_has or not target_has:
            self._disable_controls()
            missing = self.challenger_id if not challenger_has else self.target_id
            content = f"<@{missing}> does not have enough funds for the coinflip."
            await interaction.response.edit_message(content=content, view=self)
            await self.manager.save()
            return
        if not await self.manager.deduct_wallet(self.challenger_id, self.amount):
            self._disable_controls()
            content = f"<@{self.challenger_id}> no longer has enough funds for the coinflip."
            await interaction.response.edit_message(content=content, view=self)
            await self.manager.save()
            return
        if not await self.manager.deduct_wallet(self.target_id, self.amount):
            await self.manager.add_wallet(self.challenger_id, self.amount)
            self._disable_controls()
            content = f"<@{self.target_id}> no longer has enough funds for the coinflip."
            await interaction.response.edit_message(content=content, view=self)
            await self.manager.save()
            return
        winner_id = random.choice([self.challenger_id, self.target_id])
        await self.manager.add_wallet(winner_id, self.amount * 2)
        self._disable_controls()
        content = (
            f"<@{self.target_id}> accepted the coinflip from <@{self.challenger_id}>. "
            f"<@{winner_id}> wins {currency(self.amount)}."
        )
        await interaction.response.edit_message(content=content, view=self)
        await self.manager.save()
        
        # Check balance achievements for winner
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_balance_achievements(winner_id)
    
    @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.target_id:
            await interaction.response.defer()
            return
        self.disable_all_items()
        content = f"<@{self.target_id}> declined the coinflip from <@{self.challenger_id}>."
        await interaction.response.edit_message(content=content, view=self)
    
    async def on_timeout(self) -> None:
        self.disable_all_items()
        if self.message:
            await self.message.edit(content="Coinflip request expired.", view=self)


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot, manager: EconomyManager):
        self.bot = bot
        self.manager = manager
    
    async def cog_load(self) -> None:
        await self.manager.load()
    
    @app_commands.guild_only()
    @app_commands.command(name="balance", description="Check wallet and bank balances")
    async def balance(self, interaction: discord.Interaction, user: Optional[discord.User] = None) -> None:
        target = user or interaction.user
        await self.manager.ensure_user(str(interaction.guild.id), target.id)
        wallet, bank = await self.manager.get_balances(str(interaction.guild.id), target.id)
        embed = embedbuildthing("Balance")
        if hasattr(target, "display_avatar"):
            embed.set_author(name=str(target), icon_url=target.display_avatar.url)
        else:
            embed.set_author(name=str(target))
        embed.add_field(name="Wallet", value=currency(wallet), inline=False)
        embed.add_field(name="Bank", value=currency(bank), inline=False)
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
        
        # Check balance achievements
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_balance_achievements(target.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="deposit", description="Deposit money into your bank")
    async def deposit(self, interaction: discord.Interaction, amount: Optional[int] = None) -> None:
        if amount is not None and amount <= 0:
            embed = embedbuildthing("Invalid Amount", "Enter a positive amount to deposit.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        deposited = await self.manager.deposit(interaction.user.id, amount)
        if deposited <= 0:
            embed = embedbuildthing("Deposit Failed", "No funds available in your wallet.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        embed = embedbuildthing("Deposit Successful", f"Deposited {currency(deposited)} into your bank.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
        
        # Check balance achievements
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_balance_achievements(interaction.user.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="withdraw", description="Withdraw money from your bank")
    async def withdraw(self, interaction: discord.Interaction, amount: Optional[int] = None) -> None:
        if amount is not None and amount <= 0:
            embed = embedbuildthing("Invalid Amount", "Enter a positive amount to withdraw.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        withdrawn = await self.manager.withdraw(interaction.user.id, amount)
        if withdrawn <= 0:
            embed = embedbuildthing("Withdraw Failed", "No funds available in your bank.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        embed = embedbuildthing("Withdraw Successful", f"Withdrew {currency(withdrawn)} into your wallet.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
        
        # Check balance achievements
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_balance_achievements(interaction.user.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="leaderboard", description="Show the top guilds by total wealth")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        from managers import GuildsManager
        # Get guilds manager from bot
        guilds_cog = self.bot.get_cog("Guilds")
        if not guilds_cog:
            embed = embedbuildthing("Error", "Guilds system not available.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        guilds_manager = guilds_cog.guilds_manager
        guild_standings = await guilds_manager.get_guild_leaderboard_all(self.manager)
        
        if not guild_standings:
            embed = embedbuildthing("Leaderboard", "No guilds found.")
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        
        lines = []
        top_guild = None
        for index, (guild_id, total_wealth) in enumerate(guild_standings[:10], start=1):
            guild = await guilds_manager.get_guild(guild_id)
            if guild:
                display_name = guild["display_name"]
                member_count = len(guild["members"])
                if index == 1:
                    top_guild = guild
                lines.append(f"{index}. **{display_name}** (`{guild_id}`) • {currency(total_wealth)} • {member_count} member{'s' if member_count != 1 else ''}")
        
        embed = embedbuildthing("Guild Leaderboard", "\n".join(lines))
        if top_guild and top_guild.get("image_url"):
            embed.set_thumbnail(url=top_guild["image_url"])
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
        
        # Check leaderboard achievement for all users in top 5 guilds
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            for guild_id, _ in guild_standings[:5]:
                guild = await guilds_manager.get_guild(guild_id)
                if guild:
                    for member_id in guild["members"]:
                        await achievements_cog.check_guild_achievements(member_id)
    
    @app_commands.guild_only()
    @app_commands.command(name="inventory", description="Show your inventory")
    async def inventory(self, interaction: discord.Interaction) -> None:
        await self.manager.ensure_user(interaction.user.id)
        inventory = await self.manager.get_inventory(interaction.user.id)
        if not inventory:
            embed = embedbuildthing("Inventory", "You have no items.")
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        lines = []
        for key, amount in inventory.items():
            item_name = ITEM_DATA[key]["name"]
            lines.append(f"{item_name} x{amount}")
        embed = embedbuildthing("Inventory", "\n".join(lines))
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
        
        # Check inventory achievements
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_inventory_achievements(interaction.user.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="sell", description="Sell items from your inventory")
    @app_commands.describe(item="Item to sell", amount="Quantity to sell")
    async def sell(self, interaction: discord.Interaction, item: Optional[str] = None, amount: Optional[int] = None) -> None:
        if amount is not None and amount <= 0:
            embed = embedbuildthing("Invalid Amount", "Enter a positive amount to sell.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        item_key = None
        if item:
            resolved = resolve_item_key(item)
            if not resolved:
                embed = embedbuildthing("Invalid Item", "That item does not exist.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed)
                await self.manager.save()
                return
            item_key = resolved
        details, total_value = await self.manager.sell_items(interaction.user.id, item_key, amount)
        if not details:
            embed = embedbuildthing("Nothing Sold", "You have no items to sell.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        lines = describe_items(details)
        embed = embedbuildthing("Items Sold", "\n".join(lines), color=discord.Color.green())
        embed.add_field(name="Total Earned", value=currency(total_value), inline=False)
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
        
        # Check balance achievements after selling
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_balance_achievements(interaction.user.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="beg", description="Beg for money")
    async def beg(self, interaction: discord.Interaction) -> None:
        roll = random.random()
        if roll < 0.33:
            description = "You received nothing."
        elif roll < 0.66:
            amount = random.randint(3, 5)
            await self.manager.add_wallet(interaction.user.id, amount)
            description = f"You received {currency(amount)}."
        elif roll < 0.81:
            amount = random.randint(9, 16)
            await self.manager.add_wallet(interaction.user.id, amount)
            description = f"You received {currency(amount)}."
        elif roll < 0.86:
            await self.manager.add_item(interaction.user.id, "golden_potato")
            description = "You found a Golden Potato."
            
            # Check inventory achievements
            achievements_cog = self.bot.get_cog("Achievements")
            if achievements_cog:
                await achievements_cog.check_inventory_achievements(interaction.user.id)
        elif roll < 0.87:
            await self.manager.add_bank(interaction.user.id, 120)
            description = "You found a wallet with $120 and placed it in your bank."
            
            # Check balance achievements
            achievements_cog = self.bot.get_cog("Achievements")
            if achievements_cog:
                await achievements_cog.check_balance_achievements(interaction.user.id)
        else:
            description = "You received nothing."
        embed = embedbuildthing("Begging Results", description)
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
        
        # Check balance achievements
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_balance_achievements(interaction.user.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="fish", description="Go fishing")
    async def fish(self, interaction: discord.Interaction) -> None:
        roll = random.random()
        catch = None
        if roll < 0.20:
            catch = "rainbow_trout"
        elif roll < 0.35:
            catch = "bass"
        elif roll < 0.50:
            catch = "sunfish"
        elif roll < 0.60:
            catch = "spearfish"
        elif roll < 0.70:
            catch = "voltfish"
        elif roll < 0.701:
            catch = "angel_o8"
        if catch:
            await self.manager.add_item(interaction.user.id, catch)
            item_name = ITEM_DATA[catch]["name"]
            embed = embedbuildthing("Fishing Results", f"You caught a {item_name}.")
            
            # Check inventory achievements
            achievements_cog = self.bot.get_cog("Achievements")
            if achievements_cog:
                await achievements_cog.check_inventory_achievements(interaction.user.id)
        else:
            embed = embedbuildthing("Fishing Results", "You caught nothing.")
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
    
    @app_commands.guild_only()
    @app_commands.command(name="gamble", description="Gamble your money")
    async def gamble(self, interaction: discord.Interaction, amount: int) -> None:
        if amount <= 0:
            embed = embedbuildthing("Invalid Amount", "Enter a positive amount to gamble.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        if not await self.manager.has_wallet(interaction.user.id, amount):
            embed = embedbuildthing("Insufficient Funds", "You do not have enough money in your wallet.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        if not await self.manager.deduct_wallet(interaction.user.id, amount):
            embed = embedbuildthing("Insufficient Funds", "You do not have enough money in your wallet.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        roll = random.random()
        if roll < 0.70:
            returned = amount // 2
            if returned > 0:
                await self.manager.add_wallet(interaction.user.id, returned)
            result = f"You halved your bet and received {currency(returned)}."
        elif roll < 0.80:
            result = "You lost everything you gambled."
        else:
            winnings = amount * 2
            await self.manager.add_wallet(interaction.user.id, winnings)
            result = f"You doubled your bet and won {currency(winnings)}."
        embed = embedbuildthing("Gamble Results", result)
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
        
        # Check balance achievements
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_balance_achievements(interaction.user.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="donate", description="Donate money to another user")
    @app_commands.describe(user="Recipient", amount="Amount to donate")
    async def donate(self, interaction: discord.Interaction, user: discord.Member, amount: int) -> None:
        if user.id == interaction.user.id:
            embed = embedbuildthing("Invalid Recipient", "You cannot donate to yourself.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        if amount <= 0:
            embed = embedbuildthing("Invalid Amount", "Enter a positive amount to donate.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        if not await self.manager.has_wallet(interaction.user.id, amount):
            embed = embedbuildthing("Insufficient Funds", "You do not have enough money in your wallet.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        if not await self.manager.deduct_wallet(interaction.user.id, amount):
            embed = embedbuildthing("Insufficient Funds", "You do not have enough money in your wallet.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        await self.manager.add_wallet(user.id, amount)
        embed = embedbuildthing("Donation Successful", f"Donated {currency(amount)} to {user.mention}.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
        
        # Check balance achievements for recipient
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_balance_achievements(user.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="givemoney", description="Give money to a user (admin only)")
    @app_commands.describe(user="User to receive money", amount="Amount to give")
    async def givemoney(self, interaction: discord.Interaction, user: discord.Member, amount: int) -> None:
        from utils import is_admin
        if not is_admin(interaction.user):
            embed = embedbuildthing("Permission Denied", "You must have too many permissions to use this command.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        if amount <= 0:
            embed = embedbuildthing("Invalid Amount", "Enter a positive amount to give.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        await self.manager.add_wallet(user.id, amount)
        embed = embedbuildthing("Funds Granted", f"Gave {currency(amount)} to {user.mention}.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
        
        # Check balance achievements for recipient
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_balance_achievements(user.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="giveitem", description="Give an item to a user (admin only)")
    @app_commands.describe(user="User to receive the item")
    @app_commands.choices(item=[app_commands.Choice(name=data["name"], value=key) for key, data in ITEM_DATA.items()])
    async def giveitem(self, interaction: discord.Interaction, user: discord.Member, item: app_commands.Choice[str]) -> None:
        from utils import is_admin
        if not is_admin(interaction.user):
            embed = embedbuildthing("Permission Denied", "You must have a whole lotta permissions to use this command.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        await self.manager.add_item(user.id, item.value)
        item_name = ITEM_DATA[item.value]["name"]
        embed = embedbuildthing("Item Granted", f"Gave {item_name} to {user.mention}.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
        
        # Check inventory achievements for recipient
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_inventory_achievements(user.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="coinflip", description="Coinflip another user")
    @app_commands.describe(user="Opponent", amount="Amount to wager")
    async def coinflip(self, interaction: discord.Interaction, user: discord.Member, amount: int) -> None:
        if user.id == interaction.user.id:
            embed = embedbuildthing("Invalid Opponent", "You cannot coinflip yourself.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        if amount <= 0:
            embed = embedbuildthing("Invalid Amount", "Enter a positive amount to wager.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        if not await self.manager.has_wallet(interaction.user.id, amount):
            embed = embedbuildthing("Insufficient Funds", "You do not have enough money in your wallet.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        await self.manager.ensure_user(user.id)
        if not await self.manager.has_wallet(user.id, amount):
            embed = embedbuildthing("Opponent Funds", f"{user.mention} does not have enough money to coinflip.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        view = CoinflipView(self.manager, interaction.user.id, user.id, amount, self.bot)
        content = f"{interaction.user.mention} challenged {user.mention} to a coinflip for {currency(amount)}."
        await interaction.response.send_message(content=content, view=view)
        view.message = await interaction.original_response()
        await self.manager.save()
    
    @app_commands.guild_only()
    @app_commands.command(name="shop", description="Buy items from the shop")
    @app_commands.describe(item="Item to buy")
    @app_commands.choices(item=[app_commands.Choice(name=ITEM_DATA[key]["name"], value=key) for key in SHOP_ITEMS])
    async def shop(self, interaction: discord.Interaction, item: app_commands.Choice[str]) -> None:
        item_key = item.value
        item_data = ITEM_DATA[item_key]
        price = item_data["price"]
        
        if not await self.manager.has_wallet(interaction.user.id, price):
            embed = embedbuildthing("Insufficient Funds", f"You need {currency(price)} to buy {item_data['name']}.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        
        if not await self.manager.deduct_wallet(interaction.user.id, price):
            embed = embedbuildthing("Insufficient Funds", f"You need {currency(price)} to buy {item_data['name']}.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        
        await self.manager.add_item(interaction.user.id, item_key)
        embed = embedbuildthing("Purchase Successful", f"Bought {item_data['name']} for {currency(price)}.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
        await self.manager.save()
        
        # Check inventory achievements
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_inventory_achievements(interaction.user.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="robbery", description="Rob a location")
    @app_commands.describe(location="Location to rob")
    @app_commands.choices(location=[
        app_commands.Choice(name="Gas Station", value="gas_station"),
        app_commands.Choice(name="House", value="house"),
        app_commands.Choice(name="Jewelry Store", value="jewelry_store"),
        app_commands.Choice(name="Government Laboratory", value="lab"),
    ])
    async def robbery(self, interaction: discord.Interaction, location: app_commands.Choice[str]) -> None:
        location_type = location.value
        inventory = await self.manager.get_inventory(interaction.user.id)
        
        robbery_configs = {
            "gas_station": {
                "name": "Gas Station",
                "required_items": [],
                "time": 30,
                "min_payout": 300,
                "max_payout": 700,
                "base_catch_chance": 0.20,
                "wallet_penalty": 0.60,
                "bank_penalty": 0.05,
                "seize_items": False,
            },
            "house": {
                "name": "House",
                "required_items": ["lockpick"],
                "time": 60,
                "min_payout": 2000,
                "max_payout": 3000,
                "base_catch_chance": 0.60,
                "wallet_penalty": 0.60,
                "bank_penalty": 0.05,
                "seize_items": True,
            },
            "jewelry_store": {
                "name": "Jewelry Store",
                "required_items": ["lockpick", "gun"],
                "time": 90,
                "min_payout": 10000,
                "max_payout": 16000,
                "base_catch_chance": 0.90,
                "wallet_penalty": 0.75,
                "bank_penalty": 0.10,
                "seize_items": True,
            },
            "lab": {
                "name": "Government Laboratory",
                "required_items": ["advanced_lockpick", "gun", "hacker_tool"],
                "time": 180,
                "min_payout": 200000,
                "max_payout": 400000,
                "base_catch_chance": 0.95,
                "wallet_penalty": 0.80,
                "bank_penalty": 0.15,
                "seize_items": True,
            },
        }
        
        config = robbery_configs[location_type]
        
        if not await self.manager.has_items(interaction.user.id, config["required_items"]):
            missing = [ITEM_DATA[item]["name"] for item in config["required_items"] if not inventory.get(item, 0)]
            embed = embedbuildthing("Missing Requirements", f"You need: {', '.join(missing)}", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        
        await interaction.response.defer()
        
        catch_chance = config["base_catch_chance"]
        has_mask = inventory.get("mask", 0) > 0
        has_lpb = inventory.get("license_plate_blocker", 0) > 0
        
        if location_type == "lab":
            if has_mask:
                catch_chance -= 0.05
            if has_lpb:
                catch_chance -= 0.03
        else:
            if has_mask:
                catch_chance -= 0.10
            if has_lpb:
                catch_chance -= 0.25
        
        catch_chance = max(0.0, min(1.0, catch_chance))
        
        embed = embedbuildthing("Robbery in Progress", f"Robbing {config['name']}... This will take {config['time']} seconds.", color=discord.Color.orange())
        embed.add_field(name="Catch Chance", value=f"{catch_chance * 100:.1f}%", inline=False)
        message = await interaction.followup.send(embed=embed)
        
        await asyncio.sleep(config["time"])
        
        wallet, bank = await self.manager.get_balances(interaction.user.id)
        total_wallet = wallet
        total_bank = bank
        
        caught = random.random() < catch_chance
        
        if caught:
            wallet_penalty = int(total_wallet * config["wallet_penalty"])
            bank_penalty = int(total_bank * config["bank_penalty"])
            
            await self.manager.deduct_wallet(interaction.user.id, wallet_penalty)
            new_bank = max(0, total_bank - bank_penalty)
            async with self.manager.lock:
                user = self.manager._ensure_user(interaction.user.id)
                user["bank"] = new_bank
            
            seized_items = {}
            if config["seize_items"]:
                seized_items = await self.manager.seize_all_items(interaction.user.id)
            
            description = "You were caught! The robbery failed."
            description += f"\nWallet penalty: {currency(wallet_penalty)}"
            description += f"\nBank penalty: {currency(bank_penalty)}"
            if seized_items:
                item_names = [ITEM_DATA[key]["name"] for key in seized_items.keys()]
                description += f"\nSeized items: {', '.join(item_names)}"
            
            embed = embedbuildthing("Robbery Failed", description, color=discord.Color.red())
        else:
            payout = random.randint(config["min_payout"], config["max_payout"])
            await self.manager.add_wallet(interaction.user.id, payout)
            embed = embedbuildthing("Robbery Successful", f"You successfully robbed {config['name']} and got {currency(payout)}!", color=discord.Color.green())
            
            # Check smooth criminal achievement
            achievements_cog = self.bot.get_cog("Achievements")
            if achievements_cog:
                if await achievements_cog.achievements_manager.unlock_achievement(interaction.user.id, "smooth_criminal"):
                    await achievements_cog._award_achievement(interaction.user.id, "smooth_criminal")
        
        await message.edit(embed=embed)
        await self.manager.save()
        
        # Check balance achievements after any money change
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            await achievements_cog.check_balance_achievements(interaction.user.id)
    
    @app_commands.guild_only()
    @app_commands.command(name="mug", description="Mug another user")
    @app_commands.describe(user="User to mug", amount="Amount to steal from wallet")
    async def mug(self, interaction: discord.Interaction, user: discord.Member, amount: int) -> None:
        if user.id == interaction.user.id:
            embed = embedbuildthing("Invalid Target", "You cannot mug yourself.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        
        if amount <= 0:
            embed = embedbuildthing("Invalid Amount", "Enter a positive amount to mug.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        
        await self.manager.ensure_user(user.id)
        wallet, _ = await self.manager.get_balances(user.id)
        
        if wallet < amount:
            embed = embedbuildthing("Insufficient Funds", f"{user.mention} only has {currency(wallet)} in their wallet.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.manager.save()
            return
        
        inventory = await self.manager.get_inventory(interaction.user.id)
        has_mask = inventory.get("mask", 0) > 0
        has_lpb = inventory.get("license_plate_blocker", 0) > 0
        
        catch_chance = 0.50
        catch_chance += (amount // 20) * 0.03
        
        if has_mask:
            catch_chance /= 2
        if has_lpb:
            catch_chance /= 2
        
        catch_chance = max(0.0, min(1.0, catch_chance))
        
        caught = random.random() < catch_chance
        
        if caught:
            embed = embedbuildthing("Mugging Failed", f"You were caught trying to mug {user.mention}!", color=discord.Color.red())
        else:
            if await self.manager.deduct_wallet(user.id, amount):
                await self.manager.add_wallet(interaction.user.id, amount)
                embed = embedbuildthing("Mugging Successful", f"You successfully mugged {user.mention} and stole {currency(amount)}!", color=discord.Color.green())
                
                # Check balance achievements
                achievements_cog = self.bot.get_cog("Achievements")
                if achievements_cog:
                    await achievements_cog.check_balance_achievements(interaction.user.id)
            else:
                embed = embedbuildthing("Mugging Failed", f"Failed to steal from {user.mention}.", color=discord.Color.red())
        
        await interaction.response.send_message(embed=embed)
        await self.manager.save()

