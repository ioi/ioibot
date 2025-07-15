import base64
import logging
import os

from aiohttp import web
from aiohttp_session import SimpleCookieStorage, get_session, setup
import asyncpg
import bcrypt
from dotenv import load_dotenv
import pandas as pd
import yaml

from .config import Config

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


async def create_app(config: Config, conn: asyncpg.Pool):
    app = web.Application()
    setup(app, SimpleCookieStorage(max_age=3600))
    app.middlewares.append(basic_auth_middleware)
    routes = web.RouteTableDef()
    teams_all = pd.read_csv(config.team_url)
    teams = teams_all[teams_all['Voting'] == 1]


    # website
    @routes.get("/polls")
    async def polls(request):
        return web.FileResponse("./webpage/index.html")

    # return currently active poll result
    @routes.get("/polls/display")
    async def polls_active(request):
        poll_details = await conn.fetchrow(
            "SELECT poll_id, question, status, anonymous, multiple_choice FROM polls WHERE display = 1")
        if poll_details is None:
            return web.json_response({})

        votes = []
        [poll_id, question, status, anonymous, multiple_choice] = poll_details

        poll_choices = await conn.fetch(
            "SELECT poll_choice_id, choice, marker FROM poll_choices WHERE poll_id = $1", poll_id)
        if not poll_choices:
            return web.HTTPInternalServerError()

        choices = [{'choice_id': choice_id, 'choice': choice, 'marker': marker} for (choice_id, choice, marker) in poll_choices]

        if anonymous:
            if status == 1:
                results = dict()
                for (poll_choice_id, _, _) in poll_choices:
                    results[poll_choice_id] = 0

                anonym_votes = await conn.fetch("SELECT poll_choice_id FROM poll_anonym_active_votes")
                for (vote,) in anonym_votes:
                    results[vote] += 1
                vote_items = results.items()
            elif status == 2:
                vote_items = await conn.fetch("SELECT poll_choice_id, count FROM poll_anonym_votes WHERE poll_id = $1", poll_id)
            else:
                vote_items = []
            votes = [{'count': count, 'choice_id': choice} for (choice, count) in vote_items]
        else: # not anonymous
            vote_items = await conn.fetch("SELECT poll_choice_id, team_code, voted_by, voted_at FROM poll_votes WHERE poll_id = $1", poll_id)
            votes = [{'team_code': f"({team_code}) {teams.loc[teams['Code'] == team_code, ['Name']].values[0][0]}", 'voted_by': voted_by, 'voted_at': voted_at, 'choice_id': choice} for (choice, team_code, voted_by, voted_at) in vote_items]
            missing_teams = teams.loc[~teams['Code'].isin([team_code for (_, team_code, _, _) in vote_items]), ['Code', 'Name']]
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

async def run_webapp(config: Config, conn: asyncpg.Pool):
    app = await create_app(config, conn)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 9000)
    await site.start()
