CREATE TABLE IF NOT EXISTS polls (
	poll_id serial PRIMARY KEY,
	question varchar NOT NULL,
	status integer NOT NULL CHECK(status IN (0, 1, 2)), -- 0: inactive, 1: active, 2: closed
	display bool NOT NULL,
	anonymous bool NOT NULL,
	multiple_choice bool NOT NULL);

CREATE TABLE IF NOT EXISTS poll_choices (
	poll_choice_id serial PRIMARY KEY,
	poll_id integer NOT NULL,
	choice varchar NOT NULL,
	marker varchar NOT NULL,
	UNIQUE(poll_id, choice));

CREATE TABLE IF NOT EXISTS poll_anonym_active_votes (
	poll_choice_id integer NOT NULL,
	poll_id integer NOT NULL,
	team_code varchar NOT NULL,
	UNIQUE(poll_choice_id, team_code));

CREATE TABLE IF NOT EXISTS poll_anonym_votes (
	poll_choice_id integer NOT NULL,
	poll_id integer NOT NULL,
	count integer NOT NULL);

CREATE TABLE IF NOT EXISTS poll_votes (
	poll_choice_id integer NOT NULL,
	poll_id integer NOT NULL,
	team_code varchar NOT NULL,
	voted_by varchar NOT NULL,
	voted_at timestamp NOT NULL DEFAULT current_timestamp,
	UNIQUE(poll_choice_id, team_code));

CREATE TABLE IF NOT EXISTS listening_threads (
	obj_room_id varchar NOT NULL,
	sc_room_id varchar NOT NULL,
	obj_thread_id varchar NOT NULL,
	sc_thread_id varchar NOT NULL,
	UNIQUE(obj_room_id, sc_room_id, obj_thread_id, sc_thread_id));
