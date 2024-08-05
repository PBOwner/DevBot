import calendar
import logging
import random
from collections import defaultdict, deque, namedtuple
from enum import Enum
from math import ceil
from typing import cast, Iterable, Literal

import discord

from redbot.core import Config, bank, commands, errors
from redbot.core.commands.converter import TimedeltaConverter, positive_int
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import bold, box, humanize_number
from redbot.core.utils.menus import menu

T_ = Translator("Economy", __file__)

BLANK = "<:Blank:1014880410980855828>"
VARIATION_SELECTOR = "\N{VARIATION SELECTOR-16}"
ARROW = "\N{BLACK RIGHT-POINTING TRIANGLE}" + VARIATION_SELECTOR
MOCK_MEMBER = namedtuple("Member", "id guild")


class SMReel(Enum):
    eggplant = ""
    peach = ""
    cherries = ""
    heart = ""
    flc = ""
    coin = ""  # noqa: E999
    bag = ""


_ = lambda s: s
PAYOUTS = {
    (SMReel.bag, SMReel.bag, SMReel.bag): {
        "payout": lambda x: x * 50,
        "phrase": _("JACKPOT! Your bid has been multiplied * 50!"),
    },
    (SMReel.coin, SMReel.coin, SMReel.coin): {
        "payout": lambda x: x * 30,
        "phrase": _("Three coins! Your bid has been multiplied * 30!"),
    },
    (SMReel.bag, SMReel.bag): {
        "payout": lambda x: x * 25,
        "phrase": _("Two bags! Your bid has been multiplied * 25!"),
    },
    (SMReel.coin, SMReel.coin): {
        "payout": lambda x: x * 15,
        "phrase": _("Two coins! Your bid has been multiplied * 15!"),
    },
    (SMReel.flc, SMReel.flc, SMReel.flc): {
        "payout": lambda x: x * 12,
        "phrase": _("You're so lucky! Your bid has been multiplied * 12!"),
    },
    (SMReel.flc, SMReel.flc): {
        "payout": lambda x: x * 8,
        "phrase": _("Almost! Your bid has been multiplied * 8!"),
    },
    "3 symbols": {
        "payout": lambda x: x * 10,
        "phrase": _("Three symbols! Your bid has been multiplied * 10!"),
    },
    "2 symbols": {
        "payout": lambda x: x * 2,
        "phrase": _("Two consecutive symbols! Your bid has been multiplied * 2!"),
    },
}

_ = T_


def guild_only_check():
    async def pred(ctx: commands.Context):
        if await bank.is_global():
            return True
        elif ctx.guild is not None and not await bank.is_global():
            return True
        else:
            return False

    return commands.check(pred)


class SetParser:
    def __init__(self, argument):
        allowed = ("+", "-")
        try:
            self.sum = int(argument)
        except ValueError:
            raise commands.BadArgument(
                _(
                    "Invalid value, the argument must be an integer,"
                    " optionally preceded with a `+` or `-` sign."
                )
            )
        if argument and argument[0] in allowed:
            if self.sum < 0:
                self.operation = "withdraw"
            elif self.sum > 0:
                self.operation = "deposit"
            else:
                raise commands.BadArgument(
                    _(
                        "Invalid value, the amount of currency to increase or decrease"
                        " must be an integer different from zero."
                    )
                )
            self.sum = abs(self.sum)
        else:
            self.operation = "set"


