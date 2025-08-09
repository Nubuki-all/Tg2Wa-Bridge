import asyncio
import html
import io
import sys
import traceback

from telethon import events

from bridge_bot import bot, log_file_name
from bridge_bot.utils.bot_utils import split_text
from bridge_bot.utils.log_utils import logger
from bridge_bot.utils.msg_utils import (
    event_handler,
    get_args,
    user_is_dev,
    user_is_owner,
)
from bridge_bot.utils.os_utils import read_n_to_last_line, s_remove


async def get_logs_tg(event):
    if not user_is_owner(event.sender_id):
        return
    return await event_handler(event, get_logs)


async def get_logs(event, args, client):
    """
    Get bot logs in txt file or print as plain text
    Argument:
        -t Number of lines to print
        Otherwise receive as a file
    """
    if client and not user_is_owner(event.from_user.id):
        return
    try:
        if not args:
            (
                await event.reply_document(
                    document=log_file_name,
                    quote=True,
                    caption=log_file_name,
                )
                if client
                else await event.reply(file=log_file_name, force_document=True)
            )
            return
        arg = get_args("-t", to_parse=args)
        if arg.t and arg.t.isdigit() and (ind := int(arg.t)):
            msg = ""
            for i in reversed(range(1, ind)):
                msg += read_n_to_last_line(log_file_name, i)
                msg += "\n"
            msg = "Nothing Here.\nTry with a higher number" if not msg else msg
            md = "" if client else "```"
            pre_event = event
            for smsg in split_text(msg):
                smsg = f"\n{md}{smsg}{md}\n"
                pre_event = await pre_event.reply(smsg, link_preview=False)
                await asyncio.sleep(2)
        else:
            return await get_logs(event, None, client)

    except Exception:
        await logger(Exception)
        await event.reply("`An error occurred.`")


async def bash(event, cmd, client):
    """
    Run bash/system commands in bot
    Much care must be taken especially on Local deployment

    USAGE:
    Command requires executables as argument
    For example "/bash ls"
    """
    if not user_is_owner(event.from_user.id):
        if not user_is_dev(event.from_user.id):
            return
    process, e, o = await run_bash(cmd)
    OUTPUT = f"QUERY:\n__Command:__\n{cmd} \n__PID:__\n{
        process.pid}\n\nstderr: \n{e}\nOutput:\n{o}"
    if len(OUTPUT) > 4000:
        with io.BytesIO(str.encode(OUTPUT)) as out_file:
            await event.reply_document(
                document=out_file.getvalue(),
                file_name="exec.text",
                quote=True,
                caption=cmd,
            )
            await asyncio.sleep(3)
            return
    else:
        OUTPUT = f"```bash\n{cmd}```\n\n_PID:_\n{
            process.pid}\n\n```Stderr:\n{e}```\n\n```Output:\n{o}```\n"
        await event.reply(OUTPUT, link_preview=False)


async def bash_tg(event):
    async def bash(event, cmd, client):
        """
        Run bash/system commands in bot
        Much care must be taken especially on Local deployment

        USAGE:
        Command requires executables as argument
        For example "/bash ls"
        """
        if not user_is_owner(event.sender_id):
            if not user_is_dev(event.sender_id):
                return
        process, e, o = await run_bash(cmd)
        OUTPUT = f"QUERY:\n__Command:__\n{cmd} \n__PID:__\n{
            process.pid}\n\nstderr: \n{e}\nOutput:\n{o}"
        if len(OUTPUT) > 4000:
            with io.BytesIO(str.encode(OUTPUT)) as out_file:
                out_file.name = "exec.text"
                await event.client.send_file(
                    event.chat_id,
                    out_file,
                    force_document=True,
                    allow_cache=False,
                    caption=cmd,
                )
                return await event.delete()
        else:
            OUTPUT = f"<pre>\n<code class='language-bash'>{
                html.escape(cmd)}</code>\n</pre>\n<i>PID:</i>\n{
                process.pid}\n\n<pre>\n<code class='language-Stderr:'>{e}</code>\n</pre>\n<pre>\n<code class='language-Output:'>{
                html.escape(o)}</code>\n</pre>"
            await event.reply(OUTPUT, parse_mode="html")

    if not user_is_owner(event.sender_id):
        return
    try:
        return await event_handler(event, bash, require_args=True)
    except Exception:
        await logger(Exception)


