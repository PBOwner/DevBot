import discord
from redbot.core.commands import Context
from redbot.core.utils.views import View
from typing import Optional


class RPSView(View):
    def __init__(self, member: discord.Member, *, timeout: Optional[float] = 60.0):
        super().__init__(timeout=timeout)
        self.author_choice = None
        self.author_has_pressed = False
        self.member = member
        self.member_choice = None
        self.member_has_pressed = False

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji="🪨")
    async def rock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user == self.author:
            self.author_choice = "rock"
            self.author_has_pressed = True
        elif interaction.user == self.member:
            self.member_choice = "rock"
            self.member_has_pressed = True
        await interaction.response.send_message("You have chosen `rock`", ephemeral=True)
        if self.author_has_pressed and self.member_has_pressed:
            await self.disable_items()
            self.stop()

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji="📄")
    async def paper_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user == self.author:
            self.author_choice = "paper"
            self.author_has_pressed = True
        elif interaction.user == self.member:
            self.member_choice = "paper"
            self.member_has_pressed = True
        await interaction.response.send_message("You have chosen `paper`", ephemeral=True)
        if self.author_has_pressed and self.member_has_pressed:
            await self.disable_items()
            self.stop()

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji="✂️")
    async def scissors_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user == self.author:
            self.author_choice = "scissors"
            self.author_has_pressed = True
        elif interaction.user == self.member:
            self.member_choice = "scissors"
            self.member_has_pressed = True
        await interaction.response.send_message("You have chosen `scissors`", ephemeral=True)
        if self.author_has_pressed and self.member_has_pressed:
            await self.disable_items()
            self.stop()

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user not in [self.author, self.member]:
            await interaction.response.send_message(
                "You are not authorized to interact with this menu.", ephemeral=True
            )
            return False
        if interaction.user == self.author and self.author_has_pressed:
            await interaction.response.send_message(
                "You have already made your choice.", ephemeral=True
            )
            return False
        elif interaction.user == self.member and self.member_has_pressed:
            await interaction.response.send_message(
                "You have already made your choice.", ephemeral=True
            )
            return False
        return True

    async def disable_items(self):
        if self.author_choice == self.member_choice:
            if self.author_choice == "rock":
                self.rock_button.style = discord.ButtonStyle.green
            elif self.author_choice == "paper":
                self.paper_button.style = discord.ButtonStyle.green
            elif self.author_choice == "scissors":
                self.scissors_button.style = discord.ButtonStyle.green
        else:
            # Time for some unefficiency
            if self.author_choice == "rock":
                self.rock_button.style = discord.ButtonStyle.blurple
            elif self.author_choice == "paper":
                self.paper_button.style = discord.ButtonStyle.blurple
            elif self.author_choice == "scissors":
                self.scissors_button.style = discord.ButtonStyle.blurple

            if self.member_choice == "rock":
                self.rock_button.style = discord.ButtonStyle.red
            elif self.member_choice == "paper":
                self.paper_button.style = discord.ButtonStyle.red
            elif self.member_choice == "scissors":
                self.scissors_button.style = discord.ButtonStyle.red

        for child in self.children:
            child.disabled = True
        await self.message.edit(view=self)

    async def on_timeout(self):
        # We are using super() here, since we want to call the original one.
        await super().disable_items()
        await self.message.edit(content="The game has timed out.", view=self)


class ServerInfoView(View):
    def __init__(self, *, stats_embed: discord.Embed, features_embed: discord.Embed = None):
        super().__init__()
        self.stats_embed = stats_embed
        self.features_embed = features_embed

    @discord.ui.button(style=discord.ButtonStyle.red, emoji="✖️")
    async def close_button(self, interaction: discord.Interaction, button: discord.Button):
        self.stop()
        if interaction.message.flags.ephemeral:
            await interaction.response.edit_message(view=None)
            return
        await interaction.message.delete()

    @discord.ui.button(label="Stats", disabled=True, style=discord.ButtonStyle.blurple)
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        self.features_button.disabled = False
        await interaction.response.edit_message(embed=self.stats_embed, view=self)

    @discord.ui.button(label="Features", style=discord.ButtonStyle.blurple)
    async def features_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        self.stats_button.disabled = False
        await interaction.response.edit_message(embed=self.features_embed, view=self)

    async def start(self, ctx: Context):
        self.author = ctx.author
        if not self.features_embed:
            # Remove stats_button and features_button if a guild has no features to show.
            self.remove_item(self.stats_button)
            self.remove_item(self.features_button)
        kwargs = {
            "embed": self.stats_embed,
            "reference": ctx.message.to_reference(fail_if_not_exists=False),
            "mention_author": False,
            "view": self,
        }
        self.message = await ctx.send(**kwargs)
