import asyncio

from bridge_bot import jid
from bridge_bot.conf import bot, conf

from .bot_utils import sync_to_async
from .db_utils import save2db2
from .log_utils import log, logger
from .msg_utils import cleanhtml


def process_submission(submission):
    caption = ""
    image = None
    if (preview := submission.preview) and (prev_img := preview.images):
        image = prev_img[0].get("source", {}).get("url")
    if submission.over_18:
        caption += "*🔞 NSFW*\n"
    if submission.spoiler:
        caption += "⚠️ *Spoiler Warning*\n"
    if caption:
        caption += "\n"
    if submission.link_flair_text:
        caption += f"> *[{submission.link_flair_text}]*"
        caption += "\n"
    caption += f"*From:* _*{submission.subreddit_name_prefixed}*_"
    caption += f"\n*By:* _u/{submission.author.name}_"
    caption += f"\n\n*{submission.title}*"
    if submission.selftext_html:
        caption += f"\n{cleanhtml(submission.selftext_html)}"
    return image, caption, submission.over_18


async def forward_submission(data, chat):
    image, caption, nsfw = data
    if image:
        await bot.client.send_image(
            jid.build_jid(chat, "g.us"), image, caption, viewonce=nsfw
        )
    else:
        await bot.send_message(jid.build_jid(chat, "g.us"), caption)


async def forward_submissions(submissions, chats):
    try:
        for submission in submissions:
            procd = process_submission(submission)
            funcs = [forward_submission(procd, chat) for chat in chats]
            await asyncio.gather(*funcs)
            await asyncio.sleep(1)
    except Exception:
        await logger(Exception)


def fetch_latest_for_subreddit(sub_name, sub_info):
    submissions = []
    try:
        for submission in bot.reddit.subreddit(sub_name).new(limit=30):
            if submission.id != sub_info["last_id"]:
                submissions.append(submission)
                continue
            break
        else:
            sub_info["last_id"] = submissions[0].id
    except Exception:
        log(Exception)
    return submissions


async def auto_fetch_reddit_posts():
    while bot.reddit:
        subscribed = bot.group_dict.setdefault("subscribed_subreddits", {})
        if not subscribed_subs:
            await asyncio.sleep(60)
            continue
        updated = False
        for sub in subscribed.keys():
            submissions = await sync_to_async(
                fetch_latest_for_subreddit,
                sub,
                subscribed[sub],
            )
            if not submissions:
                continue
            await forward_submissions(submissions, subscribed[chats])
            updated = True
        if updated:
            await save2db2(bot.group_dict, "groups")
        await asyncio.sleep(conf.REDDIT_SLEEP)
