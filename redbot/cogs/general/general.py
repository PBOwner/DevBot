from enum import Enum
from random import randint, choice
from typing import Final, Optional
import urllib.parse
import aiohttp
import discord
from discord.ui import Button
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.menus import menu
from redbot.core.utils.chat_formatting import (
    bold,
    escape,
    humanize_number,
    humanize_timedelta,
    italics,
    pagify,
)

from .views import RPSView, ServerInfoView

_ = T_ = Translator("General", __file__)


# Thanks Jojo :D
class OddInt(commands.Converter):
    async def convert(self, ctx: commands.Context, arg: str) -> int:
        ret = int(arg)  # Don't have to catch here since I don't need logic for it
        if not ret % 2:
            raise commands.BadArgument("Input must be an odd number.")
        return ret


class RPS(Enum):
    rock = "🪨"
    paper = "📄"
    scissors = "\N{BLACK SCISSORS}\N{VARIATION SELECTOR-16}"


class RPSParser:
    def __init__(self, argument):
        if argument.lower() == "rock":
            self.choice = RPS.rock
        elif argument.lower() == "paper":
            self.choice = RPS.paper
        elif argument.lower() == "scissors":
            self.choice = RPS.scissors
        else:
            self.choice = None


MAX_ROLL: Final[int] = 2**64 - 1


