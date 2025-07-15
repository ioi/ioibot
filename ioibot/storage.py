import logging
import sqlite3

import pandas as pd

from ioibot.config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class Storage:
    def __init__(self, config: Config):
        self.vconn = sqlite3.connect('ioibot.db', isolation_level=None)
        self.config = config
        self.contestants = pd.read_csv(config.contestant_url)
        self.contestants.sort_values('ContestantCode')
        self.testing_acc = pd.read_csv(config.testing_acc_url)
        self.testing_acc.sort_values('ContestantCode')
        self.tokens = pd.read_csv(config.token_url)
        self.reload_csv()

    def reload_csv(self):
        self.teams = pd.read_csv(self.config.team_url)
        self.leaders = pd.read_csv(self.config.leader_url)
        self.translation_acc = pd.read_csv(self.config.translation_acc_url)
        self.objection_rooms = pd.read_csv(self.config.objection_room_url)
