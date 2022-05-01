import sqlite3

conn = sqlite3.connect('ioibot.db')
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

conn.commit()