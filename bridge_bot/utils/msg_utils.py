import argparse
import re
from functools import partial

from neonize.utils.enum import Presence
from neonize.utils.message import get_message_type
from telethon import TelegramClient, types
from telethon.helpers import add_surrogate, del_surrogate
from telethon.tl.types import PeerUser
from telethon.types import User

from bridge_bot import JID, Message, jid
from bridge_bot.config import bot, conf
from bridge_bot.fun.stuff import force_read_more
from bridge_bot.others.exceptions import ArgumentParserError

from .bot_utils import entities_has_spoiler

# isort: off
from .events import (
    Event,  # noqa  # pylint: disable=unused-import
    construct_event,
    construct_message,
    construct_msg_and_evt,
    download_media,
    event_handler,
)

# isort: on


def is_echo(sender):
    if conf.UB_REC_EVENTS and sender in bot.tg_client_ids:
        return True


def user_is_admin(user: str, members: list):
    for member in members:
        if user == member.JID.User or user == member.PhoneNumber.User:
            return member.IsAdmin


def user_is_dev(user: str):
    user: int
    user = int(user)
    return user == conf.DEV


def user_is_owner(user: str | int):
    user = str(user)
    return user in conf.OWNER


CLEANR = re.compile("<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});")


def cleanhtml(raw_html):
    cleantext = re.sub(CLEANR, "", raw_html)
    return cleantext


async def get_user_info(
    user_id: str | None = None,
    server: str = "s.whatsapp.net",
    user_jid: JID | None = None,
):
    jid_ = user_jid or jid.build_jid(user_id, server)
    info = await bot.client.contact.get_contact(jid_)
    if not info.Found:
        try:
            jid_ = (
                await bot.client.get_pn_from_lid(jid_)
                if jid_.Server == "lid"
                else await bot.client.get_lid_from_pn(jid_)
            )
            info = await bot.client.contact.get_contact(jid_)
        except Exception:
            pass
    return info


def get_tg_edit_data(text, raw) -> (dict, Message | None):
    message = load_proto(raw)
    msg = get_message_type(message)
    if isinstance(msg, str):
        msg = Message(conversation=text)
    else:
        if hasattr(msg, "text"):
            msg.text = text
        elif hasattr(msg, "caption"):
            msg.caption = text
        else:
            return {}, None
        field_name = msg.__class__.__name__[0].lower() + msg.__class__.__name__[1:]
        msg = Message(**{field_name: msg})
    return {"raw": msg.SerializeToString()}, msg


def get_wa_edit_data(event: Event) -> dict:
    if event.media:
        msg = event.media
        field_name = msg.__class__.__name__[0].lower() + msg.__class__.__name__[1:]
        msg = Message(**{field_name: msg})
    elif event.text and not event.media:
        msg = Message(conversation=event.text)
    else:
        return {}
    return {"raw": msg.SerializeToString()}


async def replace_mentions_for_tg(client: TelegramClient, text: str) -> str:
    """
    Replace @:digits patterns in text with markdown user mentions

    Args:
        client: Authenticated TelegramClient instance
        text: Input string containing @:digits patterns

    Returns:
        String with replaced mentions
    """
    if not text:
        return ""
    pattern = r"@:(\d+)"
    last_end = 0
    parts = []

    for match in re.finditer(pattern, text):
        # Add text before the match
        parts.append(text[last_end : match.start()])
        user_id = int(match.group(1))

        try:
            # Fetch user entity
            entity = await client.get_entity(user_id)

            # Verify it's a user account
            if not isinstance(entity, User):
                parts.append(match.group(0))
                continue

            # Get the best available name
            name = (
                entity.first_name or entity.last_name or entity.username or str(user_id)
            )

            # Escape markdown special characters
            name = re.sub(r"([\[\]()])", r"\\\1", name)

            # Create markdown mention
            mention = f"[@{name}](tg://user?id={user_id})"
            parts.append(mention)
        except Exception:
            # Keep original pattern if we can't fetch user
            parts.append(match.group(0))
        finally:
            last_end = match.end()

    # Add remaining text after last match
    parts.append(text[last_end:])
    return "".join(parts)


def replace_mentions_for_wa(text: str) -> str:
    """
    Replace @:digits patterns in text with @digits format

    Args:
        text: Input string containing @:digits patterns

    Returns:
        String with colons removed from mentions
    """
    if not text:
        return text

    return re.sub(r"@:(\d+)", r"@\1", text)