async def run_bash(cmd):
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    e = stderr.decode()
    if not e:
        e = "No Error"
    o = stdout.decode()
    if not o:
        o = "Tip:\nIf you want to see the results of your code, I suggest printing them to stdout."
    return process, e, o


async def aexec(code, client, event):
    res = {}
    exec(
        f"async def __aexec(client, message, event): "
        + "".join(f"\n {l}" for l in code.split("\n")),
        globals(),
        res,
    )
    return await res["__aexec"](client, event, event)


async def eval_message(event, cmd, client):
    """
    Evaluate and execute code within bot.
    Global namespace has been cleaned so you'll need to manually import modules

    USAGE:
    Command requires code to execute as arguments.
    For example /peval print("Hello World!")
    Kindly refrain from adding whitelines and newlines between command and argument.
    """
    if not user_is_owner(event.from_user.id):
        if not user_is_dev(event.from_user.id):
            return
    status_message = await event.reply("Processing ...")
    evaluation = await run_eval(event, cmd, client)
    final_output = "```python\n{}```\n\n```Output:\n{}```\n".format(
        cmd, evaluation.strip()
    )
    if len(final_output) > bot.max_message_length:
        final_output = "Evaluated:\n{}\n\nOutput:\n{}".format(cmd, evaluation.strip())
        with open("eval.text", "w+", encoding="utf8") as out_file:
            out_file.write(str(final_output))
        await event.reply_document(
            document="eval.text",
            caption=cmd,
            quote=True,
        )
        s_remove("eval.text")
        await asyncio.sleep(3)
        await status_message.delete()
    else:
        await status_message.edit(final_output)


async def eval_tg(event):
    async def eval_message(event, cmd, client):
        """
        Evaluate and execute code within bot.
        Global namespace has been cleaned so you'll need to manually import modules

        USAGE:
        Command requires code to execute as arguments.
        For example /eval print("Hello World!")
        Kindly refrain from adding whitelines and newlines between command and argument.
        """
        if not user_is_owner(event.sender_id):
            if not user_is_dev(event.sender_id):
                return
        msg = await event.reply("Processing ...")
        evaluation = await run_eval(event, cmd, client)

        if len(evaluation) > 4000:
            final_output = "EVAL: {} \n\n OUTPUT: \n{} \n".format(cmd, evaluation)
            with io.BytesIO(str.encode(final_output)) as out_file:
                out_file.name = "eval.text"
                await event.client.send_file(
                    event.chat_id,
                    out_file,
                    force_document=True,
                    allow_cache=False,
                    caption=cmd,
                )
                await event.delete()
        else:
            final_output = "<pre>\n<code class='language-python'>{}</code>\n</pre>\n\n<pre>\n<code class='language-Output:'>{}</code>\n</pre>\n".format(
                html.escape(cmd), html.escape(evaluation)
            )
            await msg.edit(final_output, parse_mode="html")

    if not user_is_owner(event.sender_id):
        return
    try:
        return await event_handler(event, eval_message, require_args=True)
    except Exception:
        await logger(Exception)


async def run_eval(event, cmd, client):

    old_stderr = sys.stderr
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()
    redirected_error = sys.stderr = io.StringIO()
    stdout, stderr, exc = None, None, None

    try:
        await aexec(cmd, client, event)
    except Exception:
        exc = traceback.format_exc()

    stdout = redirected_output.getvalue()
    stderr = redirected_error.getvalue()
    sys.stdout = old_stdout
    sys.stderr = old_stderr

    evaluation = ""
    if exc:
        evaluation = exc
    elif stderr:
        evaluation = stderr
    elif stdout:
        evaluation = stdout
    else:
        evaluation = "Success"
    return evaluation


def add_dev_handlers():
    bot.add_handler(bash, "bash")
    bot.add_handler(eval_message, "eval")
    bot.add_handler(get_logs, "logs")
    bot.tg_client.add_event_handler(bash_tg, events.NewMessage(pattern="/bash"))
    bot.tg_client.add_event_handler(eval_tg, events.NewMessage(pattern="/eval"))
    bot.tg_client.add_event_handler(get_logs_tg, events.NewMessage(pattern="/logs"))
