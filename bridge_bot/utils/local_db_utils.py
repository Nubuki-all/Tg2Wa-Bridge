import pickle

from bridge_bot import bot, local_gcdb

from .os_utils import file_exists


def load_local_db():
    if file_exists(local_gcdb):
        with open(local_gcdb, "rb") as file:
            local_dict = pickle.load(file)
        bot.group_dict.update(local_dict)


def save2db_lcl2(db):
    if db == "groups":
        with open(local_gcdb, "wb") as file:
            pickle.dump(bot.group_dict, file)