async def replace_wa_mentions(text, event):
    if not text:
        return text
    text = await replace_hashed(text) if "##" in text else text
    lid_address = event.lid_address
    pattern = r"@([0-9]{5,16}|0)"
    last_end = 0
    parts = []

    for match in re.finditer(pattern, text):
        # Add text before the match
        parts.append(text[last_end : match.start()])
        user_id = match.group(1)

        try:
            if not lid_address:
                user_jid = jid.build_jid(user_id)
                user_info = await get_user_info(user_jid=user_jid)
                try:
                    user_id = (await bot.client.get_lid_from_pn(user_jid)).User
                except Exception:
                    user_id = "XXXXXXXXX" if await user_is_on_wa(user_id) else user_id
                    parts.append(f"@{user_id}")
                    continue
            else:
                user_info = await get_user_info(user_id, "lid")

            if not user_info.Found:
                parts.append(f"@{user_id}")
                continue

            name = user_info.PushName or "Unknown_user"
            parts.append(f"@{name}(@:{user_id})")

        except Exception:
            parts.append(match.group(0))

        finally:
            last_end = match.end()

    parts.append(text[last_end:])
    return "".join(parts)


async def replace_hashed(text: str, wa=True) -> str:
    """
    Processes text to handle ##-prefixed tokens:
    - Tokens must be surrounded by whitespace/newline or at string boundaries
    - For 5-16 digit tokens: replace digits with 'X' if user_is_on_wa returns True
    - All other tokens: remove entirely including the ## prefix
    """
    # Precompile regex pattern for efficiency
    pattern = re.compile(r"(?<!\S)(##\S+)(?=\s|$)")
    last_end = 0
    parts = []

    for match in pattern.finditer(text):
        # Add text before the match
        parts.append(text[last_end : match.start()])
        full_token = match.group(1)
        token = full_token[2:]
        if wa and token.isdigit() and 5 <= len(token) <= 16:
            if await user_is_on_wa(token):
                parts.append("X" * len(token))

        last_end = match.end()

    parts.append(text[last_end:])
    return "".join(parts)


async def user_is_on_wa(number: str):
    response = await bot.client.is_on_whatsapp(number)
    return response[0].IsIn


def load_proto(data, jid=False):
    msg = Message() if not jid else JID()
    msg.ParseFromString(data)
    return msg


async def send_presence(online=True):
    presence = Presence.AVAILABLE if online else Presence.UNAVAILABLE
    return await bot.client.send_presence(presence)


DELIMITERS = {
    types.MessageEntityBold: ("*", "*"),
    types.MessageEntityItalic: ("_", "_"),
    types.MessageEntityStrike: ("~", "~"),
    types.MessageEntityCode: ("`", "`"),
    # Added for multi-line code support
    types.MessageEntityPre: ("```", "```"),
    types.MessageEntityBlockquote: ("> ", ""),
}


