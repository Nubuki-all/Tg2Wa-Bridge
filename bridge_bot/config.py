import traceback

from decouple import config


class Config:
    def __init__(self):
        try:
            self.ALWAYS_DEPLOY_LATEST = config(
                "ALWAYS_DEPLOY_LATEST", default=False, cast=bool
            )
            self.API_ID = config("API_ID")
            self.API_HASH = config("API_HASH")
            self.BOT_TOKEN = config("BOT_TOKEN")
            self.PH_NUMBER = config("PH_NUMBER", default="")
            self.SS_STRING = config("SESSION_STRING", default="")
            self.CMD_PREFIX = config("CMD_PREFIX", default="$")
            self.DATABASE_URL = config("DATABASE_URL", default=None)
            self.DB_ID = config("DB_ID", default="0000")
            self.DBNAME = config("DBNAME", default="WA2TG_BRIDGE")
            self.DEBUG = config("DEBUG", default=False, cast=bool)
            self.DEV = config("DEV", default="")
            self.DYNO = config("DYNO", default=None)
            self.FS_THRESHOLD = config("FLOOD_SLEEP_THRESHOLD", default=600, cast=int)
            self.R_CLI_ID = config("REDDIT_CLIENT_ID", default="")
            self.R_CLI_SECRET = config("REDDIT_CLIENT_SECRET", default="")
            self.REDDIT_SLEEP = config("REDDIT_SLEEP", default=240, cast=int)
            self.R_USER_NAME = config("REDDIT_USERNAME", default="")
            self.UB_REC_EVENTS = config("UB_REC_EVENTS", default=False, cast=bool)
            self.LOG_GROUP = config("LOG_GROUP", default="")
            self.OWNER = config("OWNER")
            self.WA_DB = config("WA_DB", default="db.sqlite3")
            self.WORKERS = config("WORKERS", default=20, cast=int)
        except Exception:
            print("Environment vars Missing; or")
            print("Something went wrong:")
            print(traceback.format_exc())
            exit()


class Runtime_Config:
    def __init__(self):
        self.client = None
        self.docker_deployed = False
        self.group_dict = {}
        self.is_connected = False
        self.max_message_length = 4096
        self.repo_branch = None
        self.reddit = None
        self.requests = None
        self.tg_client = None
        self.tg_client2 = None
        self.tg_client_ids = []
        self.add_handler = None
        self.register = None
        self.unregister = None
        self.version = None


conf = Config()
bot = Runtime_Config()
