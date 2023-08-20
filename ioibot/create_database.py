import sqlite3


def create_database():
    """Creates the databases for the voiting and the objection threads"""

    with sqlite3.connect("/data/ioibot.db") as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS polls(
                poll_id integer PRIMARY KEY AUTOINCREMENT,
                question varchar NOT NULL,
                status integer NOT NULL CHECK(status IN (0, 1, 2)), -- 0: inactive, 1: active, 2: closed
                anonymous bit NOT NULL,
                multiple_choice bit NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS poll_choices(
                poll_choice_id integer PRIMARY KEY AUTOINCREMENT,
                poll_id integer NOT NULL,
                choice varchar NOT NULL,
                marker varchar NOT NULL,
                UNIQUE(poll_id, choice),
                FOREIGN KEY (poll_id) REFERENCES polls(poll_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS poll_anonym_active_votes(
                poll_choice_id integer NOT NULL PRIMARY KEY,
                team_code varchar NOT NULL,
                UNIQUE(poll_choice_id, team_code),
                FOREIGN KEY (poll_choice_id) REFERENCES poll_choices(poll_choice_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS poll_anonym_votes(
                poll_choice_id integer NOT NULL,
                count integer NOT NULL,
                FOREIGN KEY (poll_choice_id) REFERENCES poll_choices(poll_choice_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS poll_votes(
                poll_choice_id integer NOT NULL,
                poll_id integer NOT NULL,
                team_code varchar NOT NULL,
                voted_by varchar NOT NULL,
                voted_at datetime NOT NULL,
                UNIQUE(poll_choice_id, team_code),
                FOREIGN KEY (poll_choice_id) REFERENCES poll_choices(poll_choice_id)
                FOREIGN KEY (poll_id) REFERENCES polls(poll_id)
                FOREIGN KEY (poll_choice_id, poll_id) REFERENCES poll_choices (poll_choice_id, poll_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS listening_threads(
                obj_room_id varchar NOT NULL,
                sc_room_id varchar NOT NULL,
                obj_thread_id varchar NOT NULL,
                sc_thread_id varchar NOT NULL,
                UNIQUE(obj_room_id, sc_room_id, obj_thread_id, sc_thread_id)
            )
            """
        )

        conn.commit()
