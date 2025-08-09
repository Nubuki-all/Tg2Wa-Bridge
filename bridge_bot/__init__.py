import asyncio
import logging
import os
import re
import shlex
import subprocess
import sys
import time
import traceback
from logging import DEBUG, INFO, basicConfig, getLogger, warning
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

from colorlog import ColoredFormatter
from neonize.aioze.client import NewAClient
from neonize.events import (
    CallOfferEv,
    ConnectedEv,
    DisconnectedEv,
    LoggedOutEv,
    MessageEv,
    PairStatusEv,
    ReceiptEv,
    event,
)
from neonize.proto.Neonize_pb2 import JID
from neonize.proto.Neonize_pb2 import Message as base_msg
from neonize.proto.Neonize_pb2 import MessageInfo as base_msg_info
from neonize.proto.Neonize_pb2 import MessageSource as base_msg_source
from neonize.proto.Neonize_pb2 import SendResponse
from neonize.proto.waCompanionReg.WAWebProtobufsCompanionReg_pb2 import DeviceProps
from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
    ContextInfo,
    ExtendedTextMessage,
    Message,
    StickerPackMessage,
)
from neonize.utils import jid, log
from telethon import Button, TelegramClient, errors, events, functions, types
from telethon.sessions import StringSession

from .config import bot, conf

heavy_proc_lock = asyncio.Lock()

local_gcdb = ".local_groups.pkl"
log_file_name = "logs.txt"
sudo_btn_lock = asyncio.Lock()
uptime = time.time()
version_file = "version.txt"

if os.path.exists(log_file_name):
    with open(log_file_name, "r+") as f_d:
        f_d.truncate(0)

formatter = ColoredFormatter(
    "%(asctime)s - %(log_color)s%(name)s - %(levelname)s - %(message)s%(reset)s",
    datefmt="%d-%b-%y %H:%M:%S",
    log_colors={
        "INFO": "cyan",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    },
)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    force=True,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        RotatingFileHandler(log_file_name, maxBytes=2097152000, backupCount=10),
        # logging.StreamHandler(),
        stream_handler,
    ],
)
logging.getLogger("neonize").setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.INFO)

LOGS = logging.getLogger(__name__)

no_verbose = [
    "apscheduler.executors.default",
    "telethon.client.users",
    "telethon.network.mtprotosender",
    "httpx",
]
if not conf.DEBUG:
    log.setLevel(logging.INFO)
    for item in no_verbose:
        logging.getLogger(item).setLevel(logging.WARNING)

bot.repo_branch = (
    subprocess.check_output(["git rev-parse --abbrev-ref HEAD"], shell=True)
    .decode()
    .strip()
    if os.path.exists(".git")
    else None
)
if os.path.exists(version_file):
    with open(version_file, "r") as file:
        bot.version = file.read().strip()

if sys.version_info < (3, 10):
    LOGS.critical("Please use Python 3.10+")
    exit(1)

LOGS.info("Starting...")

try:
    bot.tg_client = TelegramClient(
        "Bridge",
        conf.API_ID,
        conf.API_HASH,
        flood_sleep_threshold=conf.FS_THRESHOLD,
    )
    bot.tg_client2 = (
        TelegramClient(
            StringSession(conf.SS_STRING),
            conf.API_ID,
            conf.API_HASH,
            flood_sleep_threshold=conf.FS_THRESHOLD,
        )
        if conf.SS_STRING
        else None
    )
    bot.client = NewAClient(
        conf.WA_DB,
        props=DeviceProps(os="WA_BRIDGE", platformType=DeviceProps.CHROME),
    )
except Exception:
    LOGS.critical(traceback.format_exc())
    LOGS.info("quiting…")
    exit()
