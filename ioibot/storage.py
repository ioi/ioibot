import dropbox
import logging
import pandas as pd
from typing import Any, Dict

# The latest migration version of the database.
#
# Database migrations are applied starting from the number specified in the database's
# `migration_version` table + 1 (or from 0 if this table does not yet exist) up until
# the version specified here.
#
# When a migration is performed, the `migration_version` table should be incremented.
latest_migration_version = 0

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from ioibot.config import Config

class Storage:
    def __init__(self, database_config: Dict[str, str], config: Config):
        """Setup the database.

        Runs an initial setup or migrations depending on whether a database file has already
        been created.

        Args:
            database_config: a dictionary containing the following keys:
                * type: A string, one of "sqlite" or "postgres".
                * connection_string: A string, featuring a connection string that
                    be fed to each respective db library's `connect` method.
        """
        self.conn = self._get_database_connection(
            database_config["type"], database_config["connection_string"]
        )
        self.vconn = self._get_database_connection(
            database_config["type"], "ioibot.db"
        )

        self.cursor = self.conn.cursor()
        self.db_type = database_config["type"]
        self.config = config
        self.teams = pd.read_csv(config.team_url)
        self.leaders = pd.read_csv(config.leader_url)
        self.contestants = pd.read_csv(config.contestant_url)
        self.contestants.sort_values('ContestantCode')
        self.testing_acc = pd.read_csv(config.testing_acc_url)
        self.testing_acc.sort_values('ContestantCode')
        self.translation_acc = pd.read_csv(config.translation_acc_url)
        self.objection_rooms = pd.read_csv(config.objection_room_url)
        self.tokens = pd.read_csv(config.token_url)
        
        # dropbox configuration
        access_token = config.db_access_token
        refresh_token = config.db_refresh_token
        app_key = config.db_app_key
        app_secret = config.db_app_secret

        self.dropbox_url = pd.read_csv(config.dropbox_url)
        self.dbx = dropbox.Dropbox(
                        access_token, 
                        oauth2_refresh_token = refresh_token,
                        app_key = app_key, 
                        app_secret = app_secret
                   )

        # Try to check the current migration version
        migration_level = 0
        try:
            self._execute("SELECT version FROM migration_version")
            row = self.cursor.fetchone()
            migration_level = row[0]
        except Exception:
            self._initial_setup()
        finally:
            if migration_level < latest_migration_version:
                self._run_migrations(migration_level)

        logger.info(f"Database initialization of type '{self.db_type}' complete")

    def reload_csv(self):
        self.teams = pd.read_csv(self.config.team_url)
        self.leaders = pd.read_csv(self.config.leader_url)
        self.translation_acc = pd.read_csv(self.config.translation_acc_url)
        self.objection_rooms = pd.read_csv(self.config.objection_room_url)

    def _get_database_connection(
        self, database_type: str, connection_string: str
    ) -> Any:
        """Creates and returns a connection to the database"""
        if database_type == "sqlite":
            import sqlite3

            # Initialize a connection to the database, with autocommit on
            return sqlite3.connect(connection_string, isolation_level=None)
        elif database_type == "postgres":
            import psycopg2

            conn = psycopg2.connect(connection_string)

            # Autocommit on
            conn.set_isolation_level(0)

            return conn

    def _initial_setup(self) -> None:
        """Initial setup of the database"""
        logger.info("Performing initial database setup...")

        # Set up the migration_version table
        self._execute(
            """
            CREATE TABLE migration_version (
                version INTEGER PRIMARY KEY
            )
        """
        )

        # Initially set the migration version to 0
        self._execute(
            """
            INSERT INTO migration_version (
                version
            ) VALUES (?)
        """,
            (0,),
        )

        # Set up any other necessary database tables here

        logger.info("Database setup complete")

    def _run_migrations(self, current_migration_version: int) -> None:
        """Execute database migrations. Migrates the database to the
        `latest_migration_version`.

        Args:
            current_migration_version: The migration version that the database is
                currently at.
        """
        logger.debug("Checking for necessary database migrations...")

        # if current_migration_version < 1:
        #    logger.info("Migrating the database from v0 to v1...")
        #
        #    # Add new table, delete old ones, etc.
        #
        #    # Update the stored migration version
        #    self._execute("UPDATE migration_version SET version = 1")
        #
        #    logger.info("Database migrated to v1")

    def _execute(self, *args) -> None:
        """A wrapper around cursor.execute that transforms placeholder ?'s to %s for postgres.

        This allows for the support of queries that are compatible with both postgres and sqlite.

        Args:
            args: Arguments passed to cursor.execute.
        """
        if self.db_type == "postgres":
            self.cursor.execute(args[0].replace("?", "%s"), *args[1:])
        else:
            self.cursor.execute(*args)
