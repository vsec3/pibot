# Jobs Cog
import asyncio
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import JOB_DATA
from managers import JobsManager, EconomyManager
from utils import currency, embedbuildthing


class Jobs(commands.Cog):
    def __init__(self, bot: commands.Bot, jobs_manager: JobsManager, economy_manager: EconomyManager):
        self.bot = bot
        self.jobs_manager = jobs_manager
        self.economy_manager = economy_manager
        # Track tasks by (guild_id, user_id) tuple
        self.job_tasks: dict[tuple[int, int], asyncio.Task] = {}
    
    async def cog_load(self) -> None:
        await self.jobs_manager.load()
        # Start payout tasks for existing jobs
        # Access the guild_jobs through the lock
        async with self.jobs_manager.lock:
            for guild_id, guild_jobs in self.jobs_manager.guild_jobs.items():
                for user_id, job_key in guild_jobs.items():
                    if job_key:
                        self._start_job_payout(guild_id, user_id, job_key)
    
    def _start_job_payout(self, guild_id: int, user_id: int, job_key: str) -> None:
        """Start the payout task for a user's job"""
        task_key = (guild_id, user_id)
        if task_key in self.job_tasks:
            self.job_tasks[task_key].cancel()
        
        job_data = JOB_DATA[job_key]
        payout_per_minute = job_data["payout_per_minute"]
        
        async def payout_loop():
            while True:
                await asyncio.sleep(60)  # Wait 1 minute
                current_job = await self.jobs_manager.get_job(guild_id, user_id)
                if current_job != job_key:
                    break
                await self.economy_manager.add_wallet(guild_id, user_id, payout_per_minute)
                await self.economy_manager.save()
                
                # Check balance achievements periodically
                achievements_cog = self.bot.get_cog("Achievements")
                if achievements_cog:
                    await achievements_cog.check_balance_achievements(guild_id, user_id)
        
        self.job_tasks[task_key] = asyncio.create_task(payout_loop())
    
    @app_commands.guild_only()
    @app_commands.command(name="applyjob", description="Apply for a job")
    @app_commands.describe(job="Job to apply for")
    @app_commands.choices(job=[
        app_commands.Choice(name=job_data["name"], value=key)
        for key, job_data in JOB_DATA.items()
    ])
    async def applyjob(self, interaction: discord.Interaction, job: app_commands.Choice[str]) -> None:
        if not interaction.guild_id:
            return
        job_key = job.value
        job_data = JOB_DATA[job_key]
        
        can_apply, reason = await self.jobs_manager.can_apply(interaction.guild_id, interaction.user.id)
        if not can_apply:
            embed = embedbuildthing("Cannot Apply", reason, color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.jobs_manager.save()
            return
        
        # Check if declined
        declined = random.random() < job_data["decline_chance"]
        
        if declined:
            await self.jobs_manager.set_decline_cooldown(interaction.guild_id, interaction.user.id)
            embed = embedbuildthing("Application Declined", f"Your application for {job_data['name']} was declined. You cannot reapply for 10 minutes.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.jobs_manager.save()
            return
        
        # Accepted
        await self.jobs_manager.set_job(interaction.guild_id, interaction.user.id, job_key)
        await self.jobs_manager.clear_cooldown(interaction.guild_id, interaction.user.id)
        self._start_job_payout(interaction.guild_id, interaction.user.id, job_key)
        
        # Check minimum wage slave achievement
        achievements_cog = self.bot.get_cog("Achievements")
        if achievements_cog:
            if await achievements_cog.achievements_manager.unlock_achievement(interaction.guild_id, interaction.user.id, "minimum_wage_slave"):
                await achievements_cog._award_achievement(interaction.guild_id, interaction.user.id, "minimum_wage_slave")
        
        embed = embedbuildthing("Application Accepted", f"Congratulations! You got the job as {job_data['name']}. You will earn {currency(job_data['payout_per_minute'])} per minute.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
        await self.jobs_manager.save()
    
    @app_commands.guild_only()
    @app_commands.command(name="quitjob", description="Quit your current job")
    async def quitjob(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            return
        current_job = await self.jobs_manager.get_job(interaction.guild_id, interaction.user.id)
        if not current_job:
            embed = embedbuildthing("No Job", "You don't have a job to quit.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            await self.jobs_manager.save()
            return
        
        job_data = JOB_DATA[current_job]
        await self.jobs_manager.set_job(interaction.guild_id, interaction.user.id, None)
        
        task_key = (interaction.guild_id, interaction.user.id)
        if task_key in self.job_tasks:
            self.job_tasks[task_key].cancel()
            del self.job_tasks[task_key]
        
        embed = embedbuildthing("Job Quit", f"You quit your job as {job_data['name']}.", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed)
        await self.jobs_manager.save()

