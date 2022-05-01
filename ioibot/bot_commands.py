from nio import AsyncClient, MatrixRoom, RoomMessageText

from ioibot.chat_functions import react_to_event, send_text_to_room
from ioibot.config import Config
from ioibot.storage import Storage

class User():
    def __init__(self, store: Storage, config: Config, username: str):
        self.username = username
        self.config = config
        self.role = "Unknown"

        users = store.leaders
        teams = store.teams

        user = users.loc[self._get_username(users['UserID']) == username, \
                        ['TeamCode', 'Name', 'Role', 'UserID']]

        if not user.empty:
            country = teams.loc[teams['Code'] == user.iat[0, 0], ['Name']]
            self.team = user.iat[0, 0]
            self.name = user.iat[0, 1]
            self.role = user.iat[0, 2]
            self.country = country.iat[0, 0]

    def _get_username(self, name):
        homeserver = self.config.homeserver_url[8:]
        return "@" + name + ":" + homeserver

class Command:
    def __init__(
        self,
        client: AsyncClient,
        store: Storage,
        config: Config,
        command: str,
        room: MatrixRoom,
        event: RoomMessageText,
    ):
        """A command made by a user.

        Args:
            client: The client to communicate to matrix with.

            store: Bot storage.

            config: Bot configuration parameters.

            command: The command and arguments.

            room: The room the command was sent in.

            event: The event describing the command.
        """
        self.client = client
        self.store = store
        self.config = config
        self.command = command
        self.room = room
        self.event = event
        self.args = self.command.split()[1:]

    async def process(self):
        user = User(self.store, self.config, self.event.sender)
        self.user = user

        """Process the command"""
        if self.command.startswith("echo"):
            await self._echo()

        elif self.command.startswith("react"):
            await self._react()

        elif self.command.startswith("help"):
            await self._show_help()

        elif self.command.startswith("info"):
            await self._show_info()

        elif self.command.startswith("poll"):
            if user.role not in ['HTC']:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Only HTC can use this command."
                )
                return

            await self._manage_poll()

        elif self.command.startswith("vote"):
            if user.role not in ['Leader', 'Deputy Leader']:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Only Leader and Deputy Leader can use this command."
                )
                return

            await self._vote()

        else:
            await self._unknown_command()

    async def _echo(self):
        """Echo back the command's arguments"""
        response = " ".join(self.args)
        await send_text_to_room(self.client, self.room.room_id, response)

    async def _react(self):
        """Make the bot react to the command message"""
        # React with a start emoji
        reaction = "⭐"
        await react_to_event(
            self.client, self.room.room_id, self.event.event_id, reaction
        )

        # React with some generic text
        reaction = "Some text"
        await react_to_event(
            self.client, self.room.room_id, self.event.event_id, reaction
        )

    async def _show_help(self):
        """Show the help text"""
        if not self.args:
            text = (
                "Hello, I am a bot made with matrix-nio! Use `help commands` to view "
                "available commands."
            )
            await send_text_to_room(self.client, self.room.room_id, text)
            return

        topic = self.args[0]
        if topic == "rules":
            text = "These are the rules!"
        elif topic == "commands":
            text = "Available commands: ..."
        else:
            text = "Unknown help topic!"
        await send_text_to_room(self.client, self.room.room_id, text)

    async def _show_info(self):
        """Show team info"""
        if not self.args:
            text = (
                "Usage:"
                "  \n`info <3-letter-country-code>`: shows team members"
                "  \n  \nExamples:"
                "  \n- `info IDN`"
            )
            await send_text_to_room(self.client, self.room.room_id, text)
            return

        teamcode = self.args[0].upper()
        teams = self.store.teams
        leaders = self.store.leaders

        if teamcode not in teams['Code'].unique():
            text = (
                f"Team {teamcode} not found!"
            )
            await send_text_to_room(self.client, self.room.room_id, text)
            return

        response = f"""Team members from {teamcode}
        ({teams.loc[teams['Code'] == teamcode, 'Name'].item()}):"""

        curteam = leaders.loc[leaders['TeamCode'] == teamcode]

        roles = []
        for row in curteam["Role"]:
            if row not in roles:
                roles.append(row)

        for role in roles:
          response += f"  \n  \n{role}:"
          for index, member in curteam.iterrows():
            if member['Role'] == role:
              response += f"  \n- @{member['UserID']}:{self.config.homeserver_url[8:]} ({member['Name']})"

        response += "  \n  \nContestants:"
        for index, row in self.store.contestants.iterrows():
            if row['ContestantCode'].startswith(teamcode):
                response += f"  \n- {row['ContestantCode']} ({row['FirstName']} {row['LastName']})"

        await send_text_to_room(self.client, self.room.room_id, response)

    async def _manage_poll(self):
        cursor = self.store.vconn.cursor()

        if not self.args:
            text = (
                "Usage:  \n\n"
                '- `poll new "<question>" "<choices-separated-with-/>"`: create new poll  \n'
                '- `poll update <poll-id> "<question>" "<choices-separated-with-/>"`: update existing poll  \n'
                '- `poll list`: show list of created polls  \n'
                '- `poll activate <poll-id>`: activate a poll  \n'
                '- `poll deactivate`: deactivate all polls  \n\n'

                "Examples:  \n\n"
                '- `poll new "Is this a question?" "yes/no/abstain"`  \n'
                '- `poll update 1 "What is 1+1?" "one/two/yes"`  \n'
                '- `poll activate 10`'
            )
            await send_text_to_room(self.client, self.room.room_id, text)
            return
            
        elif self.args[0].lower() == 'new':
            input_poll = ' '.join(self.args[1:])
            input_poll = input_poll.split('"')[1::2]

            # wrong format: need more arguments, no double quotes, etc.
            if(len(input_poll) < 2):
                await send_text_to_room(
                    self.client, self.room.room_id, 
                    "Command format is invalid. Send `poll` to see all commands."
                )
                return

            cursor.execute(
                '''INSERT INTO polls (question, choices, active) VALUES (?, ?, 0)''',
                [input_poll[0], input_poll[1]]
            )
            poll_id = cursor.lastrowid

            await send_text_to_room(
                self.client, self.room.room_id,
                f"Poll created with ID {poll_id}.  \n"
            )

        elif self.args[0].lower() == 'update':
            # no id given
            if len(self.args) < 2:
                await send_text_to_room(
                    self.client, self.room.room_id, 
                    "Command format is invalid. Send `poll` to see all commands."
                )
                return

            poll_id = self.args[1]
            try:
                poll_id = int(poll_id)
            except:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Poll ID must be an integer.  \n"
                )
                return

            input_poll = ' '.join(self.args[2:])
            input_poll = input_poll.split('"')[1::2]

            # wrong format: need more arguments, no double quotes, etc.
            if(len(input_poll) < 2):
                await send_text_to_room(
                    self.client, self.room.room_id, 
                    "Command format is invalid. Send `poll` to see all commands."
                )
                return

            cursor.execute(
                '''UPDATE polls SET question = ?, choices = ? WHERE poll_id = ?''',
                [input_poll[0], input_poll[1], poll_id]
            )
            id_exist = cursor.execute('''SELECT changes()''').fetchall()[0][0]
            
            if not id_exist:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    f"Poll {poll_id} does not exist.  \n"
                )
                return

            await send_text_to_room(
                self.client, self.room.room_id,
                f"Poll {poll_id} updated.  \n"
            )

        elif self.args[0].lower() == 'list':
            cursor.execute(
                '''SELECT poll_id, question, choices, active FROM polls'''
            )
            poll_list = cursor.fetchall()

            if not poll_list:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "No polls have been created."
                )
                return

            text = ""
            for poll_detail in poll_list:
                text += f"Poll {poll_detail[0]}"
                if poll_detail[3]: # if poll is active
                    text += " (active)"
                text +=  ":  \n"
                text += f'&emsp;&ensp;"{poll_detail[1]}"  \n'

                options = poll_detail[2].split('/')
                options = '/'.join(("`"+option+"`") for option in options)
                text += f"&emsp;&ensp;{options}  \n\n"

            await send_text_to_room(self.client, self.room.room_id, text)

        elif self.args[0].lower() == 'activate':
            # no id given
            if len(self.args) < 2:
                await send_text_to_room(
                    self.client, self.room.room_id, 
                    "Command format is invalid. Send `poll` to see all commands."
                )
                return

            poll_id = self.args[1]
            try:
                poll_id = int(poll_id)
            except:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Poll ID must be an integer.  \n"
                )
                return

            cursor.execute(
                '''SELECT poll_id FROM polls WHERE poll_id = ?''',
                [poll_id]
            )
            id_exist = cursor.fetchall()

            if not id_exist:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    f"Poll {poll_id} does not exist.  \n"
                )
                return

            cursor.execute(
                '''SELECT poll_id FROM polls WHERE active = 1'''
            )
            active_exist = cursor.fetchall()

            if active_exist:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    f"Poll {active_exist[0][0]} is already active. Only one poll can be active at any time.  \n"
                )
                return
            
            cursor.execute(
                '''UPDATE polls SET active = 1 WHERE poll_id = ?''',
                [poll_id]
            )

            cursor.execute(
                '''SELECT question, choices FROM polls WHERE poll_id = ?''',
                [poll_id]
            )
            active_poll = cursor.fetchall()

            options = active_poll[0][1].split('/')
            options = '/'.join(("`"+option+"`") for option in options)

            text = (
                f"Active poll is now poll {poll_id}:  \n"
                f'&emsp;&ensp;"{active_poll[0][0]}"  \n'
                f"&emsp;&ensp;{options}  \n"
            )
            await send_text_to_room(self.client, self.room.room_id, text)

        elif self.args[0] == 'deactivate':
            cursor.execute(
                '''UPDATE polls SET active = 0 WHERE active = 1'''
            )

            await send_text_to_room(
                self.client, self.room.room_id,
                "All polls deactivated.  \n"
            )

        else:
            await send_text_to_room(
                self.client, self.room.room_id,
                "Unknown command. Send `poll` to see all available commands.  \n"
            )

    async def _vote(self):
        cursor = self.store.vconn.cursor()

        cursor.execute(
            '''SELECT poll_id, question, choices FROM polls WHERE active = 1'''
        )
        active_poll = cursor.fetchall()

        if not active_poll:
            await send_text_to_room(
                self.client, self.room.room_id,
                "There is no active poll to vote!  \n"
            )
            return

        active_poll = active_poll[0]
        poll_id  = active_poll[0]
        question = active_poll[1]
        choices  = active_poll[2].split('/')

        if not self.args:
            text  = f'Question: "{question}"  \n\n'
            text += f"You are voting on behalf of the {self.user.country} team.  \n\n"
            text += "Vote by sending one of: \n\n"
            for choice in choices:
                text += f"- `vote {choice}`  \n"

            await send_text_to_room(self.client, self.room.room_id, text)

        elif ' '.join(self.args) in choices:
            self.args = ' '.join(self.args)

            text = (
                f'Question: "{question}"  \n\n'
                f"You voted `{self.args}` on behalf of the {self.user.country} team."
                " Please wait for your vote to be displayed on the screen.  \n\n"
                "You can amend your vote by resending your vote.  \n"

            )
            await send_text_to_room(self.client, self.room.room_id, text)

            cursor.execute(
                '''
                INSERT INTO votes (poll_id, team_code, choice, voted_by, voted_at)
                VALUES (?, ?, ?, ?, datetime("now", "localtime"))
                ON CONFLICT(poll_id, team_code) DO UPDATE
                SET choice = excluded.choice, voted_by = excluded.voted_by, voted_at = datetime("now", "localtime") 
                ''',
                [poll_id, self.user.team, self.args, self.user.username]
            )

        else:
            text  = "Your vote is invalid.  \n\n"
            text += "Vote by sending one of:  \n\n"
            for choice in choices:
                text += f"- `vote {choice}`  \n"

            await send_text_to_room(self.client, self.room.room_id, text)

    async def _unknown_command(self):
        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"Unknown command '{self.command}'. Try the 'help' command for more information.",
        )
