import asyncio

from bridge_bot import jid
from bridge_bot.config import bot, conf

from .db_utils import save2db2
from .log_utils import logger
from .msg_utils import cleanhtml


def process_submission(submission):
    caption = ""
    image = None
    if (
        hasattr(submission, "preview")
        and (preview := submission.preview)
        and (prev_img := preview.get("images"))
    ):
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
        caption += f"\n{cleanhtml(submission.selftext_html).rstrip('\n')}"
    caption += f"\n\nhttps://www.reddit.com{submission.permalink}"
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
            await submission.load()
            procd = process_submission(submission)
            funcs = [forward_submission(procd, chat) for chat in chats]
            await asyncio.gather(*funcs)
            await asyncio.sleep(1)
    except Exception:
        await logger(Exception)


async def fetch_latest_for_subreddit(sub_name, sub_info):
    submissions = []
    submission_ids = []
    try:
        subreddit = await bot.reddit.subreddit(sub_name, fetch=True)
        last_ids = sub_info["last_ids"]
        async for submission in subreddit.new(limit=50):
            if (sub_id := submission.id) not in last_ids:
                submissions.append(submission)
                submission_ids.append(sub_id)
                continue
            break
        if submissions:
            last_ids.extend(reversed(submission_ids))
            if len(submissions) > 50:
                submissions = []
                await logger(
                    e=f"Anti-spam pretention activated for {sub_name}!, Previous submissions would be dropped",
                    warning=True,
                )
    except Exception:
        await logger(Exception)
    return submissions


async def auto_fetch_reddit_posts():
    subscribed = bot.group_dict.setdefault("subscribed_subreddits", {})
    while bot.reddit:
        if not subscribed:
            await asyncio.sleep(60)
            continue
        updated = False
        for sub in subscribed.keys():
            if not (sub_info := subscribed[sub])["chats"]:
                continue
            submissions = await fetch_latest_for_subreddit(
                sub,
                sub_info,
            )
            if not submissions:
                continue
            await forward_submissions(submissions, sub_info["chats"])
            updated = True
        if updated:
            await save2db2(bot.group_dict, "groups")
        await asyncio.sleep(conf.REDDIT_SLEEP)
