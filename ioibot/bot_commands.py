import asyncio
import functools
import dropbox
from datetime import datetime

from nio import AsyncClient, MatrixRoom, RoomMessageText
from nio.responses import RoomGetEventError

from ioibot.chat_functions import react_to_event, send_text_to_room, send_text_to_thread, make_pill
from ioibot.config import Config
from ioibot.storage import Storage
import shlex;

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def assume(pred, message):
    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            if pred(self):
                return await func(self, *args, **kwargs)
            else:
                await send_text_to_room(self.client, self.room.room_id, message)
                return None
        return wrapper
    return decorator

class User():
    def __init__(self, store: Storage, config: Config, username: str):
        self.username = username
        self.config = config
        self.role = "Unknown"

        users = store.leaders
        teams = store.teams

        user = users.loc[self._get_username(users['UserID']) == username, \
                        ['TeamCode', 'RealTeamCode', 'Name', 'Role', 'UserID']]

        if not user.empty:
            country = teams.loc[teams['Code'] == user.iat[0, 0], ['Name']]
            # if the user is not specified in the spreadsheet,
            # or if the country code is not found,
            # assume that the user is unauthorized to use this bot.
            if country.empty:
                self.role = "Unknown"
            else:
                self.team = user.iat[0, 0]
                self.real_team = user.iat[0, 1]
                self.name = user.iat[0, 2]
                self.role = user.iat[0, 3]
                self.country = country.iat[0, 0]
                self.user_id = user.iat[0, 4]

    def is_leader(self):
        return self.is_tc() or self.role in ['Team Leader', 'Deputy Leader']

    def is_tc(self):
        return 'TC' in self.role

    def is_sc(self):
        return 'SC' in self.role

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

        if self.user.role == "Unknown":
            await send_text_to_room(
                self.client, self.room.room_id,
                "You are not authorized to use this bot. Please contact HTC for details."
            )
            return

        """Process the command"""
        if self.command.startswith("echo"):
            await self._echo()

        elif self.command.startswith("react"):
            await self._react()

        elif self.command.startswith("help"):
            await self._show_help()

        elif self.command.startswith("info"):
            await self._show_info()

        elif self.command.startswith("refresh"):
            if not self.user.is_tc():
              await send_text_to_room(
                  self.client, self.room.room_id,
                  "Only HTC can use this command."
              )
              return
            await self._refresh()

        elif self.command.startswith("poll"):
            if not self.user.is_tc():
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Only HTC can use this command."
                )
                return

            await self._manage_poll()

        elif self.command.startswith("vote"):
            if not self.user.is_leader():
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Only Team Leader and Deputy Leader can use this command."
                )
                return

            if self.user.is_tc():
              if len(self.args) == 0:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Usage: `vote <3-letter-country-code> [choices]`"
                )
                return
              if await self._validate(len(self.args) > 0, "Usage: `vote [choices]`"): return;  
              team_code = self.args[0].upper()
              # if team code to upper does not exists
              if await self._validate(not self.store.teams.loc[self.store.teams['Code'] == team_code].empty, f"Team {team_code} not found."): return;

              self.args = self.args[1:]
            else:
              team_code = self.user.team
                
            team = self.store.teams.loc[self.store.teams['Code'] == team_code]
            if not team.empty and team.iloc[0]['Voting'] == 0:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Sorry, you are not allowed to vote."
                )
                return

            self.user.team = team_code
            await self._vote()

        elif self.command.startswith("invite"):
            await send_text_to_room(self.client, self.room.room_id, "This command is turned off")
            return

            if not self.user.is_tc():
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Only HTC can use this command."
                )
                return

            await self.invite()

        elif self.command.startswith("accounts"):
            if not self.user.is_leader():
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Only Team Leader and Deputy Leader can use this command."
                )
                return

            await self._show_accounts()

        elif self.command.startswith("objection"):
            if not self.user.is_leader() and not self.user.is_sc():
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Only Team Leaders, Deputy Leaders and SC members can use this command."
                )
                return

            await self._objection()

        elif self.command.startswith("dropbox"):
            await send_text_to_room(self.client, self.room.room_id, "This command is turned off")
            return

            if not self.user.is_leader():
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Only Team Leader and Deputy Leader can use this command."
                )
                return

            await self._get_dropbox()

        elif self.command.startswith("token"):
            await send_text_to_room(self.client, self.room.room_id, "This command is turned off")
            return

            if not self.user.is_leader():
                await send_text_to_room(
                    self.client, self.room.room_id,
                    "Only Team Leader and Deputy Leader can use this command."
                )
                return

            await self._get_token()

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

        text = ""
        text += "Hello, I am IOI 2024 bot. I understand several commands:  \n\n"
        text += "- `info`: shows various team information\n"
        text += "- `accounts`: shows various accounts for your team\n"
        text += "- `vote`: casts vote for your team\n"

        await send_text_to_room(self.client, self.room.room_id, text)

    async def _show_info(self):
        """Show team info"""
        if not self.args:
            text = (
                "Usage:  \n\n"
                "`info <3-letter-country-code>|ic|sc|tc`: shows team/IC/SC/TC members  \n\n"
                "Examples:  \n\n"
                "- `info IDN`  \n"
                "- `info ic`  \n"
            )
            await send_text_to_room(self.client, self.room.room_id, text)
            return

        teamcode = self.args[0].upper()
        teams = self.store.teams
        leaders = self.store.leaders

        if teamcode in ['IC', 'SC', 'TC']:
            rolecode = teamcode
            roles = []
            response = ""

            if rolecode == 'IC':
                roles = ['President', 'Chair of IOI / IC Member', 'IC Member', 'Secretary', 'Treasurer']
            if rolecode == 'SC':
                roles = ['ISC Member', 'HSC', 'Invited HSC']
            if rolecode == 'TC':
                roles = ['ITC Member', 'HTC', 'Invited HTC']

            for idx, role in enumerate(roles):
                if idx > 0:
                    response += "  \n  \n"
                response += f"{role}:  \n"
                for index, member in leaders.iterrows():
                    if member['Role'] == role and member['Chair'] == 1:
                        response += f"  \n- {make_pill(member['UserID'], self.config.homeserver_url)} (Chair) | {member['Name']}"
                for index, member in leaders.iterrows():
                    if member['Role'] == role and member['Chair'] != 1:
                        response += f"  \n- {make_pill(member['UserID'], self.config.homeserver_url)} | {member['Name']}"

            await send_text_to_room(self.client, self.room.room_id, response)
            return

        team = teams.loc[(teams['Code'] == teamcode) & (teams['Visible'] == 1)]

        if team.empty:
            text = (
                f"Team {teamcode} not found!"
            )
            await send_text_to_room(self.client, self.room.room_id, text)
            return

        response = f"""Team members from {teamcode}
        ({team.iloc[0]['Name']}):"""

        curteam = leaders.loc[leaders['TeamCode'] == teamcode]

        roles = []
        for index, member in curteam.iterrows():
            role = member['Role']
            userID = member['UserID']
            if role not in roles and role in ['Team Leader', 'Deputy Leader', 'Guest', 'Remote Adjunct (not on site)', 'Invited Observer/Guest'] and exists(userID):
                roles.append(role)

        for role in roles:
            response += f"  \n  \n{role}: \n"
            for index, member in curteam.iterrows():
                if member['Role'] == role and exists(member['UserID']):
                    response += f"  \n- {make_pill(member['UserID'], self.config.homeserver_url)} | {member['Name']}"

        response += "  \n  \nContestants:  \n"
        for index, row in self.store.contestants.iterrows():
            if row['ContestantCode'].startswith(teamcode):
                response += f"  \n- `{row['ContestantCode']}`"
                if row['Online'] == 1:
                    response += " (online)"
                response += f" | {row['FirstName']} {row['LastName']}"

        await send_text_to_room(self.client, self.room.room_id, response)


    def _get_poll_display(self, poll_id, question, status, display, anonymous, multiple_choice, poll_choices, user_choices = None):
        text = ""
        if poll_id is not None:
            text += f'### [{poll_id}] {question}  \n'
        else:
            text += f'### {question}  \n'
        
        text += f'anonymous: {"Yes" if anonymous else "No"}  \n'
        text += f'multiple choice: {"Yes" if multiple_choice else "No"}  \n'
        
        if status is not None:
            text += f'status: {["inactive", "active", "closed"][status]}  \n'

        if display is not None:
            text += f'{"Results are shown" if display else "Results are hidden"}  \n'

        text += '\n'

        poll_choices.sort(key=lambda x: x[0]) # sort by id
        if user_choices is not None:
            for i, (poll_choice_id, choice, marker) in enumerate(poll_choices):
                text += f'{ "**" if poll_choice_id in user_choices else ""}{i + 1}.&emsp;{marker}&emsp;{choice}{ "**" if poll_choice_id in user_choices else ""}  \n'
        else:
            for _, choice, marker in poll_choices:
                text += f'- {marker}/{choice}  \n'

        return text
  

    @assume(lambda self: self.args, (
                "Usage:  \n\n"
                '- `poll new [--options ...] "<question>" "<mark1>/<choice 1>" "<mark 2>/<choice 2>" "<mark3>/<choice 3>" ... `: create new poll  \n'
                '- `poll update <poll-id> [--options ...] "<question>" "<mark 1>/<choice 1>" "<mark 2>/<choice 2>" "<mark 3>/<choice 3>" ...`: update existing poll  \n'
                '- `poll update <poll-id> [--options ...] "[question]"`: update existing poll but leave the choices  \n'
                '- `poll list`: show list of created polls  \n'
                '- `poll clear-display`: clears the displayed poll from the web interface  \n'
                '- `poll activate <poll-id>`: activate a poll  \n'
                '- `poll close`: deactivate all polls  \n\n'

                'Ooptions for `new` and `update`:  \n'
                '    - `-a, --anonymous`: make the poll anonymous  \n'
                '    - `-m, --multiple-choice`: allow multiple choices  \n'
                '    - `-d, --display`: set to show  \n'
                '    - `-s, --start`: set to active if no other pool is open  \n\n'
                
                'Note:  if an argument consists of multiple words you can wrap it in double quotes, otherwise you don\'t have to.  \n\n'
                
                "Examples:  \n"
                '- `poll new "What is your favorite color?" 🟥/Red 🟧/Orange 🟨/Yellow 🟩/Green 🟦/Blue`: creates a poll  \n'
                '- `poll new -ds "Question?" "✅/Vote for motion" "❌/Vote against motion" "➖/Abstain"`: creates, displays and starts a poll   \n'
                '- `poll new --anonymous "What is your favorite number?" "1️⃣/One" "2️⃣/Two" "3️⃣/Three" "4️⃣/Four"`: creates an anonymous poll   \n'
                
                '- `poll new  --multiple-choice --anonymous "What is your favorite letter?" "A" "B" "🅾️/O"`: creates an anonym, multiple choice poll   \n'
                '- `poll new "Is this a question?" yes no abstain"`: creates a poll with the default markers  \n'
                '- `poll update 1 -ma "What is 1+1?" one two three`: changes the existing poll 1 to be anonym and multiple choice, also rewrites the question and answers  \n'
                '- `poll update 1 -d`: sets poll 1 to be displayed  \n'
                '- `poll activate 10`: opens poll 10 for voting  \n'
    ))
    async def _manage_poll(self):
        cursor = self.store.vconn.cursor()

        def _get_options(args):
            ANONYM  = int(0b0001)
            MULTIPLE= int(0b0010)
            DISPLAY = int(0b0100)
            START   = int(0b1000)

            long_options = {"--anonymous" : ANONYM, "--multiple-choice" : MULTIPLE, "--display" : DISPLAY, "--start" : START}
            short_options = {"a" : ANONYM, "m" : MULTIPLE, "d" : DISPLAY, "s" : START}

            err = ""
            options = 0
            arguments = []
            for arg in args:
                if arg.startswith("--"):
                    if arg in long_options:
                        options |= long_options[arg]
                    else:
                        err += f"Unknown option ignored: {arg}.  \n"
                elif arg.startswith("-"):
                    for c in arg[1:]:
                        if c in short_options:
                            options |= short_options[c]
                        else:
                            err += f"Unknown option ignored: -{c}.  \n"
                else:
                    arguments.append(arg.strip())

            anonymous        = int(bool(options & ANONYM))
            multiple_choice  = int(bool(options & MULTIPLE))
            display          = int(bool(options & DISPLAY))
            start            = int(bool(options & START))

            return (arguments, err, (anonymous, multiple_choice, display, start))

        async def _new(args):
            (arguments, err, (anonymous, multiple_choice, display, start)) = _get_options(args)
            if await self._validate(len(arguments) >= 3, "Command is invalid, there must be a question and at least 2 choices.\nSend `poll` to see all commands."): return;

            question = arguments[0]
            choices_with_markers = arguments[1:]

            choices = [""] * len(choices_with_markers)
            markers = [""] * len(choices_with_markers)

            for i, choice_with_marker in enumerate(choices_with_markers):
                if '/' in choice_with_marker:
                    marker = choice_with_marker.split('/')[0]
                    choice = choice_with_marker[len(marker)+1:]
                    markers[i] = marker
                    choices[i] = choice
                else:
                    choices[i] = choice_with_marker
                    markers[i] = str(i+1)

            if await self._validate(all(markers.count(marker) == 1 for marker in markers), f"Command format is invalid, there are duplicate markers. Send `poll` to see all commands."): return;
            if await self._validate(all([choices.count(choice) == 1 for choice in choices]), f"Command format is invalid, there are duplicate choices. Send `poll` to see all commands."): return;

            status = 0
            if start:
                cursor.execute('SELECT poll_id FROM polls WHERE status = 1')
                active_exist = cursor.fetchone()
                status = 1 if not active_exist else 0

            if display:
                cursor.execute('UPDATE polls SET display = 0')

            cursor.execute(
                '''INSERT INTO polls (question, status, display, anonymous, multiple_choice)
                VALUES (?, ?, ?, ?, ?)''',
                [question, status, display, anonymous, multiple_choice]
            )
            
            poll_id = cursor.lastrowid

            for choice, marker in zip(choices, markers):
                cursor.execute(
                    '''INSERT INTO poll_choices (poll_id, choice, marker)
                    VALUES (?, ?, ?)''',
                    [poll_id, choice, marker]
                )

            text = self._get_poll_display(
                poll_id = poll_id, 
                question = question,
                status = status,
                display = display,
                anonymous = anonymous,
                multiple_choice = multiple_choice,
                poll_choices = list(zip(range(len(choices)), choices, markers)),
                user_choices = None,
            )
            

            if start == 1 and status == 0:
                text += '\n\n'
                text += f'Poll {poll_id} is **inactive**, beacause another poll is still active.  \n'

            if err:
                text += '\n\n'
                text += err

            await send_text_to_room(self.client, self.room.room_id, text)

        async def _update(poll_id, args):
            cursor.execute('SELECT question, status FROM polls WHERE poll_id = ?', [poll_id])
            poll_exists = cursor.fetchone()
            if await self._validate(poll_exists, f"Poll {poll_id} does not exist.  \n\nSend `poll list` to see all created polls.  \n"): return;
            (question_db, status) = poll_exists

            input_poll = ' '.join(args)
            
            try:
              (arguments, err, (anonymous, multiple_choice, display, start)) = _get_options(shlex.split(input_poll))
            except Exception as e:
              err_message="Wrong format"
              if hasattr(e, 'message'):
                  err_message = e.message
              await send_text_to_room(self.client, self.room.room_id, f"Format Error: {err_message}")
              return
            
            if anonymous == 0 and multiple_choice == 0 and start == 0 and len(arguments) == 0 and display == 1: # only the display is changed
                cursor.execute('UPDATE polls SET display = CASE WHEN poll_id = ? THEN 1 ELSE 0 END', [poll_id])
                await send_text_to_room(self.client, self.room.room_id, f'Poll {poll_id} is now displayed.  \n')
                return

            if await self._validate(status == 0, f"Poll {poll_id} is {['inactive', 'active', 'closed'][status]}, it cannot be updated  \n"): return;

            if len(arguments) <= 1: # only update the question
                if display:
                    cursor.execute('UPDATE polls SET display = 0')
    
                question = arguments[0] if len(arguments) == 1 else question_db

                cursor.execute(
                    '''UPDATE polls SET question = ?, display = ?, anonymous = ?, multiple_choice = ? WHERE poll_id = ?''',
                    [question, anonymous, display, multiple_choice, poll_id]
                )

                # get poll choices
                cursor.execute('SELECT poll_choice_id, choice, marker FROM poll_choices WHERE poll_id = ?', [poll_id])
                poll_choices = cursor.fetchall()
                if await self._validate(poll_choices, f"Internal server error while updating a poll.  \n"): return;

                text = self._get_poll_display(
                    poll_id = poll_id, 
                    question = question,
                    status = status,
                    display = display,
                    anonymous = anonymous,
                    multiple_choice = multiple_choice,
                    poll_choices = poll_choices,
                    user_choices = None,
                )

                if start:
                    text += '\n\n'
                    text += f'Use `poll activate {poll_id}` to activate this poll.  \n'
                    text += f'Use `poll close` to close the currently active poll.  \n'

                if err:
                    text += '\n\n'
                    text += err

                await send_text_to_room(self.client, self.room.room_id, text)
                return       
           
            if await self._validate(len(arguments) >= 3, "Command is invalid, there must be a question and at least 2 choices. Send `poll` to see all commands."): return;

            question = arguments[0]
            choices_with_markers = arguments[1:]

            choices = [""] * len(choices_with_markers)
            markers = [""] * len(choices_with_markers)

            for i, choice_with_marker in enumerate(choices_with_markers):
                if '/' in choice_with_marker:
                    marker = choice_with_marker.split('/')[0]
                    choice = choice_with_marker[len(marker)+1:]
                    markers[i] = marker
                    choices[i] = choice
                else:
                    choices[i] = choice_with_marker
                    markers[i] = str(i+1)

            if await self._validate(all(markers.count(marker) == 1 for marker in markers), f"Command format is invalid, there are duplicate markers. Send `poll` to see all commands."): return;
            if await self._validate(all([choices.count(choice) == 1 for choice in choices]), f"Command format is invalid, there are duplicate choices. Send `poll` to see all commands."): return;


            if display:
                    cursor.execute('UPDATE polls SET display = 0')

            cursor.execute(
                '''UPDATE polls SET question = ?, display = ?, anonymous = ?, multiple_choice = ? WHERE poll_id = ?''',
                [question, anonymous, display, multiple_choice, poll_id]
            )

            cursor.execute('DELETE FROM poll_choices WHERE poll_id = ?', [poll_id])
            for choice, marker in zip(choices, markers):
                cursor.execute(
                    '''INSERT INTO poll_choices (poll_id, choice, marker)
                    VALUES (?, ?, ?)''',
                    [poll_id, choice, marker]
                )


            text = self._get_poll_display(
                poll_id = poll_id, 
                question = question,
                status = status, 
                display = display,
                anonymous = anonymous,
                multiple_choice = multiple_choice,
                poll_choices = list(zip(range(len(choices)), choices, markers)),
                user_choices = None,
            )

            if start:
                text += '\n\n'
                text += f'Only polls in the **inactive** state can be updated.  \n'

            if err:
                text += '\n\n'
                text += err

            await send_text_to_room(self.client, self.room.room_id, text)

        async def _list():
            cursor.execute('SELECT poll_id, question, status, display, anonymous, multiple_choice FROM polls')
            poll_list = cursor.fetchall()

            if await self._validate(poll_list, "No polls have been created."): return;

            cursor.execute('SELECT poll_id, choice, marker FROM poll_choices')
            poll_choices_ungrouped = cursor.fetchall()

            text = '## Created polls'
            poll_choices = dict()
            for poll_id, choice, marker in poll_choices_ungrouped:
                if poll_id not in poll_choices:
                    poll_choices[poll_id] = []
                poll_choices[poll_id].append(f"{marker} / {choice}")

            for poll_id, question, status, display, anonymous, multiple_choice  in poll_list:
                text += '\n\n'
                text += f'### [{poll_id}] {question}  \n'
                text += f'anonymous: {"Yes" if anonymous else "No"}  \n'
                text += f'multiple choice: {"Yes" if multiple_choice else "No"}  \n'
                text += f'status: {["inactive", "active", "closed"][status]}  \n'
                text += f"{'Results are shown' if display else 'Results are hidden'}  \n\n"

                for choice in poll_choices[poll_id]:
                    text += f'- {choice}  \n'

            await send_text_to_room(self.client, self.room.room_id, text)

        async def _activate(poll_id = None):
            if poll_id is None:
                cursor.execute('SELECT poll_id, question, status, display, anonymous, multiple_choice FROM polls WHERE status = 1')
                poll_details = cursor.fetchone()

                if await self._validate(poll_details, "There is no active poll."): return;
                
                poll_id, question, status, display, anonymous, multiple_choice = poll_details
                cursor.execute('SELECT poll_choice_id, choice, marker FROM poll_choices WHERE poll_id = ?', [poll_id])
                poll_choices = cursor.fetchall()
                if await self._validate(poll_choices, "Internal server error: There are no choices for this poll!"): return;

                text = self._get_poll_display(
                    poll_id = poll_id, 
                    question = question,
                    status = status,
                    display = display,
                    anonymous = anonymous,
                    multiple_choice = multiple_choice,
                    poll_choices = poll_choices,
                    user_choices = None,
                )

                await send_text_to_room(self.client, self.room.room_id, text)
                return

            cursor.execute('SELECT status FROM polls WHERE poll_id = ?', [poll_id])
            id_exist = cursor.fetchall()
            if await self._validate(id_exist, f"Poll {poll_id} does not exist.  \n\nSend `poll list` to see all created polls.  \n"): return;
            (status,) = id_exist[0]
            if await self._validate(status == 0, f"Poll {poll_id} is {['inactive', 'active', 'closed'][status]}, it cannot be activated  \n"): return;

            cursor.execute('SELECT poll_id FROM polls WHERE status = 1')
            active_exist = cursor.fetchall()
            if await self._validate(not active_exist, f"Poll {active_exist[0][0] if active_exist else 'None'} is already active. Only one poll can be active at any time.  \n"): return;

            cursor.execute('UPDATE polls SET status = 1 WHERE poll_id = ?', [poll_id])
            cursor.execute('SELECT question, status, display, anonymous, multiple_choice FROM polls WHERE poll_id = ?',[poll_id])

            
            poll_details = cursor.fetchone()
            if await self._validate(poll_details, f"Poll {poll_id} does not exist.  \n\nSend `poll list` to see all created polls.  \n"): return;
            
            question, status, display, anonymous, multiple_choice = poll_details

            cursor.execute('SELECT poll_choice_id, choice, marker FROM poll_choices WHERE poll_id = ?', [poll_id])
            poll_choices = cursor.fetchall()

            text = self._get_poll_display(
                poll_id = poll_id,
                question = question,
                status = status,
                display = display,
                anonymous = anonymous,
                multiple_choice = multiple_choice,
                poll_choices = poll_choices,
                user_choices = None,
            )

            await send_text_to_room(self.client, self.room.room_id, text)

        async def _close():
            cursor.execute('SELECT poll_id, anonymous, multiple_choice FROM polls WHERE status = 1')
            active_exist = cursor.fetchall()
            if await self._validate(active_exist, "There is no active poll."): return;
            
            poll_id, anonymous, multiple_choice = active_exist[0]

            if anonymous:
                cursor.execute('SELECT poll_choice_id FROM poll_choices WHERE poll_id = ?', [poll_id])
                poll_choices = cursor.fetchall()

                results = dict()
                for (poll_choice_id,) in poll_choices:
                    results[poll_choice_id] = 0

                cursor.execute('SELECT poll_choice_id FROM poll_anonym_active_votes')
                votes = cursor.fetchall()
                for (vote,) in votes:
                    results[vote] += 1
                
                for poll_choice_id, count in results.items():
                    cursor.execute('INSERT INTO poll_anonym_votes (poll_choice_id, poll_id, count) VALUES (?, ?, ?)', [poll_choice_id, poll_id, count])

                cursor.execute('UPDATE polls SET status = 2 WHERE poll_id = ?', [poll_id])
                cursor.execute('DELETE FROM poll_anonym_active_votes')

            else: # not anonymous 
                cursor.execute('UPDATE polls SET status = 2 WHERE poll_id = ?', [poll_id])

            await send_text_to_room(
                self.client, self.room.room_id,
                "The voting has been closed!."
            )


        if self.args[0].lower() == 'new':
            input_poll = ' '.join(self.args[1:])
            try:
              arguments = shlex.split(input_poll)
            except Exception as e:
              err_message="Wrong format"
              if hasattr(e, 'message'):
                  err_message = e.message
              await send_text_to_room(self.client, self.room.room_id, f"Format Error: {err_message}")
              return

            await _new(arguments)

        elif self.args[0].lower() == 'update':
            if await self._validate(len(self.args) >= 2, "Command format is invalid. Send `poll` to see all commands."): return;
            if await self._validate(len(self.args[1]) < 10 and self.args[1].isdigit(), "Poll ID must be an integer.  \n"): return;
            poll_id = int(self.args[1])
            args = self.args[2:]
            await _update(poll_id, args)

        elif self.args[0].lower() == 'list':
            if await self._validate(len(self.args) == 1, "Command format is invalid. Send `poll` to see all commands."): return;
            await _list()

        elif self.args[0].lower() == 'activate':
            if await self._validate(len(self.args) <= 2, "Command format is invalid. Send `poll` to see all commands."): return;
            poll_id = self.args[1] if len(self.args) == 2 else None
            if poll_id is not None:
                if await self._validate(len(poll_id) < 10 and poll_id.isdigit(), "Poll ID must be an integer."): return;
                poll_id = int(poll_id)
            await _activate(poll_id)

        elif self.args[0] == 'close':
            if await self._validate(len(self.args) == 1, "Command format is invalid. Send `poll` to see all commands."): return;
            await _close()

        elif self.args[0] == 'clear-display':
            cursor.execute('UPDATE polls SET display = 0')
            await send_text_to_room(self.client, self.room.room_id, "Display cleared.")
            
        else:
            await send_text_to_room(self.client, self.room.room_id, "Unknown command. Send `poll` to see all available commands.  \n")

    async def _vote(self):
        
        cursor = self.store.vconn.cursor()

        cursor.execute('SELECT poll_id, question, anonymous, multiple_choice FROM polls WHERE status = 1')
        poll_details = cursor.fetchone()
        if await self._validate(poll_details, "There is no active poll."): return;
        
        poll_id, question, anonymous, multiple_choice = poll_details

        cursor.execute('SELECT poll_choice_id, choice, marker FROM poll_choices WHERE poll_id = ?', [poll_id])
        poll_choices = cursor.fetchall()
        if await self._validate(poll_choices, "Internal server error: There are no choices for this poll!"): return;
        
        poll_choices.sort(key=lambda x: x[0])

        if not self.args:
            if anonymous:
                cursor.execute('''SELECT poll_choice_id FROM poll_anonym_active_votes WHERE team_code = ?''', [self.user.team])
            else: # not anonymous
                cursor.execute('''SELECT poll_choice_id FROM poll_votes WHERE poll_id = ? AND team_code = ?''', [poll_id, self.user.team])

            choice = cursor.fetchall()
            choices = [c for (c,) in choice] if choice else []

            text = self._get_poll_display(
                poll_id = None, 
                question = question,
                status = None, 
                display = None,
                anonymous = anonymous,
                multiple_choice = multiple_choice,
                poll_choices = poll_choices,
                user_choices = choices,
            )

            text += "  \n\n"
            if multiple_choice:
                text += "Vote by sending: `vote <number> <number> ...`  \n"
                text += "Example: `vote 1 3`  \n"
            else:
                text += "Vote by sending: `vote <number>`  \n"
                text += "Example: `vote 1`  \n"
            text += "You can amend your vote by resending your vote.  \n"
            text += "You can delete your vote by sending `vote delete`.  \n"

            await send_text_to_room(self.client, self.room.room_id, text)
            return

        if len(self.args) == 1:
            if self.args[0].lower() == 'delete':
                if anonymous:
                    cursor.execute('DELETE FROM poll_anonym_active_votes WHERE team_code = ?', [self.user.team])
                else:
                    cursor.execute('DELETE FROM poll_votes WHERE poll_id = ? AND team_code = ?', [poll_id, self.user.team])

                await send_text_to_room(self.client, self.room.room_id, "Your vote has been deleted.")
                return
            
        choices = []
        if multiple_choice:
            if await self._validate(all([len(choice) < 4 and choice.isdigit() for choice in self.args]), "Invalid vote: Every vote must be an integer."): return;
            choices = [int(choice) for choice in self.args]
            
            if await self._validate(all([choice >= 1 and choice <= len(poll_choices) for choice in choices]), f"Invalid vote: Every vote must be between 1 and {len(poll_choices)}."): return;
            if await self._validate(all([choices.count(choice) == 1 for choice in choices]), "Invalid vote: There are duplicates in your vote."): return;
        else:
            if await self._validate(len(self.args) == 1, "Invalid vote: You must vote for exactly one choice."): return;
            if await self._validate(len(self.args[0]) < 4 and self.args[0].isdigit(), "Invalid vote: Your vote must be an integer."): return;
            choices = [int(self.args[0])]
            if await self._validate(choices[0] >= 1 and choices[0] <= len(poll_choices), f"Invalid vote: Your vote must be between 1 and {len(poll_choices)}."): return;

        if anonymous:
            cursor.execute('DELETE FROM poll_anonym_active_votes WHERE team_code = ?', [self.user.team])

            user_choices = [poll_choices[choice - 1][0] for choice in choices]
            for choice in user_choices:
                cursor.execute(
                    '''
                    INSERT INTO poll_anonym_active_votes (poll_choice_id, poll_id, team_code)
                    VALUES (?, ?, ?)
                    ''',
                    [choice, poll_id, self.user.team]
                )
                
        else: # not anonymous
            cursor.execute('DELETE FROM poll_votes WHERE poll_id = ? AND team_code = ?', [poll_id, self.user.team])

            user_choices = [poll_choices[choice - 1][0] for choice in choices]
            for choice in user_choices:
                cursor.execute(
                    '''
                    INSERT INTO poll_votes (poll_choice_id, poll_id, team_code, voted_by, voted_at)
                    VALUES (?, ?, ?, ?, datetime("now", "localtime"))
                    ''',
                    [choice, poll_id, self.user.team, self.user.username]
                )
            
        text = self._get_poll_display(
            poll_id = None, 
            question = question,
            status = None, 
            display = None,
            anonymous = anonymous,
            multiple_choice = multiple_choice,
            poll_choices = poll_choices,
            user_choices = user_choices,
        )
        text += "\n\nYour vote has been recorded as shown above in bold."

        await send_text_to_room(self.client, self.room.room_id, text)

    async def _refresh(self):
        self.store.reload_csv()
        await send_text_to_room(self.client, self.room.room_id, "Successfully refreshed!")

    async def invite(self):
        """Invite all accounts with role to room"""
        if not self.args:
            text = (
                "Usage:"
                "  \n`invite <role> <room id>`: Invite all accounts with role to room"
                "  \n  \nExamples:"
                "  \n- `invite translators !egvUrNsxzCYFUtUmEJ:matrix.ioi2022.id`"
                "  \n- `invite online !egvUrNsxzCYFUtUmEJ:matrix.ioi2022.id`"
            )
            await send_text_to_room(self.client, self.room.room_id, text)
            return


        if self.args[0].lower() == 'translators':
            for index, acc in self.store.leaders.iterrows():
                if acc['Matrix Exists'] == 'Y':
                    if ((acc['Role'] == 'Guest' or acc['Role'] == 'Remote Adjunct (not on site)')
                        and acc['Translating'] == 0
                    ):
                        continue

                    await self.client.room_invite(
                        self.args[1],
                        f"@{acc['UserID']}:{self.config.homeserver_url[8:]}"
                    )
                    await asyncio.sleep(0.25)
                    
        elif self.args[0].lower() == 'online':
            online_countries = set()
            for index, acc in self.store.contestants.iterrows():
                if acc['Online'] == 1:
                    online_countries.add(acc['RealTeamCode'])

            leaders = self.store.leaders
            for country in online_countries:
                leader_accounts = leaders[leaders['RealTeamCode'] == country]
                for index, acc in leader_accounts.iterrows():
                    if acc['Matrix Exists'] == 'Y':
                        await self.client.room_invite(
                            self.args[1],
                            f"@{acc['UserID']}:{self.config.homeserver_url[8:]}"
                        )
                        await asyncio.sleep(0.25)

        await send_text_to_room(self.client, self.room.room_id, "Successfully invited!")

    async def _show_accounts(self):
        if not self.args:
            text = (
                "Usage:  \n\n"
                "- `accounts early-practice`: Show accounts for the early practice contest  \n"
                "- `accounts contest`: Show online contestant accounts for the actual practice/contest days  \n"
                "- `accounts translation`: Show team account for translation system  \n"
            )
            await send_text_to_room(self.client, self.room.room_id, text)
            return

        team_code = self.user.team
        team_country = self.user.country

        if self.args[0].lower() == 'contest':
            contestants = self.store.contestants
            real_team_code = self.user.real_team
            accounts = contestants.loc[contestants['RealTeamCode'] == real_team_code]

            if accounts.empty:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    f"No contestant accounts available for team {team_code} ({team_country}). Please contact HTC for details."
                )
                return

            online_accounts = accounts.loc[accounts['Online'] == 1]

            if online_accounts.empty:
                text = f"All contestants of team {team_code} ({team_country}) are participating on-site."
                text += " We do not distribute contestant accounts for on-site contestants."
                await send_text_to_room(self.client, self.room.room_id, text)
                return

            text = f"Online contestant accounts (`username`: `password`) for team {team_code} ({team_country}):  \n\n"
            for index, account in online_accounts.iterrows():
                text += f"- {account['FirstName']} {account['LastName']}  \n"
                text += f"  `{account['ContestantCode']}`: `{account['Password']}`  \n"

            text += "\n\n These accounts are to be used for actual practice and contest days."

            await send_text_to_room(self.client, self.room.room_id, text)


        elif self.args[0].lower() == 'translation':
            translation = self.store.translation_acc
            account = translation.loc[translation['TeamCode'] == team_code]

            if account.empty:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    f"No translation account available for team {team_code} ({team_country}). Please contact HTC for details."
                )
                return

            text  = f"Translation account (`username`: `password`) for team {team_code} ({team_country}): \n\n"
            text += f"`{team_code}`: `{account.iat[0, 1]}` \n\n"

            await send_text_to_room(self.client, self.room.room_id, text)

        elif self.args[0].lower() == 'early-practice':
            testing = self.store.testing_acc
            real_team_code = self.user.real_team
            accounts = testing.loc[testing['RealTeamCode'] == real_team_code]

            if accounts.empty:
                await send_text_to_room(
                    self.client, self.room.room_id,
                    f"No early practice contest accounts available for team {team_code} ({team_country}). Please contact HTC for details."
                )
                return

            text = f"Early practice contest accounts (`username`: `password`) for team {team_code} ({team_country}): \n\n"
            for index, account in accounts.iterrows():
                text += f"- {account['FirstName']} {account['LastName']}  \n"
                text += f"  `{account['ContestantCode']}`: `{account['Password']}`  \n"
            text += "\n\n These accounts are NOT used for actual contest days."

            await send_text_to_room(self.client, self.room.room_id, text)

        else:
            await send_text_to_room(
                self.client, self.room.room_id,
                "Command format is invalid. Send `accounts` to see all commands."
            )

    async def _objection(self):
        if not self.args:
            text = (
                "Usage:  \n\n"
                "- `!c objection <Optional: Major/Minor> <content>`: Send objection to the SC.  \n\n"
                "Examples:  \n"
                "- `!c objection Major We had a very similar problem in our practice contest!`: Send Major objection to the SC.  \n"
                "- `!c objection It is not specified for the intervals whether they are open or closed`: Send (default) Minor objection to the SC.  \n"
            )
            await send_text_to_room(self.client, self.room.room_id, text)
            return

        if len(self.args) == 0:
            await send_text_to_room(
                self.client, self.room.room_id,
                "Command format is invalid. Send `objection` to see all commands."
            )
            return

        if self.args[0].lower() in ['major', 'minor']:
            severity = self.args[0].lower()
            content = ' '.join(self.args[1:])
        else:
            severity = 'minor'
            content = ' '.join(self.args[0:])


        objection_rooms = self.store.objection_rooms
        sc_room_id = objection_rooms.loc[objection_rooms['Objection Room ID'] == self.room.room_id, ['SC Room ID']]
        if sc_room_id.empty:
            await send_text_to_room(
                self.client, self.room.room_id,
                "This room is not an objection room. Please contact HTC for details."
            )
            return
        sc_room_id = sc_room_id.values[0][0]

        original_post = f"https://matrix.to/#/{self.room.room_id}/{self.event.event_id}?via={self.config.homeserver_url}"
        
        sc_message = (
            f"{'#### Major' if severity == 'major' else '##### *Minor*' }  \n\n"
            f"{content}  \n\n"
            f"Objection from {make_pill(self.user.user_id, self.config.homeserver_url)}  \n"
            f"Original: {original_post}"

        )
        sc_message_response = await send_text_to_room(self.client, sc_room_id, sc_message)

        objection_room_text = (
            "Your objection has been sent to the SC.  \n\n"
            "Please write any further additions for this objection in this thread."
        )
        obj_thread_id = self.event.event_id
        
        cursor = self.store.vconn.cursor()
        cursor.execute('''
            INSERT INTO 
                listening_threads (obj_room_id, sc_room_id, obj_thread_id, sc_thread_id)
                VALUES(?, ?, ?, ?)
        ''', [self.room.room_id, sc_room_id, obj_thread_id, sc_message_response.event_id])
        
        await send_text_to_thread(
            self.client, self.room.room_id,
            objection_room_text,
            reply_to_event_id = obj_thread_id
        )


    async def _get_dropbox(self):
        dropbox_link = self.store.dropbox_url
        team_code = self.user.team
        real_team_code = self.user.real_team
        team_country = self.user.country

        # yyyy/mm/dd format
        if(datetime.now() < datetime(2022, 8, 10)):
            day = 0
        elif(datetime.now() < datetime(2022, 8, 12)):
            day = 1
        else:
            day = 2

        url = dropbox_link.loc[dropbox_link['RealTeamCode'] == real_team_code, ["Day " + str(day)]]
        if url.empty:
            await send_text_to_room(
                self.client, self.room.room_id,
                f"No Dropbox file request link found for team {team_code} ({team_country}). Plase contact HTC for details."
            )
            return
        url = url.values[0]

        text = f"Dropbox upload link for Day {day} for team {team_code} ({team_country}):  \n\n"
        text += url + "  \n\n"

        dbx = self.store.dbx
        try:
            res = dbx.files_list_folder(f"/Uploads/Day {day}/{real_team_code}")
        except Exception as e:
            await send_text_to_room(self.client, self.room.room_id, "No upload folder found.")
            return 

        if not res.entries:
            text += "The folder is empty. Please upload the required files through the link provided above."
            await send_text_to_room(self.client, self.room.room_id, text)
            return

        text += "List of successfully uploaded files:  \n"

        def list_directory(dbx, path, prefix):
            nonlocal text
            res = dbx.files_list_folder(path)
            for entry in res.entries:
                if (isinstance(entry, dropbox.files.FolderMetadata)):
                    list_directory(dbx, path + "/" + entry.name, prefix + entry.name + "/")
                else:
                    text += f"- `{prefix}{entry.name}`  \n"

        list_directory(dbx, f"/Uploads/Day {day}/{real_team_code}", "")

        await send_text_to_room(self.client, self.room.room_id, text)

    async def _get_token(self):
        tokens = self.store.tokens
        token = tokens.loc[tokens['TeamCode'] == self.user.team]

        if token.empty:
            await send_text_to_room(
                self.client, self.room.room_id,
                "There is no token for your team."
            )
        else:
            await send_text_to_room(
                self.client, self.room.room_id,
                f"Token for team {self.user.team}: `{token.iloc[0, 1]}`"
            )

    async def _unknown_command(self):
        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"Unknown command '{self.command}'. Try the 'help' command for more information.",
        )

    async def _validate(self, pred, message):
        """
        Check if pred is true, if not send message to room
        If a function is given than it will be called and if it throws an exception it will treated as validation failure
        
        Returns:
            True if the caller should interrupt the command

        Intended usage:
            if await self._validate(pred, message): return;
        """

        if not pred:
            await send_text_to_room(self.client, self.room.room_id, message)
            return True
        
        return False

def exists(n):
    return n == n
