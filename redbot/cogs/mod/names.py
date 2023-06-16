from typing import Union, cast

import discord
from discord.errors import NotFound
from discord.ui import Button
from discord.utils import escape_markdown as unmarkdown
from redbot.core import bank, commands
from redbot.core.utils.chat_formatting import bold, humanize_list, humanize_number, pagify
from redbot.core.utils.common_filters import (
    escape_spoilers_and_mass_mentions,
    filter_invites,
    filter_various_mentions,
)
from redbot.core.utils.mod import get_audit_reason
from redbot.core.utils.views import View, _StopButton
from .abc import MixinMeta
from .utils import is_allowed_by_hierarchy

STATUS_EMOJIS = {
    "streaming": 749221434039205909,
    "mobile_online": 947032955904229396,
    "online": 749221433552404581,
    "mobile_idle": 947032931526901760,
    "idle": 749221433095356417,
    "mobile_dnd": 947032903966134312,
    "dnd": 749221432772395140,
    "offline": 749221433049088082,
}

PROFILE_EMOJIS = {
    "staff": 954383694284587078,
    "partner": 954383655806066718,
    "hypesquad": 954383838581231667,
    "bug_hunter": 954383621916086312,
    "hypesquad_bravery": 954383915068555294,
    "hypesquad_brilliance": 954383900837314580,
    "hypesquad_balance": 954383947343757354,
    "early_supporter": 954384007922073630,
    "bug_hunter_level_2": 954383608532049960,
    "verified_bot_1": 933696996873732168,
    "verified_bot_2": 933696948723134494,
    "verified_bot_developer": 954383743865470986,
    "discord_certified_moderator": 954383710105509898,
    "active_developer": 1089609770174001274,
    # Non-Flags:
    "bot": 848557763172892722,
}

# FORMAT: {server_id: {role_id: [emoji_id, title]}}
SPECIAL_BADGES = {
    825535079719501824: {  # Kiki✨'s Support (ʚ﹕The Cloud House﹕ɞ)
        954373039972298752: [954383743865470986, "Bot Developer"],
        833755355711930378: [915138297355968574, "Support Staff"],
        954374737700737075: [954383608532049960, "Bug Hunter"],
        943331260590338058: [954398197751611413, "Bot Voter"],
    },
    133049272517001216: {  # Red - Discord Bot
        346744009458450433: [917079459641831474, "Contributor"],
        506598631726383105: [925401264395796481, "Cog Creator"],
    },
}


