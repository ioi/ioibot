import logging

from aiohttp import web

from ioibot.storage import Storage

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

routes = web.RouteTableDef()
store_key = web.AppKey("store", Storage)
static_root = 'webpage' # TODO make this configurable

# return currently active poll result
@routes.get("/api/polls")
async def polls_active(req: web.Request):
    store = req.app[store_key]
    conn = store.conn
    teams = store.teams

    poll_details = await conn.fetchrow(
        "SELECT poll_id, question, status, anonymous, multiple_choice FROM polls WHERE display")
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
        votes = [{'team_code': f"({team_code}) {teams.loc[teams['Code'] == team_code, ['Name']].values[0][0]}", 'voted_by': voted_by, 'voted_at': voted_at.isoformat(), 'choice_id': choice} for (choice, team_code, voted_by, voted_at) in vote_items]
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

# for development, should be handled by nginx
@routes.get('/')
async def get_index(req: web.Request):
    return web.FileResponse(f'{static_root}/index.html')
routes.static('/', static_root)

async def run_webapp(store: Storage):
    app = web.Application()
    app[store_key] = store
    app.add_routes(routes)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 9000) # TODO make this configurable
    await site.start()