def whatsapp_unparse(raw_text, entities):
    # Convert to surrogate text for offset safety
    text = add_surrogate(raw_text)
    entities = list(entities)  # Make mutable copy

    # Process hyperlinks first (reverse order to handle offsets)
    text_url_entities = [
        e for e in entities if isinstance(e, types.MessageEntityTextUrl)
    ]
    text_url_entities.sort(key=lambda e: e.offset, reverse=True)

    # Separate other entities
    other_entities = [
        e for e in entities if not isinstance(e, types.MessageEntityTextUrl)
    ]

    # Process each hyperlink entity
    for entity in text_url_entities:
        start = entity.offset
        end = start + entity.length

        # Extract display text and create replacement
        display_text = del_surrogate(text[start:end])
        replacement = add_surrogate(f"{display_text}: {entity.url}")
        replacement_length = len(replacement)

        # Replace text segment
        text = text[:start] + replacement + text[end:]
        length_diff = replacement_length - (end - start)

        # Adjust offsets of subsequent entities
        for other in other_entities:
            if other.offset >= end:
                other.offset += length_diff
            # Remove entities overlapping with replaced segment
            elif other.offset + other.length > start and other.offset < end:
                other.length = 0  # Mark for removal

        # Remove entities marked for deletion
        other_entities = [e for e in other_entities if e.length > 0]

    # Define allowed surrounding characters
    ALLOWED_BEFORE = set(" \t\n.,!?()")
    ALLOWED_AFTER = set(" \t\n.,!?()")

    # Process formatting entities with boundary trimming
    insert_at = []
    for i, entity in enumerate(other_entities):
        start = entity.offset
        end = start + entity.length
        delimiter = DELIMITERS.get(type(entity))

        if not delimiter:
            continue

        # Skip empty entities
        if start >= end:
            continue

        # Skip formatting entities that span multiple lines
        entity_text = del_surrogate(text[start:end])
        if (
            type(entity)
            in {
                types.MessageEntityBold,
                types.MessageEntityItalic,
                types.MessageEntityStrike,
                types.MessageEntityCode,
            }
            and "\n" in entity_text
        ):
            continue  # Drop multi-line formatting entities

        # Check surrounding characters for non-blockquote entities
        if not isinstance(entity, type(entity)) != types.MessageEntityPre:
            # Check character before the entity
            if start > 0 and text[start - 1] not in ALLOWED_BEFORE:
                continue  # Skip this entity
            # Check character after the entity
            if end < len(text) and text[end] not in ALLOWED_AFTER:
                continue  # Skip this entity

        # Trim whitespace for formatting entities (except code/pre)
        if type(entity) in {
            types.MessageEntityBold,
            types.MessageEntityItalic,
            types.MessageEntityStrike,
        }:
            segment = text[start:end]

            # Trim leading whitespace
            ltrim = 0
            while ltrim < len(segment) and segment[ltrim].isspace():
                ltrim += 1

            # Trim trailing whitespace
            rtrim = 0
            while rtrim < len(segment) and segment[-1 - rtrim].isspace():
                rtrim += 1

            if ltrim + rtrim >= len(segment):
                continue  # Skip all-whitespace entities

            start += ltrim
            end -= rtrim

        # Add delimiters to insertion list
        open_marker, close_marker = delimiter
        insert_at.append((start, i, open_marker))
        insert_at.append((end, -i, close_marker))

    # Sort insertions by position and priority
    insert_at.sort(key=lambda x: (x[0], x[1]))

    # Apply insertions in reverse order
    last_quote_end = None
    while insert_at:
        pos, _, marker = insert_at.pop()

        # Handle blockquote formatting
        if marker == "":
            last_quote_end = pos
        elif marker == "> " and last_quote_end:
            # Format blockquote content
            segment = text[pos:last_quote_end]
            segment = re.sub(r"\n\n+", "\n", segment)  # Compress newlines
            segment = "> " + segment.replace("\n", "\n> ")
            text = text[:pos] + segment + text[last_quote_end:]
            last_quote_end = None
            continue
        else:
            # Insert regular marker
            text = text[:pos] + marker + text[pos:]

    return del_surrogate(text)


async def get_bridge_rheader_wa(event, client):
    is_user = True
    if isinstance(event.actor, PeerUser):
        user_id = event.actor.user_id
    else:
        user_id = int(f"-100{event.actor.channel_id}")
        is_user = False
    user = await client.get_entity(user_id)
    name = f"{
            user.first_name} {
            user.last_name if user.last_name else ''}" if is_user else user.title
    username = f"@{user.username}, " if user.username else ""
    user_id = f"@:{user.id}" if is_user else ""
    text = (
        f"> *From:* _*{name.strip()}*_{'' if is_user else ' _[Channel]_'}\n"
        f"> *Tag:* {username}{user_id}"
    ).strip(", ")
    text += "\n\n"

    return text


def get_bridge_header_wa(event):
    forwarder = None
    is_user = True
    if (user := event.sender) and isinstance(user, User):
        name = f"{user.first_name} {user.last_name if user.last_name else ''}"
    elif user or (user := event.chat):
        name = user.title
        is_user = False

    username = f"@{user.username}, " if user.username else ""
    user_id = f"@:{user.id}" if is_user else ""
    text = (
        f"> *From:* _*{name.strip()}*_{'' if is_user else ' _[Channel]_'}\n"
        f"> *Tag:* {username}{user_id}"
    ).strip(", ")
    if fi := event.forward:
        forwarder = (fi.chat.title if fi.chat else f"{
                fi.sender.first_name} {
                fi.sender.last_name if fi.sender.last_name else ''}").strip()
    if forwarder:
        text += f"\n\nForwarded from\n↪ *{forwarder}*"
    text += "\n\n"

    if entities_has_spoiler(event.entities):
        text += f"⚠️ *Spoiler Warning* {force_read_more}\n\n"

    return text


