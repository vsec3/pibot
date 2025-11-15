# Configuration and constants
from pathlib import Path
from typing import Dict, Any

# Admin whitelist - user IDs that can use admin commands without permissions
ADMIN_WHITELIST: list[int] = []  # Add user IDs here

# File paths
DATA_FILE = Path(__file__).with_name("moddata.json")
ECONOMY_FILE = Path(__file__).with_name("economy.json")
JOBS_FILE = Path(__file__).with_name("jobs.json")
GUILDS_FILE = Path(__file__).with_name("guilds.json")
ACHIEVEMENTS_FILE = Path(__file__).with_name("achievements.json")

# Item data
ITEM_DATA: Dict[str, Dict[str, Any]] = {
    "golden_potato": {"name": "Golden Potato", "min_value": 30, "max_value": 30, "sellable": True},
    "rainbow_trout": {"name": "Rainbow Trout", "min_value": 15, "max_value": 22, "sellable": True},
    "bass": {"name": "Bass", "min_value": 18, "max_value": 19, "sellable": True},
    "sunfish": {"name": "Sunfish", "min_value": 17, "max_value": 20, "sellable": True},
    "spearfish": {"name": "Spearfish", "min_value": 25, "max_value": 32, "sellable": True},
    "voltfish": {"name": "Voltfish", "min_value": 27, "max_value": 36, "sellable": True},
    "angel_o8": {"name": "Angel_o8", "min_value": 5000, "max_value": 10000, "sellable": True},
    "lockpick": {"name": "Lockpick", "price": 50, "sellable": False},
    "gun": {"name": "Gun", "price": 150, "sellable": False},
    "advanced_lockpick": {"name": "Advanced Lockpick", "price": 500, "sellable": False},
    "hacker_tool": {"name": "Hacker Tool", "price": 1200, "sellable": False},
    "mask": {"name": "Mask", "price": 60, "sellable": False},
    "license_plate_blocker": {"name": "License Plate Blocker", "price": 500, "sellable": False},
    "admin_itemitemitem": {"name": "Volts Prize", "price": 9999999, "sellable": False},
}

SHOP_ITEMS = ["lockpick", "gun", "advanced_lockpick", "hacker_tool", "mask", "license_plate_blocker"]

# Job data
JOB_DATA = {
    "factory_worker": {
        "name": "Factory Worker",
        "payout_per_minute": 50,
        "decline_chance": 0.05,
    },
    "office_worker": {
        "name": "Office Worker",
        "payout_per_minute": 100,
        "decline_chance": 0.35,
    },
    "scientist": {
        "name": "Scientist",
        "payout_per_minute": 250,
        "decline_chance": 0.60,
    },
    "doctor": {
        "name": "Doctor",
        "payout_per_minute": 500,
        "decline_chance": 0.90,
    },
}

# Guild creation cost
GUILD_CREATION_COST = 12500

# Achievements
ACHIEVEMENTS = {
    "money_lover": {
        "name": "Money Lover",
        "description": "Have 5K Total at some point",
        "reward": 50,
    },
    "money_fiend": {
        "name": "Money Fiend",
        "description": "Have 10K Total at some point",
        "reward": 100,
    },
    "smooth_criminal": {
        "name": "Smooth Criminal",
        "description": "Rob without being caught",
        "reward": 250,
    },
    "minimum_wage_slave": {
        "name": "Minimum Wage Slave",
        "description": "Work a job",
        "reward": 500,
    },
    "leaderboard": {
        "name": "Leaderboard",
        "description": "Reach top 5 on the leaderboard (be in a top 5 guild)",
        "reward": 5000,
    },
    "guildmaster": {
        "name": "Guildmaster",
        "description": "Create a guild",
        "reward": 2500,
    },
    "guildeer": {
        "name": "Guildeer",
        "description": "Join a guild",
        "reward": 100,
    },
    "money_launderer": {
        "name": "Money Launderer",
        "description": "Reach 100K total",
        "reward": 2000,
    },
    "gifted_by_god": {
        "name": "Gifted by God",
        "description": "Reach 1M total",
        "reward": 1000,
    },
    "savehacking": {
        "name": "Savehacking",
        "description": "Reach 10M Total",
        "reward": 10000,
    },
    "volt_prize_receiver": {
        "name": "Volt Prize Receiver",
        "description": "Have a \"Volt's Prize\" (admin_itemitemitem) in your inventory.",
        "reward": 100000,
    },
}