class ModInfo(MixinMeta):
    """
    Commands regarding names, userinfo, etc.
    """

    async def get_names(self, user: Union[discord.Member, discord.User]):
        user_data = await self.config.user(user).all()
        usernames, display_names, nicks = user_data["past_names"], user_data["past_display_names"], []
        usernames = list(map(escape_spoilers_and_mass_mentions, filter(None, usernames)))
        display_names = list(map(escape_spoilers_and_mass_mentions, filter(None, display_names)))
        if isinstance(user, discord.Member):
            nicks = await self.config.member(user).past_nicks()
        nicks = list(map(escape_spoilers_and_mass_mentions, filter(None, nicks)))
        return usernames, display_names, nicks

    @staticmethod
    def handle_custom(user: Union[discord.Member, discord.User]):
        c_acts = [a for a in user.activities if a.type == discord.ActivityType.custom]
        if not c_acts:
            return None
        a = c_acts[0]
        if a.name and a.emoji:
            return f"`Custom Status ` : {a.emoji} {unmarkdown(a.name)}"
        return f"`Custom Status ` : {unmarkdown(a.name or a.emoji)}"

    @staticmethod
    def handle_streaming(user: Union[discord.Member, discord.User]):
        s_acts = [a for a in user.activities if a.type == discord.ActivityType.streaming]
        if not s_acts:
            return None
        s_act = s_acts[0]
        if isinstance(s_act, discord.Streaming):
            act = "`Streaming     ` : [{name}{sep}{game}]({url}){platform}".format(
                name=unmarkdown(s_act.name) if s_act.name else "",
                sep=" | " if s_act.game else "",
                game=unmarkdown(s_act.game) if s_act.game else "",
                url=s_act.url,
                platform=f" on {s_act.platform}" if s_act.platform else "",
            )
            if not s_act.name and not s_act.game:
                act = f"`Streaming     ` : {s_act.url}"
        else:
            act = f"`Streaming     ` : {s_act.name}"
        return act

    @staticmethod
    def handle_listening(user: Union[discord.Member, discord.User]):
        l_acts = [a for a in user.activities if a.type == discord.ActivityType.listening]
        if not l_acts:
            return None
        l_act = l_acts[0]
        if isinstance(l_act, discord.Spotify):
            act = "`Listening to  ` : [{title}{sep}{artist}]({url})".format(
                title=unmarkdown(l_act.title),
                sep=" by " if l_act.artists else "",
                artist=unmarkdown(humanize_list(l_act.artists)) if l_act.artists else "",
                url=l_act.track_url,
            )
        else:
            act = f"`Listening to  ` : {l_act.name}"
        return act

    @staticmethod
    def handle_playing(user: Union[discord.Member, discord.User]):
        p_acts = [a.name for a in user.activities if a.type == discord.ActivityType.playing]
        if not p_acts:
            return None
        return f"`Playing       ` : {humanize_list(p_acts)}"

    @staticmethod
    def handle_watching(user: Union[discord.Member, discord.User]):
        w_acts = [a.name for a in user.activities if a.type == discord.ActivityType.watching]
        if not w_acts:
            return None
        return f"`Watching      ` : {humanize_list(w_acts)}"

    @staticmethod
    def handle_competing(user: Union[discord.Member, discord.User]):
        c_acts = [a.name for a in user.activities if a.type == discord.ActivityType.competing]
        if not c_acts:
            return None
        return f"`Competing in  ` : {humanize_list(c_acts)}"

    def get_status_string(self, user: Union[discord.Member, discord.User]):
        string = ""
        for status in [
            self.handle_custom(user),
            self.handle_streaming(user),
            self.handle_listening(user),
            self.handle_playing(user),
            self.handle_watching(user),
            self.handle_competing(user),
        ]:
            if not status:
                continue
            string += f"{status}\n"
        return string

    @commands.command(aliases=["ui", "whois"])
    @commands.bot_has_permissions(embed_links=True, use_external_emojis=True)
    async def userinfo(
        self,
        ctx: commands.Context,
        *,
        user: Union[discord.Member, discord.User] = commands.Author,
    ):
        """Show information about a user.

        This includes fields for status, discord join date, server join date,
        voice state and previous usernames/display names/nicknames.

        If the member has no roles, previous usernames, display names, or nicknames,
        these fields will be omitted.
        """
        guild = ctx.guild
        timestamp = int(user.created_at.timestamp())
        created_on = f"<t:{timestamp}>\n(<t:{timestamp}:R>)"
        usernames, display_names, nicks = await self.get_names(ctx, user)

        status_emoji = None
        status_string = None
        roles = None
        name = str(user)
        color = await ctx.embed_color()
        member_number = None
        voice_state = None
        shared_guilds = None
        joined_on = None
        since_joined = None
        user_joined = None

        if guild and isinstance(user, discord.Member):
            status = "offline"
            if any(a.type is discord.ActivityType.streaming for a in user.activities):
                status = "streaming"
            elif user.status == discord.Status.online:
                status = "mobile_online" if user.is_on_mobile() else "online"
            elif user.status == discord.Status.idle:
                status = "mobile_idle" if user.is_on_mobile() else "idle"
            elif user.status == discord.Status.dnd:
                status = "mobile_dnd" if user.is_on_mobile() else "dnd"
            status_emoji = ctx.bot.get_emoji(STATUS_EMOJIS[status])

            status_string = self.get_status_string(user)
            roles = user.roles[-1:0:-1]
            joined_on = "{}\n({} days ago)".format(user_joined, since_joined)
            name = f"{name} ~ {user.nick}" if user.nick else name
            color = user.color
            member_number = sorted(guild.members, key=lambda m: m.joined_at).index(user) + 1
            voice_state = user.voice
            if user == guild.me:
                shared_guilds = len(ctx.bot.guilds)
            else:
                shared_guilds = len(user.mutual_guilds)

            if user.joined_at:
                joined_on = "<t:{0}>\n(<t:{0}:R>)".format(int(user.joined_at.timestamp()))
            else:
                joined_on = "Unknown"
        title = unmarkdown(name) + " "
        if status_emoji:
            title = f"{status_emoji} {unmarkdown(name)} "
        description = status_string or ""
        if shared_guilds:
            description += f"`Shared Servers` : {shared_guilds}"

        data = discord.Embed(title=title, description=description, color=color)
        data.set_thumbnail(url=user.display_avatar.url)
        data.add_field(name="Joined Discord on", value=created_on)
        if joined_on:
            data.add_field(name="Joined This Server on", value=joined_on)

        role_str = None
        if roles:
            role_str = ", ".join([x.mention for x in roles])
            if len(role_str) > 1024:
                continuation_string = "and {nn} more roles."
                available_length = 1024 - len(continuation_string)
                role_chunks = []
                remaining_roles = 0
                for r in roles:
                    chunk = f"{r.mention}, "
                    if len(chunk) < available_length:
                        available_length -= len(chunk)
                        role_chunks.append(chunk)
                    else:
                        remaining_roles += 1
                role_chunks.append(continuation_string.format(nn=remaining_roles))
                role_str = "".join(role_chunks)

        if role_str:
            if len(roles) > 1:
                data.add_field(name=f"Roles ({len(roles)})", value=role_str, inline=False)
            else:
                data.add_field(name="Role", value=role_str, inline=False)

        for single_form, plural_form, names in (
            ("Previous Username", "Previous Usernames", usernames),
            ("Previous Display Name", "Previous Display Names", display_names),
            ("Previous Nickname", "Previous Nicknames", nicks),
        ):
            if names:
                data.add_field(
                    name=f"{plural_form} ({len(names)})" if len(names) > 1 else single_form,
                    value=filter_invites(", ".join(names)),
                    inline=False,
                )

        if voice_state:
            data.add_field(
                name="Current Voice Channel",
                value="{0.mention} (ID: {0.id})".format(voice_state.channel),
                inline=False,
            )

        badges = user.public_flags.all()
        flags_count = 0
        badge_str = ""
        if badges:
            format_name = lambda name: name.replace("_", " ").title()
            get_emoji = lambda name: ctx.bot.get_emoji(PROFILE_EMOJIS[name])

            flags = [f.name for f in badges]
            flags_count = len(flags)
            if user.bot:
                b1 = str(get_emoji("verified_bot_1"))
                b2 = str(get_emoji("verified_bot_2"))
                data.title += b1 + b2 if "verified_bot" in flags else str(get_emoji("bot"))
                badge_str = None
            else:
                badge_str += "\n".join(
                    [
                        f"{get_emoji(flag)} {format_name(flag)}"
                        if flag in PROFILE_EMOJIS
                        else f"❓ {format_name(flag)}"
                        for flag in flags
                    ]
                )
        boosted_servers = []
        for guild in ctx.bot.guilds:
            member = guild.get_member(user.id)
            if not member:
                continue
            boosting = member.premium_since
            if not boosting:
                continue
            boosted_servers.append(guild)
        if user.avatar and (user.avatar.is_animated() or user.banner or boosted_servers):
            flags_count = len(flags) + 1
            e = ctx.bot.get_emoji(710871154839126036)
            badge_str += f"\n{e} Nitro Subscriber"
        if badge_str:
            if flags_count > 1:
                data.add_field(name=f"Badges ({flags_count})", value=badge_str, inline=False)
            else:
                data.add_field(name="Badge", value=badge_str, inline=False)

        special_badges = []
        if not user.bot:
            for guild_id, roles in SPECIAL_BADGES.items():
                if (g := ctx.bot.get_guild(guild_id)) and (m := g.get_member(user.id)):
                    for r in reversed(m.roles):
                        if r.id in roles:
                            role = roles[r.id]
                            special_badges.append(f"{ctx.bot.get_emoji(role[0])} {role[1]}")
            if (g := ctx.bot.get_guild(825535079719501824)) and g.get_member(user.id):
                e = ctx.bot.get_emoji(915569880160436264)
                special_badges.append(f"{e} [The Cloud House](https://discord.gg/Zef3pD8Yt5)")

        if special_badges:
            name = (
                f"Special Badges ({len(special_badges)})"
                if len(special_badges) > 1
                else "Special Badge"
            )
            data.add_field(name=name, value="\n".join(special_badges))

        if not user.bot and ctx.bot.get_cog("Economy"):
            balance = await bank.get_balance(user)
            currency = await bank.get_currency_name(guild)
            bankstat = f"**Coins**: {humanize_number(balance)} {currency}"
            if balance > 0:
                data.add_field(name="Balance", value=bankstat, inline=False)

        ordinal = lambda n: "%d%s" % (
            n,
            "tsnrhtdd"[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10 :: 4],
        )

        if member_number:
            data.set_footer(text="{} Member | User ID: {}".format(ordinal(member_number), user.id))
        else:
            data.set_footer(text="User ID: {}".format(user.id))

        view = View()
        stop_button = _StopButton()
        view.add_item(stop_button)
        if user.avatar:
            view.add_item(
                Button(
                    style=discord.ButtonStyle.link,
                    label="User Avatar",
                    url=user.avatar.with_format("png").url,
                )
            )
        if isinstance(user, discord.Member) and user.guild_avatar:
            view.add_item(
                Button(
                    style=discord.ButtonStyle.link,
                    label="Server Avatar",
                    url=user.guild_avatar.with_format("png").url,
                )
            )

        # Banner is only available via bot.fetch_user()
        user = await ctx.bot.fetch_user(user.id)
        try:
            member = await guild.fetch_member(user.id)
        except NotFound:
            member = None

        if user.banner:
            data.set_image(url=user.banner.with_size(4096).url)
            view.add_item(
                Button(
                    style=discord.ButtonStyle.link,
                    label="User Banner",
                    url=user.banner.with_format("png").url,
                )
            )
        if member and member.banner:
            data.set_image(url=member.banner.with_size(4096).url)
            view.add_item(
                Button(
                    style=discord.ButtonStyle.link,
                    label="Server Banner",
                    url=member.banner.with_format("png").url,
                )
            )

        if len(view.children) > 3:
            view.remove_item(stop_button)
            view.add_item(_StopButton(row=1))
        await view.start(ctx, embed=data)

    @commands.command()
    @commands.guild_only()
    async def names(self, ctx: commands.Context, *, member: discord.Member = commands.Author):
        """Show previous usernames, display names, and server nicknames of a member."""
        usernames, display_names, nicks = await self.get_names(member)
        parts = []
        for header, names in (
            ("Past 20 usernames:", usernames),
            ("Past 20 display names:", display_names),
            ("Past 20 nicknames:", nicks),
        ):
            if names:
                parts.append(bold(header) + ", ".join(names))
        if parts:
            # each name can have 32 characters, we store 3*20 names which totals to
            # 60*32=1920 characters which is quite close to the message length limit
            for msg in pagify(filter_various_mentions("\n\n".join(parts))):
                await ctx.send(msg)

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_nicknames=True)
    @commands.admin_or_permissions(manage_nicknames=True)
    async def rename(self, ctx: commands.Context, member: discord.Member, *, nickname: str = ""):
        """Change a member's nickname.

        Leaving the nickname argument empty will remove it.
        """
        nickname = nickname.strip()
        me = cast(discord.Member, ctx.me)
        if not nickname:
            nickname = None
        elif not 2 <= len(nickname) <= 32:
            await ctx.send("Nicknames must be between 2 and 32 characters long.")
            return
        if not (
            (me.guild_permissions.manage_nicknames or me.guild_permissions.administrator)
            and me.top_role > member.top_role
            and member != ctx.guild.owner
        ):
            await ctx.send(
                "I do not have permission to rename that member. "
                "They may be higher than or equal to me in the role hierarchy."
            )
        elif ctx.author != member and not await is_allowed_by_hierarchy(
            self.bot, self.config, ctx.guild, ctx.author, member
        ):
            await ctx.send(
                "I cannot let you do that. You are not higher than the user in the role hierarchy."
            )
        else:
            try:
                await member.edit(reason=get_audit_reason(ctx.author, None), nick=nickname)
            except discord.Forbidden:
                # Just in case we missed something in the permissions check above
                await ctx.send("I don't have the permission to rename that member.")
            except discord.HTTPException as exc:
                if exc.status == 400:  # BAD REQUEST
                    await ctx.send("That nickname is invalid.")
                else:
                    await ctx.send("An unexpected error has occurred.")
            else:
                await ctx.send("Done.")
