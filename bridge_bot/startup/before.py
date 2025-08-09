import pickle
from importlib.metadata import version

from pymongo import MongoClient

from bridge_bot import LOGS, bot, conf, os, sys, version_file
from bridge_bot.utils.local_db_utils import load_local_db
from bridge_bot.utils.os_utils import file_exists

LOGS.info("=" * 30)
LOGS.info(f"Python version: {sys.version.split()[0]}")
LOGS.info(f"Neonize version: {version('neonize')}")
LOGS.info(f"Telethon version: {version('telethon')}")

vmsg = f"Warning: {version_file} is missing!"
if file_exists(version_file):
    with open(version_file, "r") as file:
        ver = file.read().strip()
    vmsg = f"Bot version: {ver}"

LOGS.info(f"Branch: {bot.repo_branch or 'Unknown!'}")
LOGS.info(vmsg)

if os.path.isdir("/one"):
    bot.docker_deployed = True
    LOGS.info("Docker: Yes")

LOGS.info("=" * 30)


def load_db(_db, _key, var, var_type=None):
    queries = _db.find({"_id": conf.PH_NUMBER or conf.DB_ID})
    raw = None
    for query in queries:
        raw = query.get(_key)

    if not raw:
        return
    out = pickle.loads(raw)
    if not out:
        return

    if var_type == "list":
        for item in out.split():
            if item in conf.OWNER.split():
                continue
            if item not in var:
                var.append(item)
    elif var_type == "dict":
        var.update(out)


if conf.DATABASE_URL:
    cluster = MongoClient(conf.DATABASE_URL)
    db = cluster[conf.DBNAME]
    userdb = db["users"]

    load_db(userdb, "groups", bot.group_dict, "dict")


else:
    userdb = None

    load_local_db()