@cog_i18n(_)
class General(commands.Cog):
    """General commands."""

    global _
    _ = lambda s: s
    ball = [
        _("As I see it, yes"),
        _("It is certain"),
        _("It is decidedly so"),
        _("Most likely"),
        _("Outlook good"),
        _("Signs point to yes"),
        _("Without a doubt"),
        _("Yes"),
        _("Yes – definitely"),
        _("You may rely on it"),
        _("Reply hazy, try again"),
        _("Ask again later"),
        _("Better not tell you now"),
        _("Cannot predict now"),
        _("Concentrate and ask again"),
        _("Don't count on it"),
        _("My reply is no"),
        _("My sources say no"),
        _("Outlook not so good"),
        _("Very doubtful"),
    ]
    _ = T_

    def __init__(self, bot: Red) -> None:
        super().__init__()
        self.bot = bot
        self.stopwatches = {}

    async def red_delete_data_for_user(self, **kwargs):
        """Nothing to delete"""
        return

    @commands.command(usage="<first> <second> [others...]")
    async def choose(self, ctx, amount: Optional[OddInt], *choices):
        """Choose between multiple options.

        There must be at least 2 options to pick from.
        Options are separated by spaces.

        To denote options which include whitespace, you should enclose the options in double quotes.

        You can specify an amount to make the bot choose the best choice.
        Minimum amount is 1 and Maximum amount is 25.
        """
        amount = amount or 1
        if amount > 25:
            amount = 25
        choices = [escape(c, mass_mentions=True) for c in choices if c]
        if len(choices) < 2:
            return await ctx.send(_("Not enough options to pick from."))
        if amount == 1:  # Small if statement blocks are good
            return await ctx.send(f"Best of all choices: `{choice(choices)}`")
        picks = {k: 0 for k in choices}
        for i in range(amount):
            picks[choice(choices)] += 1
        pick = sorted(picks.items(), key=lambda x: x[1])[1]
        await ctx.send(f"Best of all choices: `{pick[0]}` (Chosen `{pick[1]}` times)")

    @commands.command()
    async def roll(self, ctx, number: int = 100):
        """Roll a random number.

        The result will be between 1 and `<number>`.

        `<number>` defaults to 100.
        """
        author = ctx.author
        if 1 < number <= MAX_ROLL:
            n = randint(1, number)
            await ctx.send(
                "{author.mention} :game_die: {n} :game_die:".format(
                    author=author, n=humanize_number(n)
                )
            )
        elif number <= 1:
            await ctx.send(_("{author.mention} Maybe higher than 1? ;P").format(author=author))
        else:
            await ctx.send(
                _("{author.mention} Max allowed number is {maxamount}.").format(
                    author=author, maxamount=humanize_number(MAX_ROLL)
                )
            )

    @commands.command()
    async def flip(self, ctx, user: discord.Member = None):
        """Flip a coin... or a user.

        Defaults to a coin.
        """
        if user is not None:
            msg = ""
            if user.id == ctx.bot.user.id:
                user = ctx.author
                msg = _("Nice try. You think this is funny?\n How about *this* instead:\n\n")
            char = "abcdefghijklmnopqrstuvwxyz"
            tran = "ɐqɔpǝɟƃɥᴉɾʞlɯuodbɹsʇnʌʍxʎz"
            table = str.maketrans(char, tran)
            name = user.display_name.translate(table)
            char = char.upper()
            tran = "∀qƆpƎℲפHIſʞ˥WNOԀQᴚS┴∩ΛMX⅄Z"
            table = str.maketrans(char, tran)
            name = name.translate(table)
            await ctx.send(msg + "(╯°□°）╯︵ " + name[::-1])
        else:
            await ctx.send(_("*flips a coin and... ") + choice([_("HEADS!*"), _("TAILS!*")]))

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    async def rps(self, ctx: commands.Context, *, member: discord.Member = None):
        """Play a Rock Paper Scissors game. You can mention a member to play against them."""
        if member == ctx.author:
            await ctx.send(_("You can't play against yourself."), ephemeral=True)
            return
        member = member or ctx.me
        if member.bot and member != ctx.me:
            await ctx.send(_("You can't play against a bot."), ephemeral=True)
            return
        author = ctx.author
        with_bot = True if member == ctx.me else False
        author_name = _("You") if with_bot else author.display_name
        member_name = _("Me") if with_bot else member.display_name

        content = None if with_bot else f"{author.mention} vs {member.mention}"
        embed = discord.Embed(title=_("Rock, Paper, Scissors"), color=await ctx.embed_color())
        embed.set_author(name=f"{author_name} vs {member_name}")
        embed.description = (
            f"\N{LARGE BLUE SQUARE} {author_name} \N{WHITE QUESTION MARK ORNAMENT} | "
            f"\N{WHITE QUESTION MARK ORNAMENT} {member_name} \N{LARGE RED SQUARE}"
        )
        embed.set_footer(text=_("Please choose between rock, paper, and scissors."))

        view = RPSView(member)
        view.member_choice = choice(("rock", "paper", "scissors")) if with_bot else None
        view.member_has_pressed = True if with_bot else False
        await view.start(ctx, content=content, embed=embed)
        timed_out = await view.wait()
        if timed_out:
            # Timeout message will be handled by RPSView, so just stop here.
            return

        cond = {
            (RPS.rock, RPS.paper): False,
            (RPS.rock, RPS.scissors): True,
            (RPS.paper, RPS.rock): True,
            (RPS.paper, RPS.scissors): False,
            (RPS.scissors, RPS.rock): False,
            (RPS.scissors, RPS.paper): True,
        }
        author_choice = RPSParser(view.author_choice).choice
        member_choice = RPSParser(view.member_choice).choice
        if author_choice == member_choice:
            outcome = None  # Tie
        else:
            outcome = cond[(author_choice, member_choice)]

        if outcome is True:
            embed.description = (
                "\N{LARGE BLUE SQUARE} {a} {ac} | {mc} {m} \N{LARGE RED SQUARE}"
            ).format(
                a=author_name,
                ac=author_choice.value,
                mc=member_choice.value,
                m=member_name,
            )
            embed.color = discord.Color.green()
            embed.set_footer(text=f"{author_name} won!", icon_url=author.display_avatar.url)
        elif outcome is False:
            embed.description = (
                "\N{LARGE BLUE SQUARE} {a} {ac} | {mc} {m} \N{LARGE RED SQUARE}"
            ).format(
                a=author_name,
                ac=author_choice.value,
                mc=member_choice.value,
                m=member_name,
            )
            embed.color = discord.Color.red()
            member_name = _("I") if with_bot else member.display_name
            embed.set_footer(text=f"{member_name} won!", icon_url=member.display_avatar.url)
        else:
            embed.description = (
                "\N{LARGE BLUE SQUARE} {a} {ac} | {mc} {m} \N{LARGE RED SQUARE}"
            ).format(
                a=author_name,
                ac=author_choice.value,
                mc=member_choice.value,
                m=member_name,
            )
            embed.set_footer(text="It's a tie!")
        await view.message.edit(embed=embed)

    @commands.command(name="8", aliases=["8ball"])
    async def _8ball(self, ctx, *, question: str):
        """Ask 8 ball a question.

        Question must end with a question mark.
        """
        if question.endswith("?") and question != "?":
            await ctx.send("`" + T_(choice(self.ball)) + "`")
        else:
            await ctx.send(_("That doesn't look like a question."))

    @commands.command()
    async def lmgtfy(self, ctx, *, search_terms: str):
        """Create a lmgtfy link."""
        search_terms = escape(urllib.parse.quote_plus(search_terms), mass_mentions=True)
        await ctx.send("https://lmgtfy.app/?q={}".format(search_terms))

    @commands.command()
    @commands.guild_only()
    async def hug(self, ctx, user: discord.Member, intensity: int = 1):
        """Because everyone likes hugs!

        Up to 10 intensity levels.
        """
        name = italics(user.display_name)
        if intensity <= 0:
            msg = "(っ˘̩╭╮˘̩)っ" + name
        elif intensity <= 3:
            msg = "(っ´▽｀)っ" + name
        elif intensity <= 6:
            msg = "╰(*´︶`*)╯" + name
        elif intensity <= 9:
            msg = "(つ≧▽≦)つ" + name
        elif intensity >= 10:
            msg = "(づ￣ ³￣)づ{} ⊂(´・ω・｀⊂)".format(name)
        else:
            # For the purposes of "msg might not be defined" linter errors
            raise RuntimeError
        await ctx.send(msg)

    @staticmethod
    async def serverinfo_embed(ctx: commands.Context, guild: discord.Guild) -> discord.Embed:
        description = (guild.description or "") + "\n"
        description += "Created on **<t:{0}>**. That's **__<t:{0}:R>__**!".format(
            int(guild.created_at.timestamp())
        )
        embed = discord.Embed(description=description, color=await ctx.embed_color())

        icon_url = "https://cdn.discordapp.com/emojis/741839228526395432.png?quality=lossless"
        if "VERIFIED" in guild.features:
            icon_url = "https://cdn.discordapp.com/emojis/751162278719520858.png?quality=lossless"
        elif "PARTNERED" in guild.features:
            icon_url = "https://cdn.discordapp.com/emojis/848556249691193424.png?quality=lossless"
        elif guild.premium_tier == 1:
            icon_url = "https://cdn.discordapp.com/emojis/741839228434120761.png?quality=lossless"
        elif guild.premium_tier == 2:
            icon_url = "https://cdn.discordapp.com/emojis/741839228849094736.png?quality=lossless"
        elif guild.premium_tier == 3:
            icon_url = "https://cdn.discordapp.com/emojis/741839228970991737.png?quality=lossless"
        embed.set_author(name=guild.name, icon_url=icon_url)

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.with_size(1024).url)
        if guild.splash:
            embed.set_image(url=guild.splash.with_size(4096).url)
        if guild.banner:
            embed.set_image(url=guild.banner.with_size(4096).url)  # Prioritize

        joined_on = (
            "I joined this server on {bot_join}. That's over {since_join} days ago!".format(
                bot_join=guild.me.joined_at.strftime("%d %b %Y %H:%M:%S"),
                since_join=humanize_number((ctx.message.created_at - guild.me.joined_at).days),
            )
        )
        embed.set_footer(text=joined_on)
        return embed

    @commands.command(aliases=["si"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True, use_external_emojis=True)
    async def serverinfo(self, ctx, *, guild: discord.Guild = commands.CurrentGuild):
        """Show server information."""
        stats_embed = await self.serverinfo_embed(ctx, guild)

        online = humanize_number(
            len([m.status for m in guild.members if m.status != discord.Status.offline])
        )
        total_users = humanize_number(guild.member_count)
        online_str = f"<:online:749221433552404581> Online Users: **{online}/{total_users}**\n"

        member_stats = {
            "<:humans:724948692242792470> Humans: ": lambda m: not m.bot,
            "<:bot:848557763172892722> Bots: ": lambda m: m.bot,
        }
        online_stats = {
            "<:online:749221433552404581>": lambda m: m.status is discord.Status.online,
            "<:idle:749221433095356417>": lambda m: m.status is discord.Status.idle,
            "<:do_not_disturb:749221432772395140>": lambda m: (
                m.status is discord.Status.do_not_disturb
            ),
            "<:streaming:749221434039205909>": lambda m: any(
                a.type is discord.ActivityType.streaming for a in m.activities
            ),
            "<:mobile:749067110931759185>": lambda m: m.is_on_mobile(),
            "<:offline:749221433049088082>": lambda m: (m.status is discord.Status.offline),
        }

        member_str = ""
        for emoji, value in member_stats.items():
            num = len([m for m in guild.members if value(m)])
            member_str += f"{emoji} {bold(humanize_number(num))}\n"

        status_str = ""
        count = 1
        for emoji, value in online_stats.items():
            num = len([m for m in guild.members if value(m)])
            status_str += f"{emoji} {bold(humanize_number(num))}" + (
                "\n" if count % (2 if guild.large else 3) == 0 else " "
            )
            count += 1

        stats_embed.add_field(name="Members", value=online_str + member_str + status_str)

        text_channels = len(guild.text_channels)
        news_channels = len([c for c in guild.text_channels if c.is_news()])
        nsfw_channels = len([c for c in guild.text_channels if c.is_nsfw()])
        text_threads = len([t for t in guild.threads if isinstance(t.parent, discord.TextChannel)])
        forums = len([c for c in guild.forums])
        nsfw_forums = len([c for c in guild.forums if c.is_nsfw()])
        forum_threads = len(
            [t for t in guild.threads if isinstance(t.parent, discord.ForumChannel)]
        )
        voice_channels = len(guild.voice_channels)
        stage_channels = len(guild.stage_channels)
        stats_embed_channels_field_values = [
            f"<:text_channel:725390525863034971> Text: {bold(str(text_channels))}",
            f"<:Branch1:1089963964567396372> News: {bold(str(news_channels))}",
            f"<:Branch2:1089963940659876001> Threads: {bold(str(text_threads))}",  # 2
            f"<:Forum:1089965636815433748> Forums: {bold(str(forums))}",
            f"<:Branch2:1089963940659876001> Threads: {bold(str(forum_threads))}",  # 4 (5 if nsfw_channels)
            f"<:voice_channel:725390524986425377> Voice: {bold(str(voice_channels))}",
            f"<:stage_channel:828073435908800582> Stage: {bold(str(stage_channels))}",
        ]
        if nsfw_channels:
            stats_embed_channels_field_values.insert(
                2, f"<:Branch1:1089963964567396372> NSFW: {bold(str(nsfw_channels))}"
            )
        if nsfw_forums:
            stats_embed_channels_field_values.insert(
                5 if nsfw_channels else 4,
                f"<:Branch1:1089963964567396372> NSFW: {bold(str(nsfw_forums))}",
            )
        stats_embed.add_field(name="Channels", value="\n".join(stats_embed_channels_field_values))

        verif_level = guild.verification_level
        verification = f"{verif_level.value} - {verif_level.name.title()}"
        shard_info = ""
        if self.bot.shard_count > 1:
            shard_info = "<:Red:917079459641831474> Shard ID: **{id}/{count}**".format(
                id=guild.shard_id + 1, count=self.bot.shard_count
            )
        stats_embed.add_field(
            name="Utility",
            value=(
                f"<:owner:725387683811033140> Owner: {bold(str(guild.owner))} | {guild.owner.mention}\n"
                f"<:Verification:947538751972835368> Verification Level: {bold(verification)}\n"
                f"<:ID:947512240372867096> Server ID: {bold(str(guild.id))}\n{shard_info}"
            ),
            inline=False,
        )

        afk_channel = guild.afk_channel.mention if guild.afk_channel else "-"
        stats_embed.add_field(
            name="Miscellaneous",
            value=(
                (
                    "<:VoiceChannel:948050342279544872> AFK Channel: {afk_channel}\n"
                    "<:Slowmode:947536577486262293> AFK Timeout: {afk_timeout}\n"
                    "<:Emoji:947538720695922738> Custom Emojis: {emoji_count}\n"
                    "<:Role:947538116808429628> Roles: {role_count}"
                ).format(
                    afk_channel=bold(afk_channel),
                    afk_timeout=bold(humanize_timedelta(seconds=guild.afk_timeout)),
                    emoji_count=bold(humanize_number(len(guild.emojis))),
                    role_count=bold(humanize_number(len(guild.roles))),
                )
            ),
        )

        features_embed = None
        guild_features_str = "\n".join(
            [
                f"<a:Check:945850988751904868> {feature.replace('_', ' ').title()}"
                for feature in sorted(guild.features)
            ]
        )
        if guild_features_str:
            features_embed = await self.serverinfo_embed(ctx, guild)
        features_pages = pagify(guild_features_str, shorten_by=0, page_length=450)
        for i, page in enumerate(features_pages):
            name = "Server Features" if not i else "\N{ZERO WIDTH SPACE}"
            features_embed.add_field(name=name, value=page)

        def _size(num: int):
            for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
                if abs(num) < 1024.0:
                    return "{0:.1f}{1}".format(num, unit)
                num /= 1024.0
            return "{0:.1f}{1}".format(num, "YB")

        def _bitsize(num: int):
            for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
                if abs(num) < 1000.0:
                    return "{0:.1f}{1}".format(num, unit)
                num /= 1000.0
            return "{0:.1f}{1}".format(num, "YB")

        if guild.premium_tier > 0:
            nitro_boost = (
                "<:booster:710871139227795487> Tier {boostlevel} with {boosts} boosts\n"
                "<:FileSize:947512316482691125> Max File Size: {file_limit}\n"
                "<:Emoji:947538720695922738> Emoji Limit: {emojis_limit}\n"
                "<:Undeafened:947539805741404250> Max Bitrate: {bitrate}"
            ).format(
                boostlevel=bold(str(guild.premium_tier)),
                boosts=bold(humanize_number(guild.premium_subscription_count)),
                file_limit=bold(_size(guild.filesize_limit)),
                emojis_limit=bold(str(guild.emoji_limit)),
                bitrate=bold(_bitsize(guild.bitrate_limit)),
            )
            if not features_embed:
                features_embed = await self.serverinfo_embed(ctx, guild)
            features_embed.add_field(name="Server Boost Info", value=nitro_boost, inline=False)

        view = ServerInfoView(stats_embed=stats_embed, features_embed=features_embed)
        if guild.icon:
            view.add_item(
                Button(
                    style=discord.ButtonStyle.link,
                    label="Server Icon",
                    url=guild.icon.with_format("png").url,
                    row=1 if features_embed else 0,
                )
            )
        if guild.banner:
            view.add_item(
                Button(
                    style=discord.ButtonStyle.link,
                    label="Server Banner",
                    url=guild.banner.with_format("png").url,
                    row=1 if features_embed else 0,
                )
            )
        if guild.splash:
            view.add_item(
                Button(
                    style=discord.ButtonStyle.link,
                    label="Server Splash",
                    url=guild.splash.with_format("png").url,
                    row=1 if features_embed else 0,
                )
            )
        await view.start(ctx)

    @commands.command()
    async def urban(self, ctx: commands.Context, *, word: str):
        """Search the Urban Dictionary.

        This uses the unofficial Urban Dictionary API.
        """

        try:
            url = "https://api.urbandictionary.com/v0/define"
            headers = {"content-type": "application/json"}
            params = {"term": word.lower()}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    data = await response.json()
        except aiohttp.ClientError:
            await ctx.send(
                _("No Urban Dictionary entries were found, or there was an error in the process.")
            )
            return

        if data.get("error") != 404:
            if not data.get("list"):
                return await ctx.send(_("No Urban Dictionary entries were found."))
            pages = []
            if await ctx.embed_requested():
                for ud in data["list"]:
                    embed = discord.Embed(url=ud["permalink"], color=discord.Color.random())
                    embed.set_author(name=ud["author"])
                    title = ud["word"].title()
                    if len(title) > 256:
                        title = "{}...".format(title[:253])
                    embed.title = title
                    description = ud["definition"] + "\n\n"
                    if len(description) > 2048:
                        description = "{}...\n\n".format(description[:2045])
                    if len(ud["example"]) > 1024:
                        description += "**Example**\n{}".format(ud["example"])
                    else:
                        embed.add_field(name="Example", value=ud["example"])
                    embed.description = description
                    embed.set_footer(
                        text=_(
                            "👍 {thumbs_up} | 👎 {thumbs_down}  •  Powered by Urban Dictionary"
                        ).format(
                            thumbs_up=humanize_number(int(ud["thumbs_up"])),
                            thumbs_down=humanize_number(int(ud["thumbs_down"])),
                        )
                    )
                    pages.append(embed)
            else:
                for ud in data["list"]:
                    ud.setdefault("example", "N/A")
                    # lines = "-"*len(ud["permalink"])
                    message = _(
                        "<{permalink}>\n{word} by {author}\n\n{description}\n\n"
                        "\👍 {thumbs_up} | \👎 {thumbs_down} • Powered by Urban Dictionary"
                    ).format(word=ud.pop("word").capitalize(), description="{description}", **ud)
                    max_desc_len = 2000 - len(message)
                    description = _("{definition}\n\n**Example**\n{example}").format(**ud)
                    if len(description) > max_desc_len:
                        description = "{}...".format(description[: max_desc_len - 3])
                    message = message.format(description=description)
                    pages.append(message)
            if pages and len(pages) > 0:
                await menu(ctx, pages)
        else:
            await ctx.send(
                _("No Urban Dictionary entries were found, or there was an error in the process.")
            )
