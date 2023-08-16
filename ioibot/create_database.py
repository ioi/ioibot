import sqlite3

def create_database():
	conn = sqlite3.connect('/data/ioibot.db')
	c = conn.cursor()

	c.execute(
		'''
		CREATE TABLE IF NOT EXISTS polls(
			poll_id integer PRIMARY KEY AUTOINCREMENT,
			question varchar NOT NULL,
			choices varchar NOT NULL,
			active bit NOT NULL
		)
		'''
	)

	c.execute(
		'''
		CREATE TABLE IF NOT EXISTS votes(
			poll_id integer NOT NULL,
			team_code varchar NOT NULL,
			choice varchar NOT NULL,
			voted_by varchar NOT NULL,
			voted_at datetime NOT NULL,
			UNIQUE(poll_id, team_code)
		)
		'''
	)


	c.execute(
		'''
		CREATE TABLE IF NOT EXISTS listening_threads(
			obj_room_id varchar NOT NULL,
			sc_room_id varchar NOT NULL,
			obj_thread_id varchar NOT NULL,
			sc_thread_id varchar NOT NULL,
			UNIQUE(obj_room_id, sc_room_id, obj_thread_id, sc_thread_id)
		)
		'''
	)
	
	conn.commit()
