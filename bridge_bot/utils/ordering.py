"""Keeps bridged chats in order.

Both Telegram and WhatsApp start every update in its own task, so without
this a small text can be bridged before a large file sent before it, and an
edit, reply or reaction can look for a message that isn't bridged yet.

- New messages in a chat are bridged one at a time, in the order they came in.
- Replies skip that queue and wait only for the message they reply to,
  which in turn waits for its own target, however deep the chain goes.
- Edits, deletes and reactions wait only for the message they target, and
  updates to the same message run in arrival order.
"""

import asyncio
from collections import defaultdict

from telethon import events
from telethon.tl import types

from bridge_bot import bot, conf

# Give up waiting after this long, so one stuck update can't stall a chat
# forever.
MAX_TURN = 1800

_locks = {}
_lock_users = defaultdict(int)
# Release callbacks of the turns held by each task.
_turns = {}
# (side, chat_id, msg_id) -> set once that new message has been bridged.
_pending = {}


async def hold_turn(key, pending=None):
    """Waits for earlier holders of key, then holds it until end_chat_turn()
    is called or the current task is done.

    Must be awaited before the task's first other await, so the queue order
    matches arrival order (asyncio.Lock wakes waiters in FIFO order).
    With pending, a (side, chat_id, msg_id) key, that message counts as not
    yet bridged until the turn ends.
    """
    done = asyncio.Event()
    if pending:
        _pending[pending] = done
    lock = _locks.setdefault(key, asyncio.Lock())
    _lock_users[key] += 1
    released = False
    timer = None

    def release(*_):
        nonlocal released
        if released:
            return
        released = True
        if timer:
            timer.cancel()
        if lock.locked():
            lock.release()
        _lock_users[key] -= 1
        if not _lock_users[key]:
            del _lock_users[key]
            _locks.pop(key, None)
        if pending and _pending.get(pending) is done:
            del _pending[pending]
        done.set()

    try:
        await lock.acquire()
    except BaseException:
        # Cancelled while queued: we never held the lock.
        released = True
        _lock_users[key] -= 1
        if not _lock_users[key]:
            del _lock_users[key]
            _locks.pop(key, None)
        if pending and _pending.get(pending) is done:
            del _pending[pending]
        done.set()
        raise

    task = asyncio.current_task()
    timer = asyncio.get_running_loop().call_later(MAX_TURN, release)
    task.add_done_callback(release)
    task.add_done_callback(lambda _: _turns.pop(task, None))
    _turns.setdefault(task, []).append(release)


async def wait_for_messages(side, chat_id, msg_ids):
    """Waits until the given messages, if still pending, are bridged.

    chat_id may be None (Telegram deletes outside channels); then a pending
    message with a matching id in any chat counts.
    """
    waits = [
        done.wait()
        for (s, c, m), done in list(_pending.items())
        if s == side and m in msg_ids and (chat_id is None or c == chat_id)
    ]
    if waits:
        try:
            await asyncio.wait_for(asyncio.gather(*waits), MAX_TURN)
        except asyncio.TimeoutError:
            pass


async def hold_new_message_turn(side, chat_id, msg_id, reply_to=None):
    """Orders a new message: behind the chat's earlier new messages or,
    for a reply, behind only the message it replies to."""
    pending = (side, chat_id, msg_id)
    if reply_to is None:
        await hold_turn((side, chat_id), pending)
        return
    # A turn of its own, so the reply counts as pending until it's bridged.
    await hold_turn((side, chat_id, "reply", msg_id), pending)
    await wait_for_messages(side, chat_id, [reply_to])


async def hold_target_turn(side, chat_id, msg_ids):
    """Waits until the targeted messages are bridged, and for earlier
    edits, deletes or reactions to them."""
    for msg_id in sorted(set(msg_ids)):
        await hold_turn((side, chat_id, "target", msg_id))
    await wait_for_messages(side, chat_id, msg_ids)


def end_chat_turn():
    """Releases the turns held by the current task before it finishes."""
    for release in _turns.pop(asyncio.current_task(), []):
        release()


def tg_reply_target(event):
    """The id of the message a Telegram message replies to in the same chat."""
    reply = event.reply_to
    # Story replies and replies to other chats have nothing to wait for here.
    if not isinstance(reply, types.MessageReplyHeader) or reply.reply_to_peer_id:
        return None
    # In forum topics every message points at the topic's first message;
    # it's only a real reply when the topic is given separately.
    if reply.forum_topic and not reply.reply_to_top_id:
        return None
    return reply.reply_to_msg_id


def order_clients():
    bridge_client = (
        bot.tg_client2 if (bot.tg_client2 and conf.UB_REC_EVENTS) else bot.tg_client
    )
    return {bridge_client, bot.tg_client2 or bot.tg_client}


def ordered_chat(chat_id):
    return chat_id in bot.group_dict.setdefault(
        "tg_bridges", {}
    ) or chat_id in bot.group_dict.setdefault("subscribed_channels", {})


def add_order_handlers():
    """Registers the Telegram handlers that take a turn.

    Telethon runs an update's handlers in registration order inside one task.
    Call this before any other Telegram handler is added, so the turn is
    taken first, and call add_order_end_handlers() right after the bridge
    handlers, so commands that run after them don't hold up the chat.
    """

    async def new_message(event):
        await hold_new_message_turn(
            "tg", event.chat_id, event.id, tg_reply_target(event)
        )

    async def edited(event):
        await hold_target_turn("tg", event.chat_id, [event.id])

    async def deleted(event):
        await hold_target_turn("tg", event.chat_id, event.deleted_ids)

    for client in order_clients():
        client.add_event_handler(
            new_message, events.NewMessage(func=lambda e: ordered_chat(e.chat_id))
        )
        client.add_event_handler(
            edited, events.MessageEdited(func=lambda e: ordered_chat(e.chat_id))
        )
        # Deletes outside channels don't say which chat they're from.
        client.add_event_handler(
            deleted,
            events.MessageDeleted(
                func=lambda e: e.chat_id is None or ordered_chat(e.chat_id)
            ),
        )


def add_order_end_handlers():
    """Releases the turns once the bridge handlers are done."""

    async def end_turn(_):
        end_chat_turn()

    for client in order_clients():
        for builder in (events.NewMessage, events.MessageEdited, events.MessageDeleted):
            client.add_event_handler(end_turn, builder())