@cog_i18n(_)
class Economy(commands.Cog):
    """Get rich and have fun with imaginary currency!"""

    default_guild = {
        "PAYDAY_TIME": 300,
        "PAYDAY_CREDITS": 120,
        "SLOT_MIN": 5,
        "SLOT_MAX": 100,
        "SLOT_TIME": 5,
        "REGISTER_CREDITS": 0,
        "CREDITS_PER_MESSAGE": {"default_min": 1, "default_max": 20, "channels": {}},
        "WHITELISTED_CHANNELS": [],
        "BLACKLISTED_CHANNELS": [],
    }
    default_global = default_guild
    default_member = {"next_daily": 0, "next_weekly": 0, "next_monthly": 0, "last_slot": 0}
    default_role = {"PAYDAY_CREDITS": 0}
    default_user = default_member

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot  # Ensure bot is set
        global _bot_ref
        _bot_ref = self.bot  # Set the global reference
        self.config = Config.get_conf(self, 1256844281)
        self.config.register_guild(**self.default_guild)
        self.config.register_global(**self.default_global)
        self.config.register_member(**self.default_member)
        self.config.register_user(**self.default_user)
        self.config.register_role(**self.default_role)
        self.slot_register = defaultdict(dict)

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        if requester != "discord_deleted_user":
            return

        await self.config.user_from_id(user_id).clear()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        guild = message.guild
        channel = message.channel

        if not guild:
            return

        if await self.config.guild(guild).BLACKLISTED_CHANNELS():
            if channel.id in await self.config.guild(guild).BLACKLISTED_CHANNELS():
                return

        if await self.config.guild(guild).WHITELISTED_CHANNELS():
            if channel.id not in await self.config.guild(guild).WHITELISTED_CHANNELS():
                return

        credits_per_message = await self.config.guild(guild).CREDITS_PER_MESSAGE()
        default_min = credits_per_message["default_min"]
        default_max = credits_per_message["default_max"]
        channel_credits = credits_per_message["channels"].get(str(channel.id), None)

        if channel_credits:
            min_credits = channel_credits["min"]
            max_credits = channel_credits["max"]
        else:
            min_credits = default_min
            max_credits = default_max

        credits = random.randint(min_credits, max_credits)
        await bank.deposit_credits(message.author, credits)

    @guild_only_check()
    @commands.command()
    async def balance(self, ctx: commands.Context, user: discord.Member = commands.Author):
        """Show the user's account balance.

        Example:
        - `[p]balance`
        - `[p]balance @Kuro`

        **Arguments**

        - `<user>` The user to check the balance of. If omitted, defaults to your own balance.
        """

        bal = await bank.get_balance(user)
        currency = await bank.get_currency_name(ctx.guild)
        max_bal = await bank.get_max_balance(ctx.guild)
        if bal > max_bal:
            bal = max_bal
            await bank.set_balance(user, bal)
        msg = "{name} have {num} {currency}".format(
            name=user.display_name, num=humanize_number(bal), currency=currency
        )
        embed = discord.Embed(
            description=msg, color=await ctx.embed_color(), timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{user.display_name}'s Balance", icon_url=user.display_avatar)
        await ctx.send(embed=embed)

    @guild_only_check()
    @commands.command(aliases=["pay", "transfer"])
    async def share(self, ctx: commands.Context, amount: int, to: discord.Member):
        """Share coins to other users.

        This will come out of your balance, so make sure you have enough.

        Example:
        - `[p]share 1000 @Kuro`

        **Arguments:**
        - `<amount>` The amount of coins to give.
        - `<to>` The user to give coins to.
        """
        currency = await bank.get_currency_name(ctx.guild)

        author_bal = await bank.get_balance(ctx.author) - amount
        other_bal = await bank.get_balance(to) + amount

        try:
            await bank.transfer_credits(ctx.author, to, amount)
        except (ValueError, errors.BalanceTooHigh) as e:
            return await ctx.send(str(e))

        await ctx.send(
            (
                "{user} gave {other_user} {num} {currency}. "
                "Now {user} have {bal} {currency} and {other_user} have {other_bal} {currency}."
            ).format(
                user=ctx.author.display_name,
                num=humanize_number(amount),
                currency=currency,
                other_user=to.display_name,
                bal=humanize_number(author_bal),
                other_bal=humanize_number(other_bal),
            )
        )

    @commands.is_owner()
    @guild_only_check()
    @commands.command(aliases=["setbal"])
    async def setbalance(self, ctx: commands.Context, to: discord.Member, creds: SetParser):
        """Set the balance of a user's coins.

        Putting + or - signs before the amount will add/remove user's coins instead.

        Examples:
        - `[p]setbalance @Kuro 69` - Sets balance to 69
        - `[p]setbalance @Kuro +4` - Increases balance by 4
        - `[p]setbalance @Kuro -2` - Decreases balance by 2

        **Arguments:**
        - `<to>` The user to set the currency of.
        - `<creds>` The amount of currency to set their balance to.
        """
        currency = await bank.get_currency_name(ctx.guild)

        try:
            if creds.operation == "deposit":
                await bank.deposit_credits(to, creds.sum)
                msg = "Added {num} {currency} to {user}'s account.".format(
                    num=humanize_number(creds.sum),
                    currency=currency,
                    user=to.display_name,
                )
            elif creds.operation == "withdraw":
                await bank.withdraw_credits(to, creds.sum)
                msg = "Removed {num} {currency} from {user}'s account.".format(
                    num=humanize_number(creds.sum),
                    currency=currency,
                    user=to.display_name,
                )
            else:
                await bank.set_balance(to, creds.sum)
                msg = "Set {user}'s coins to {num} {currency}.".format(
                    num=humanize_number(creds.sum),
                    currency=currency,
                    user=to.display_name,
                )
        except (ValueError, errors.BalanceTooHigh) as e:
            await ctx.send(str(e))
        else:
            await ctx.send(msg)

    @bank.is_owner_if_bank_global()
    @commands.command()
    async def bankreset(self, ctx: commands.Context, confirmation: bool = False):
        """Delete all bank accounts.

        Examples:
        - `[p]bankreset` - Did not confirm. Shows the help message.
        - `[p]bankreset yes`

        **Arguments:**
        - `<confirmation>` This will default to false unless specified.
        """
        if confirmation is False:
            await ctx.send(
                "This will delete all bank accounts.\nIf you're sure, type `{prefix}bankreset yes`".format(
                    prefix=ctx.clean_prefix,
                )
            )
        else:
            await bank.wipe_bank(ctx.guild)
            await ctx.send("All bank accounts have been deleted.")

    @commands.is_owner()
    @commands.command()
    async def bankprune(self, ctx: commands.Context, confirmation: bool = False):
        """Prune bank accounts for users who no longer share a server with the bot.

        Examples:
        - `[p]bankprune` - Did not confirm. Shows the help message.
        - `[p]bankprune yes`

        **Arguments:**
        - `<confirmation>` This will default to false unless specified.
        """

        if confirmation is False:
            await ctx.send(
                (
                    "This will delete all bank accounts for users "
                    "who no longer share a server with the bot."
                    "\nIf you're sure, type `{prefix}bankprune yes`"
                ).format(prefix=ctx.clean_prefix)
            )
        else:
            await bank.bank_prune(self.bot)
            await ctx.send(
                "Bank accounts for users who "
                "no longer share a server with the bot have been pruned."
            )

    @guild_only_check()
    @commands.command(aliases=["payday"])
    async def daily(self, ctx: commands.Context):
        """Get some free daily currency."""
        author = ctx.author
        cur_time = calendar.timegm(ctx.message.created_at.utctimetuple())
        credits_name = await bank.get_currency_name(ctx.guild)

        # Gets the latest time the user used the command successfully and adds the global payday time
        next_daily = await self.config.user(author).next_daily() + await self.config.PAYDAY_TIME()
        if cur_time >= next_daily:
            weekend = discord.utils.utcnow().isoweekday() > 5
            try:
                credits = await self.config.PAYDAY_CREDITS() * (2 if weekend else 1)
                await bank.deposit_credits(author, credits)
            except errors.BalanceTooHigh as exc:
                await bank.set_balance(author, exc.max_balance)
                d = (
                    "You've reached the maximum amount of {currency}!"
                    "\n\nYou currently have {new_balance} {currency}."
                ).format(currency=credits_name, new_balance=humanize_number(exc.max_balance))
                await ctx.send(embed=discord.Embed(description=d, color=await ctx.embed_color()))
                return
            # Sets the current time as the latest payday
            await self.config.user(author).next_daily.set(cur_time)
            pos = await bank.get_leaderboard_position(author)
            t = f"Here, take some {credits_name}, {author.name}!"
            if weekend:
                d = (
                    "Enjoy {amount} {currency}!\n"
                    "You have earned {amount} {currency} more as a weekend bonus!\n\n"
                    "Now you have {new_balance} {currency}!"
                )
            else:
                d = "Enjoy {amount} {currency}!\n\nNow you have {new_balance} {currency}!"
            d = d.format(
                amount=bold(humanize_number(await self.config.PAYDAY_CREDITS())),
                currency=credits_name,
                new_balance=bold(humanize_number(await bank.get_balance(author))),
            )
            f = "You are currently #{pos} on the global leaderboard!".format(
                pos=humanize_number(pos) if pos else pos
            )
            e = discord.Embed(title=t, description=d, color=await ctx.embed_color())
            e.set_author(name=author.display_name, icon_url=author.display_avatar)
            e.set_footer(text=f)
            await ctx.send(embed=e)
        else:
            dtime = self.display_time(next_daily - cur_time)
            d = "Too soon. You can only claim once everyday."
            e = discord.Embed(description=d, color=await ctx.embed_color())
            e.set_author(name=author.display_name, icon_url=author.display_avatar)
            e.set_footer(text="You have to wait for {time} more.".format(time=dtime))
            await ctx.send(embed=e)

    @guild_only_check()
    @commands.command(aliases=["lb"])
    async def leaderboard(self, ctx: commands.Context, top: int = 10, show_global: bool = False):
        """Print the leaderboard.

        Defaults to top 10.

        Examples:
        - `[p]leaderboard`
        - `[p]leaderboard 50` - Shows the top 50 instead of top 10.
        - `[p]leaderboard 100 yes` - Shows the top 100 from all servers.

        **Arguments**

        - `<top>` How many positions on the leaderboard to show. Defaults to 10 if omitted.
        - `<show_global>` Whether to include results from all servers. This will default to false unless specified.
        """
        guild = ctx.guild
        author = ctx.author
        embed_requested = await ctx.embed_requested()
        footer_message = _("Page {page_num}/{page_len}.")
        max_bal = await bank.get_max_balance(ctx.guild)

        if top < 1:
            top = 10
        base_embed = discord.Embed(title=_("Economy Leaderboard"))
        if show_global and await bank.is_global():
            # show_global is only applicable if bank is global
            bank_sorted = await bank.get_leaderboard(positions=top, guild=None)
            base_embed.set_author(
                name=ctx.bot.user.display_name, icon_url=ctx.bot.user.display_avatar
            )
        else:
            bank_sorted = await bank.get_leaderboard(positions=top, guild=guild)
            if guild:
                base_embed.set_author(name=guild.name, icon_url=guild.icon)

        try:
            bal_len = len(humanize_number(bank_sorted[0][1]["balance"]))
            bal_len_max = len(humanize_number(max_bal))
            if bal_len > bal_len_max:
                bal_len = bal_len_max
            # first user is the largest we'll see
        except IndexError:
            return await ctx.send(_("There are no accounts in the bank."))
        pound_len = len(str(len(bank_sorted)))
        header = "{pound:{pound_len}}{score:{bal_len}}{name:2}\n".format(
            pound="#",
            name=_("Name"),
            score=_("Score"),
            bal_len=bal_len + 6,
            pound_len=pound_len + 3,
        )
        highscores = []
        pos = 1
        temp_msg = header
        for acc in bank_sorted:
            try:
                name = guild.get_member(acc[0]).display_name
            except AttributeError:
                user_id = ""
                if await ctx.bot.is_owner(ctx.author):
                    user_id = f"({str(acc[0])})"
                name = f"{acc[1]['name']} {user_id}"

            balance = acc[1]["balance"]
            if balance > max_bal:
                balance = max_bal
                await bank.set_balance(MOCK_MEMBER(acc[0], guild), balance)
            balance = humanize_number(balance)
            if acc[0] != author.id:
                temp_msg += (
                    f"{f'{humanize_number(pos)}.': <{pound_len+2}} "
                    f"{balance: <{bal_len + 5}} {name}\n"
                )

            else:
                temp_msg += (
                    f"{f'{humanize_number(pos)}.': <{pound_len+2}} "
                    f"{balance: <{bal_len + 5}} "
                    f"<<{author.display_name}>>\n"
                )
            if pos % 10 == 0:
                if embed_requested:
                    embed = base_embed.copy()
                    embed.description = box(temp_msg, lang="md")
                    embed.set_footer(
                        text=footer_message.format(
                            page_num=len(highscores) + 1,
                            page_len=ceil(len(bank_sorted) / 10),
                        )
                    )
                    highscores.append(embed)
                else:
                    highscores.append(box(temp_msg, lang="md"))
                temp_msg = header
            pos += 1

        if temp_msg != header:
            if embed_requested:
                embed = base_embed.copy()
                embed.description = box(temp_msg, lang="md")
                embed.set_footer(
                    text=footer_message.format(
                        page_num=len(highscores) + 1,
                        page_len=ceil(len(bank_sorted) / 10),
                    )
                )
                highscores.append(embed)
            else:
                highscores.append(box(temp_msg, lang="md"))

        if highscores:
            await menu(ctx, highscores)
        else:
            await ctx.send(_("No balances found."))

    @guild_only_check()
    @commands.command()
    async def payouts(self, ctx: commands.Context):
        """Show the payouts for the slot machine."""
        embed = discord.Embed(title="Slot Machine Payouts", color=await ctx.embed_color())
        embed.description = (
            "{bag.value} {bag.value} {bag.value} : Bet * 50\n"
            "{coin.value} {coin.value} {coin.value} : Bet * 30\n"
            "{bag.value} {bag.value} {blank} : Bet * 25\n"
            "{coin.value} {coin.value} {blank} : Bet * 15\n"
            "{flc.value} {flc.value} {flc.value} : Bet * 12\n"
            "{flc.value} {flc.value} {blank} : Bet * 8\n\n"
            "`Three Symbols :` Bet * 10\n"
            "`Two Symbols   :` Bet * 2"
        ).format(blank=BLANK, **SMReel.__dict__)
        await ctx.send(embed=embed)

    @guild_only_check()
    @commands.command()
    async def slot(self, ctx: commands.Context, bid: int):
        """Use the slot machine.

        Example:
        - `[p]slot 50`

        **Arguments**

        - `<bid>` The amount to bet on the slot machine. Winning payouts are higher when you bet more.
        """
        author = ctx.author
        guild = ctx.guild
        if await bank.is_global():
            valid_bid = await self.config.SLOT_MIN() <= bid <= await self.config.SLOT_MAX()
            slot_time = await self.config.SLOT_TIME()
            last_slot = await self.config.user(author).last_slot()
        else:
            valid_bid = (
                await self.config.guild(guild).SLOT_MIN()
                <= bid
                <= await self.config.guild(guild).SLOT_MAX()
            )
            slot_time = await self.config.guild(guild).SLOT_TIME()
            last_slot = await self.config.member(author).last_slot()
        now = calendar.timegm(ctx.message.created_at.utctimetuple())

        if (now - last_slot) < slot_time:
            await ctx.send(_("You're on cooldown, try again in a bit."))
            return
        if not valid_bid:
            await ctx.send(_("That's an invalid bid amount, sorry :/"))
            return
        if not await bank.can_spend(author, bid):
            await ctx.send(_("You ain't got enough money, friend."))
            return
        if await bank.is_global():
            await self.config.user(author).last_slot.set(now)
        else:
            await self.config.member(author).last_slot.set(now)
        await self.slot_machine(ctx, author, ctx.channel, bid)

    @staticmethod
    async def slot_machine(ctx, author, channel, bid):
        default_reel = deque(cast(Iterable, SMReel))
        reels = []
        for i in range(3):
            default_reel.rotate(random.randint(-999, 999))  # weeeeee
            new_reel = deque(default_reel, maxlen=3)  # we need only 3 symbols
            reels.append(new_reel)  # for each reel
        rows = (
            (reels[0][0], reels[1][0], reels[2][0]),
            (reels[0][1], reels[1][1], reels[2][1]),
            (reels[0][2], reels[1][2], reels[2][2]),
        )

        slot = "~~\n~~"  # Mobile friendly
        for i, row in enumerate(rows):  # Let's build the slot to show
            sign = "{blank} ".format(blank=BLANK)
            if i == 1:
                sign = "{arrow} ".format(arrow=ARROW)
            slot += "{}{} {} {}\n".format(
                sign, *[c.value for c in row]  # pylint: disable=no-member
            )

        payout = PAYOUTS.get(rows[1])
        if not payout:
            # Checks for two-consecutive-symbols special rewards
            payout = PAYOUTS.get((rows[1][0], rows[1][1]), PAYOUTS.get((rows[1][1], rows[1][2])))
        if not payout:
            # Still nothing. Let's check for 3 generic same symbols
            # or 2 consecutive symbols
            has_three = rows[1][0] == rows[1][1] == rows[1][2]
            has_two = (rows[1][0] == rows[1][1]) or (rows[1][1] == rows[1][2])
            if has_three:
                payout = PAYOUTS["3 symbols"]
            elif has_two:
                payout = PAYOUTS["2 symbols"]

        pay = 0
        if payout:
            then = await bank.get_balance(author)
            pay = payout["payout"](bid)
            now = then - bid + pay
            try:
                await bank.set_balance(author, now)
            except errors.BalanceTooHigh as exc:
                await bank.set_balance(author, exc.max_balance)
                await channel.send(
                    _(
                        "You've reached the maximum amount of {currency}! "
                        "Please spend some more \N{GRIMACING FACE}\n{old_balance} -> {new_balance}!"
                    ).format(
                        currency=await bank.get_currency_name(getattr(channel, "guild", None)),
                        old_balance=humanize_number(then),
                        new_balance=humanize_number(exc.max_balance),
                    )
                )
                return
            phrase = T_(payout["phrase"])
        else:
            then = await bank.get_balance(author)
            await bank.withdraw_credits(author, bid)
            now = then - bid
            phrase = bold("You didn't win anything!")
        embed = discord.Embed(title=f"{author.name}'s Slot Machine", color=await ctx.embed_color())
        embed.description = "{slot}\n{phrase}\nYour bid: {bid}".format(
            slot=slot, phrase=phrase, bid=bold(humanize_number(bid))
        )
        embed.add_field(
            name="Balance",
            value="Old Balance: {old}\nNew Balance: {new}".format(
                old=bold(humanize_number(then)), new=bold(humanize_number(now))
            ),
        )
        await channel.send(embed=embed)

    @guild_only_check()
    @bank.is_owner_if_bank_global()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.group()
    async def economyset(self, ctx: commands.Context):
        """Base command to manage Economy settings."""
        pass

    @economyset.command(name="showsettings")
    async def economyset_showsettings(self, ctx: commands.Context):
        """
        Shows the current economy settings
        """
        role_paydays = []
        guild = ctx.guild
        if await bank.is_global():
            conf = self.config
        else:
            conf = self.config.guild(guild)
            for role in guild.roles:
                rolepayday = await self.config.role(role).PAYDAY_CREDITS()
                if rolepayday:
                    role_paydays.append(f"{role}: {rolepayday}")
        await ctx.send(
            box(
                _(
                    "---Economy Settings---\n"
                    "Minimum slot bid: {slot_min}\n"
                    "Maximum slot bid: {slot_max}\n"
                    "Slot cooldown: {slot_time}\n"
                    "Payday amount: {payday_amount}\n"
                    "Payday cooldown: {payday_time}\n"
                    "Credits per message (default): {default_min}-{default_max}\n"
                    "Whitelisted channels: {whitelisted_channels}\n"
                    "Blacklisted channels: {blacklisted_channels}\n"
                ).format(
                    slot_min=humanize_number(await conf.SLOT_MIN()),
                    slot_max=humanize_number(await conf.SLOT_MAX()),
                    slot_time=humanize_number(await conf.SLOT_TIME()),
                    payday_time=humanize_number(await conf.PAYDAY_TIME()),
                    payday_amount=humanize_number(await conf.PAYDAY_CREDITS()),
                    default_min=humanize_number(await conf.CREDITS_PER_MESSAGE.default_min()),
                    default_max=humanize_number(await conf.CREDITS_PER_MESSAGE.default_max()),
                    whitelisted_channels=", ".join(
                        [str(ch) for ch in await conf.WHITELISTED_CHANNELS()]
                    ),
                    blacklisted_channels=", ".join(
                        [str(ch) for ch in await conf.BLACKLISTED_CHANNELS()]
                    ),
                )
            )
        )
        if role_paydays:
            await ctx.send(box(_("---Role Payday Amounts---\n") + "\n".join(role_paydays)))

    @economyset.command()
    async def slotmin(self, ctx: commands.Context, bid: positive_int):
        """Set the minimum slot machine bid.

        Example:
        - `[p]economyset slotmin 10`

        **Arguments**

        - `<bid>` The new minimum bid for using the slot machine. Default is 5.
        """
        guild = ctx.guild
        is_global = await bank.is_global()
        if is_global:
            slot_max = await self.config.SLOT_MAX()
        else:
            slot_max = await self.config.guild(guild).SLOT_MAX()
        if bid > slot_max:
            await ctx.send(
                _(
                    "Warning: Minimum bid is greater than the maximum bid ({max_bid}). "
                    "Slots will not work."
                ).format(max_bid=humanize_number(slot_max))
            )
        if is_global:
            await self.config.SLOT_MIN.set(bid)
        else:
            await self.config.guild(guild).SLOT_MIN.set(bid)
        credits_name = await bank.get_currency_name(guild)
        await ctx.send(
            _("Minimum bid is now {bid} {currency}.").format(
                bid=humanize_number(bid), currency=credits_name
            )
        )

    @economyset.command()
    async def slotmax(self, ctx: commands.Context, bid: positive_int):
        """Set the maximum slot machine bid.

        Example:
        - `[p]economyset slotmax 50`

        **Arguments**

        - `<bid>` The new maximum bid for using the slot machine. Default is 100.
        """
        guild = ctx.guild
        is_global = await bank.is_global()
        if is_global:
            slot_min = await self.config.SLOT_MIN()
        else:
            slot_min = await self.config.guild(guild).SLOT_MIN()
        if bid < slot_min:
            await ctx.send(
                _(
                    "Warning: Maximum bid is less than the minimum bid ({min_bid}). "
                    "Slots will not work."
                ).format(min_bid=humanize_number(slot_min))
            )
        credits_name = await bank.get_currency_name(guild)
        if is_global:
            await self.config.SLOT_MAX.set(bid)
        else:
            await self.config.guild(guild).SLOT_MAX.set(bid)
        await ctx.send(
            _("Maximum bid is now {bid} {currency}.").format(
                bid=humanize_number(bid), currency=credits_name
            )
        )

    @economyset.command()
    async def slottime(
        self,
        ctx: commands.Context,
        *,
        duration: TimedeltaConverter(default_unit="seconds"),  # noqa: F821
    ):
        """Set the cooldown for the slot machine.

        Examples:
        - `[p]economyset slottime 10`
        - `[p]economyset slottime 10m`

        **Arguments**

        - `<duration>` The new duration to wait in between uses of the slot machine. Default is 5 seconds.
        Accepts: seconds, minutes, hours, days, weeks (if no unit is specified, the duration is assumed to be given in seconds)
        """
        seconds = int(duration.total_seconds())
        guild = ctx.guild
        if await bank.is_global():
            await self.config.SLOT_TIME.set(seconds)
        else:
            await self.config.guild(guild).SLOT_TIME.set(seconds)
        await ctx.send(_("Cooldown is now {num} seconds.").format(num=seconds))

    @economyset.command()
    async def paydaytime(
        self,
        ctx: commands.Context,
        *,
        duration: TimedeltaConverter(default_unit="seconds"),  # noqa: F821
    ):
        """Set the cooldown for the payday command.

        Examples:
        - `[p]economyset paydaytime 86400`
        - `[p]economyset paydaytime 1d`

        **Arguments**

        - `<duration>` The new duration to wait in between uses of payday. Default is 5 minutes.
        Accepts: seconds, minutes, hours, days, weeks (if no unit is specified, the duration is assumed to be given in seconds)
        """
        seconds = int(duration.total_seconds())
        guild = ctx.guild
        if await bank.is_global():
            await self.config.PAYDAY_TIME.set(seconds)
        else:
            await self.config.guild(guild).PAYDAY_TIME.set(seconds)
        await ctx.send(
            _("Value modified. At least {num} seconds must pass between each payday.").format(
                num=seconds
            )
        )

    @economyset.command()
    async def paydayamount(self, ctx: commands.Context, creds: int):
        """Set the amount earned each payday.

        Example:
        - `[p]economyset paydayamount 400`

        **Arguments**

        - `<creds>` The new amount to give when using the payday command. Default is 120.
        """
        guild = ctx.guild
        max_balance = await bank.get_max_balance(ctx.guild)
        if creds <= 0 or creds > max_balance:
            return await ctx.send(
                _("Amount must be greater than zero and less than {maxbal}.").format(
                    maxbal=humanize_number(max_balance)
                )
            )
        credits_name = await bank.get_currency_name(guild)
        if await bank.is_global():
            await self.config.PAYDAY_CREDITS.set(creds)
        else:
            await self.config.guild(guild).PAYDAY_CREDITS.set(creds)
        await ctx.send(
            _("Every payday will now give {num} {currency}.").format(
                num=humanize_number(creds), currency=credits_name
            )
        )

    @economyset.command()
    async def rolepaydayamount(self, ctx: commands.Context, role: discord.Role, creds: int):
        """Set the amount earned each payday for a role.

        Set to `0` to remove the payday amount you set for that role.

        Only available when not using a global bank.

        Example:
        - `[p]economyset rolepaydayamount @Members 400`

        **Arguments**

        - `<role>` The role to assign a custom payday amount to.
        - `<creds>` The new amount to give when using the payday command.
        """
        guild = ctx.guild
        max_balance = await bank.get_max_balance(ctx.guild)
        if creds >= max_balance:
            return await ctx.send(
                _(
                    "The bank requires that you set the payday to be less than"
                    " its maximum balance of {maxbal}."
                ).format(maxbal=humanize_number(max_balance))
            )
        credits_name = await bank.get_currency_name(guild)
        if await bank.is_global():
            await ctx.send(_("The bank must be per-server for per-role paydays to work."))
        else:
            if creds <= 0:  # Because I may as well...
                default_creds = await self.config.guild(guild).PAYDAY_CREDITS()
                await self.config.role(role).clear()
                await ctx.send(
                    _(
                        "The payday value attached to role has been removed. "
                        "Users with this role will now receive the default pay "
                        "of {num} {currency}."
                    ).format(num=humanize_number(default_creds), currency=credits_name)
                )
            else:
                await self.config.role(role).PAYDAY_CREDITS.set(creds)
                await ctx.send(
                    _(
                        "Every payday will now give {num} {currency} "
                        "to people with the role {role_name}."
                    ).format(
                        num=humanize_number(creds), currency=credits_name, role_name=role.name
                    )
                )

    @economyset.command()
    async def setcreditsrange(self, ctx: commands.Context, min_credits: int, max_credits: int):
        """Set the default range for random credits per message.

        Example:
        - `[p]economyset setcreditsrange 1 50`

        **Arguments**

        - `<min_credits>` The minimum credits per message.
        - `<max_credits>` The maximum credits per message.
        """
        guild = ctx.guild
        if min_credits < 0 or max_credits < 0 or min_credits > max_credits:
            await ctx.send(_("Invalid range. Ensure that 0 <= min_credits <= max_credits."))
            return

        await self.config.guild(guild).CREDITS_PER_MESSAGE.default_min.set(min_credits)
        await self.config.guild(guild).CREDITS_PER_MESSAGE.default_max.set(max_credits)
        await ctx.send(
            _("Default credits per message range set to {min_credits}-{max_credits}.").format(
                min_credits=min_credits, max_credits=max_credits
            )
        )

    @economyset.command()
    async def setchannelcreditsrange(self, ctx: commands.Context, channel: discord.TextChannel, min_credits: int, max_credits: int):
        """Set the credits per message range for a specific channel.

        Example:
        - `[p]economyset setchannelcreditsrange #general 5 25`

        **Arguments**

        - `<channel>` The channel to set the credits range for.
        - `<min_credits>` The minimum credits per message.
        - `<max_credits>` The maximum credits per message.
        """
        guild = ctx.guild
        if min_credits < 0 or max_credits < 0 or min_credits > max_credits:
            await ctx.send(_("Invalid range. Ensure that 0 <= min_credits <= max_credits."))
            return

        async with self.config.guild(guild).CREDITS_PER_MESSAGE.channels() as channels:
            channels[str(channel.id)] = {"min": min_credits, "max": max_credits}

        await ctx.send(
            _("Credits per message range for {channel} set to {min_credits}-{max_credits}.").format(
                channel=channel.name, min_credits=min_credits, max_credits=max_credits
            )
        )

    @economyset.command()
    async def whitelist(self, ctx: commands.Context, channel: discord.TextChannel):
        """Whitelist a channel for earning credits per message.

        Example:
        - `[p]economyset whitelist #general`

        **Arguments**

        - `<channel>` The channel to whitelist.
        """
        guild = ctx.guild
        async with self.config.guild(guild).WHITELISTED_CHANNELS() as whitelisted_channels:
            if channel.id not in whitelisted_channels:
                whitelisted_channels.append(channel.id)
                await ctx.send(
                    _("Channel {channel} has been whitelisted for earning credits per message.").format(
                        channel=channel.name
                    )
                )
            else:
                await ctx.send(
                    _("Channel {channel} is already whitelisted.").format(channel=channel.name)
                )

    @economyset.command()
    async def blacklist(self, ctx: commands.Context, channel: discord.TextChannel):
        """Blacklist a channel from earning credits per message.

        Example:
        - `[p]economyset blacklist #general`

        **Arguments**

        - `<channel>` The channel to blacklist.
        """
        guild = ctx.guild
        async with self.config.guild(guild).BLACKLISTED_CHANNELS() as blacklisted_channels:
            if channel.id not in blacklisted_channels:
                blacklisted_channels.append(channel.id)
                await ctx.send(
                    _("Channel {channel} has been blacklisted from earning credits per message.").format(
                        channel=channel.name
                    )
                )
            else:
                await ctx.send(
                    _("Channel {channel} is already blacklisted.").format(channel=channel.name)
                )

    @economyset.command()
    async def unwhitelist(self, ctx: commands.Context, channel: discord.TextChannel):
        """Remove a channel from the whitelist.

        Example:
        - `[p]economyset unwhitelist #general`

        **Arguments**

        - `<channel>` The channel to remove from the whitelist.
        """
        guild = ctx.guild
        async with self.config.guild(guild).WHITELISTED_CHANNELS() as whitelisted_channels:
            if channel.id in whitelisted_channels:
                whitelisted_channels.remove(channel.id)
                await ctx.send(
                    _("Channel {channel} has been removed from the whitelist.").format(
                        channel=channel.name
                    )
                )
            else:
                await ctx.send(
                    _("Channel {channel} is not in the whitelist.").format(channel=channel.name)
                )

    @economyset.command()
    async def unblacklist(self, ctx: commands.Context, channel: discord.TextChannel):
        """Remove a channel from the blacklist.

        Example:
        - `[p]economyset unblacklist #general`

        **Arguments**

        - `<channel>` The channel to remove from the blacklist.
        """
        guild = ctx.guild
        async with self.config.guild(guild).BLACKLISTED_CHANNELS() as blacklisted_channels:
            if channel.id in blacklisted_channels:
                blacklisted_channels.remove(channel.id)
                await ctx.send(
                    _("Channel {channel} has been removed from the blacklist.").format(
                        channel=channel.name
                    )
                )
            else:
                await ctx.send(
                    _("Channel {channel} is not in the blacklist.").format(channel=channel.name)
                )

    # What would I ever do without stackoverflow?
    @staticmethod
    def display_time(seconds, granularity=2):
        intervals = (  # Source: http://stackoverflow.com/a/24542445
            (_("weeks"), 604800),  # 60 * 60 * 24 * 7
            (_("days"), 86400),  # 60 * 60 * 24
            (_("hours"), 3600),  # 60 * 60
            (_("minutes"), 60),
            (_("seconds"), 1),
        )

        result = []

        for name, count in intervals:
            value = seconds // count
            if value:
                seconds -= value * count
                if value == 1:
                    name = name.rstrip("s")
                result.append("{} {}".format(value, name))
        return ", ".join(result[:granularity])
