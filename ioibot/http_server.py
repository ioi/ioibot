import base64
import logging
import os
import sqlite3

from aiohttp import web
from aiohttp_session import SimpleCookieStorage, get_session, setup
import bcrypt
from dotenv import load_dotenv
import pandas as pd
import yaml

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

load_dotenv()

uname = os.getenv('VOTING_USERNAME').strip()
passw_hash = bytes(os.getenv('VOTING_PASSWORD').strip(), "utf-8")

# Middleware function to perform Basic Authentication
async def basic_auth_middleware(app, handler):
    async def middleware(request):
        # Extract the Authorization header from the request
        auth_header = request.headers.get("Authorization")
        session = await get_session(request)

        if auth_header:
            try:
                auth_type, encoded_credentials = auth_header.split(" ")
                if auth_type.lower() == "basic":
                    decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
                    username, password = decoded_credentials.split(":")
                    username = username.strip()
                    password = password.strip()
                    password = bytes(password, "utf-8")
                    if username == uname and bcrypt.hashpw(password, passw_hash) == passw_hash:
                        logger.info(f"Authentication successful for {request.remote}")

                        session["authenticated"] = True
                        return await handler(request)

            except Exception as e:
                print(f"Authentication error: {e}")

        # Authentication failed or no credentials provided, check session for authentication
        if session.get("authenticated"):
            logger.info(f"Authentication successful for {request.remote}")

            return await handler(request)
        else:
            logger.info(f"Authentication failed for {request.remote}")

            # Authentication failed, return a 401 Unauthorized response
            response = web.Response(status=401)
            response.headers["WWW-Authenticate"] = 'Basic realm="Secure Area"'
            return response

    return middleware


async def create_app():
    app = web.Application()
    setup(app, SimpleCookieStorage(max_age=3600))
    app.middlewares.append(basic_auth_middleware)
    routes = web.RouteTableDef()
    conn = sqlite3.connect("ioibot.db")
    cursor = conn.cursor()
    with open("config.yaml", "r") as file_stream:
        config = yaml.safe_load(file_stream)
    teams_all = pd.read_csv(config["datasource"]["team_url"])
    teams = teams_all[teams_all['Voting'] == 1]


    # website
    @routes.get("/polls")
    async def polls(request):
        return web.FileResponse("./webpage/index.html")

    # return currently active poll result
    @routes.get("/polls/display")
    async def polls_active(request):
        cursor.execute("SELECT poll_id, question, status, anonymous, multiple_choice FROM polls WHERE display = 1")
        poll_exist = cursor.fetchone()
        if not poll_exist:
            result = {}
            return web.json_response(result)

        votes = []
        [poll_id, question, status, anonymous, multiple_choice] = poll_exist

        cursor.execute("SELECT poll_choice_id, choice, marker FROM poll_choices WHERE poll_id = ?", [poll_id])
        poll_choices = cursor.fetchall()
        if not poll_choices:
            return web.HTTPInternalServerError()

        choices = [{'choice_id': choice_id, 'choice': choice, 'marker': marker} for (choice_id, choice, marker) in poll_choices]

        if anonymous:
            if status == 1:
                results = dict()
                for (poll_choice_id, _, _) in poll_choices:
                    results[poll_choice_id] = 0

                cursor.execute("SELECT poll_choice_id FROM poll_anonym_active_votes")
                anonym_votes = cursor.fetchall()
                if anonym_votes:
                    for (vote,) in anonym_votes:
                        results[vote] += 1

                    votes = [{'count': count, 'choice_id': choice} for (choice, count) in results.items()]
                else:
                    votes = []

            elif status == 2:
                cursor.execute("SELECT poll_choice_id, count FROM poll_anonym_votes WHERE poll_id = ?", [poll_id])
                votes_exists = cursor.fetchall()
                votes = [{'count': count, 'choice_id': choice} for (choice, count) in votes_exists] if votes_exists else []
        else: # not anonymous
            cursor.execute("SELECT poll_choice_id, team_code, voted_by, voted_at FROM poll_votes WHERE poll_id = ?", [poll_id])
            votes_exists = cursor.fetchall()

            votes = [{'team_code': f"({team_code}) {teams.loc[teams['Code'] == team_code, ['Name']].values[0][0]}", 'voted_by': voted_by, 'voted_at': voted_at, 'choice_id': choice} for (choice, team_code, voted_by, voted_at) in votes_exists] if votes_exists else []
            missing_teams = teams.loc[~teams['Code'].isin([team_code for (_, team_code, _, _) in votes_exists]), ['Code', 'Name']]
            for _, row in missing_teams.iterrows():
                votes.append({'team_code': f"({row['Code']}) {row['Name']}", 'voted_by': None, 'voted_at': None, 'choice_id': None})

        response = {
            'question': question,
            'choices': choices,
            'anonymous': anonymous,
            'multiple_choice': multiple_choice,
            'status': status,
            'votes': votes,
        }

        return web.json_response(response)


    app.router.add_routes(routes)
    app.router.add_static("/", "./")
    return app


async def main():
    app = await create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 9000)
    await site.start()