def add_bridge_header_tg(text, sender):
    header = f"> **From:** __**{sender.name}**__\n" f"> **Tag:** @:{sender.hid}\n"
    return header + "\n" + (text or "")


def get_subscription_header(event):
    forwarder = None
    text = f"> *From:* {event.chat.title}\n> *CHAT ID:* {event.chat_id}"
    if fi := event.forward:
        forwarder = (fi.chat.title if fi.chat else f"{
                fi.sender.first_name} {
                fi.sender.last_name if fi.sender.last_name else ''}").strip()
    if forwarder:
        text += f"\n\nForwarded from\n↪ *{forwarder}*"
    text += "\n\n"
    if entities_has_spoiler(event.entities):
        text += f"⚠️ *Spoiler Warning* {force_read_more}\n\n"
    return text


def conv_tgmd_to_wamd(text, entities):
    if not (text and entities):
        return text
    # entities = [en for en in entities if type(en) in WA_FORMAT_DELIMITERS.values()]
    return whatsapp_unparse(text, entities)


async def clean_reply(event, reply, func, *args, **kwargs):
    clas = reply if reply else event
    func = getattr(clas, func)
    pfunc = partial(func, *args, **kwargs)
    return await pfunc()


class ThrowingArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentParserError(message)


def line_split(line):
    return [t.strip("\"'") for t in re.findall(r'[^\s"]+|"[^"]*"', line)]


def get_args(*args, to_parse: str, get_unknown=False):
    parser = ThrowingArgumentParser(
        description="parse command flags", exit_on_error=False, add_help=False
    )
    for arg in args:
        if isinstance(arg, list):
            parser.add_argument(arg[0], action=arg[1], required=False)
        else:
            parser.add_argument(arg, type=str, required=False)
    flag, unknowns = parser.parse_known_args(line_split(to_parse))
    if get_unknown:
        unknown = " ".join(map(str, unknowns))
        return flag, unknown
    return flag


def process_line(line):
    if not line:
        return line

    whitespace = " \t"
    formatting_chars = ["*", "_", "~"]
    stacks = {char: [] for char in formatting_chars}
    paired_indices = set()

    for i, char in enumerate(line):
        if char not in formatting_chars:
            continue

        is_opening = False
        is_closing = False

        # Check opening conditions
        if i == 0:
            if i < len(line) - 1 and line[i + 1] not in whitespace:
                is_opening = True
        else:
            prev_char = line[i - 1]
            if (
                prev_char in whitespace
                or prev_char in formatting_chars
                or not prev_char.isalnum()
            ):
                if i < len(line) - 1 and line[i + 1] not in whitespace:
                    is_opening = True

        # Check closing conditions
        if i == len(line) - 1:
            if i > 0 and line[i - 1] not in whitespace:
                is_closing = True
        else:
            next_char = line[i + 1]
            if (
                next_char in whitespace
                or next_char in formatting_chars
                or not next_char.isalnum()
            ):
                if i > 0 and line[i - 1] not in whitespace:
                    is_closing = True

        if char in formatting_chars:
            if is_closing and stacks[char]:
                open_index = stacks[char].pop()
                substr = line[open_index + 1 : i]
                if any(c not in whitespace for c in substr):
                    paired_indices.add(open_index)
                    paired_indices.add(i)
            elif is_opening:
                stacks[char].append(i)

    new_line_parts = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] in formatting_chars and i in paired_indices:
            new_line_parts.append(line[i] * 2)
            i += 1
        elif line[i] in formatting_chars:
            j = i
            while j < n and line[j] == line[i] and (j not in paired_indices):
                j += 1
            run = j - i
            for k in range(run):
                new_line_parts.append(line[i])
                if k < run - 1:
                    new_line_parts.append(" ")
            i = j
        else:
            new_line_parts.append(line[i])
            i += 1

    return "".join(new_line_parts)


def whatsapp_md_to_telegram_md(message):
    lines = message.split("\n")
    in_code_block = False
    output_lines = []

    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith("```") and not in_code_block:
            in_code_block = True
            output_lines.append(line)
        elif in_code_block and stripped_line.startswith("```"):
            in_code_block = False
            output_lines.append(line)
        elif in_code_block:
            output_lines.append(line)
        else:
            processed_line = process_line(line)
            output_lines.append(processed_line)

    return "\n".join(output_lines)
