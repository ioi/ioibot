from aiohttp import web
import asyncio
import pandas as pd
import sqlite3
import yaml

async def create_app():
	app = web.Application()
	routes = web.RouteTableDef()
	conn = sqlite3.connect('ioibot.db')
	cursor = conn.cursor()
	with open("data/config.yaml", "r") as file_stream:
		config = yaml.safe_load(file_stream)
	teams = pd.read_csv(config['datasource']['team_url'])

	# website
	@routes.get('/polls')
	async def home(request):
		return web.FileResponse('./webpage/index.html')

	# return currently active poll result
	@routes.get('/polls/active')
	async def home(request):
		cursor.execute(
			'''SELECT poll_id, question FROM polls WHERE active = 1'''
		)
		poll_exist = cursor.fetchone()

		if not poll_exist:
			result = {}
			return web.json_response(result)
		else:
			# make sure that the json will return the question
			# and list of countries with either 
			# their choice / "none" if they haven't voted yet

			[poll_id, question] = poll_exist
			cursor.execute(
				'''SELECT team_code, choice FROM votes WHERE poll_id = ?''',
				[poll_id]
			)
			vote_result = cursor.fetchall()

			result = {'question': question}
			vote_result  = {
				vote[0]:vote[1] 
				for vote in vote_result
			}

			# show country name instead of country code for ease of use
			votes = {}
			for key, team in teams.iterrows():
				if team['Voting'] == 0:
					continue
				if team['Code'] in vote_result:
					votes[team['Name']] = vote_result[team['Code']]
				else:
					votes[team['Name']] = None

			result['votes'] = votes	
			return web.json_response(result)

	# return poll result with specified poll_id
	@routes.get('/polls/{pid}')
	async def api_poll_id(request):
		try:
			poll_id = int(request.match_info['pid'])
		except:
			raise web.HTTPBadRequest()

		cursor.execute(
			'''SELECT poll_id, question FROM polls WHERE poll_id = ?''',
			[poll_id]
		)
		poll_exist = cursor.fetchone()

		if not poll_exist:
			raise web.HTTPBadRequest()
		else:
			[poll_id, question] = poll_exist
			cursor.execute(
				'''SELECT team_code, choice FROM votes WHERE poll_id = ?''',
				[poll_id]
			)
			vote_result = cursor.fetchall()

			result = {'question': question}
			vote_result  = {
				vote[0]:vote[1] 
				for vote in vote_result
			}

			votes = {}
			for key, team in teams.iterrows():
				if team['Code'] in vote_result:
					votes[team['Name']] = vote_result[team['Code']]
				else:
					votes[team['Name']] = None

			result['votes'] = votes	
			return web.json_response(result)
			
	app.router.add_routes(routes)
	app.router.add_static('/', './')
	return app

async def main():
	app = await create_app()
	runner = web.AppRunner(app)
	await runner.setup()
	site = web.TCPSite(runner, '127.0.0.1', 9000)
	await site.start();
