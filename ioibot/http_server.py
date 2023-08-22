from aiohttp import web
import asyncio
import pandas as pd
import sqlite3
import yaml


async def create_app():
    app = web.Application()
    routes = web.RouteTableDef()
    conn = sqlite3.connect("/data/ioibot.db")
    cursor = conn.cursor()
    with open("/data/config.yaml", "r") as file_stream:
        config = yaml.safe_load(file_stream)
    teams = pd.read_csv(config["datasource"]["team_url"])

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

    # return poll result with specified poll_id
    @routes.get("/polls/{pid}")
    async def api_poll_id(request):
        try:
            poll_id = int(request.match_info["pid"])
        except:
            raise web.HTTPBadRequest()

        cursor.execute("SELECT poll_id, question, status, anonymous, multiple_choice FROM polls WHERE poll_id = ? AND status <> 0", [poll_id])
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
                    return web.HTTPInternalServerError()

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
