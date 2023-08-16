import logging

from nio import AsyncClient, MatrixRoom, RoomMessageText

from ioibot.chat_functions import send_text_to_room, react_to_event, send_text_to_thread
from ioibot.config import Config
from ioibot.storage import Storage
from nio.responses import RoomGetEventError


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Message:
    def __init__(
        self,
        client: AsyncClient,
        store: Storage,
        config: Config,
        message_content: str,
        room: MatrixRoom,
        event: RoomMessageText,
    ):
        """Initialize a new Message

        Args:
            client: nio client used to interact with matrix.

            store: Bot storage.

            config: Bot configuration parameters.

            message_content: The body of the message.

            room: The room the event came from.

            event: The event defining the message.
        """
        self.client = client
        self.store = store
        self.config = config
        self.message_content = message_content
        self.room = room
        self.event = event

    async def process(self) -> None:
        """Process and possibly respond to the message"""
        objection_rooms = self.store.objection_rooms
        sc_room_id = objection_rooms.loc[objection_rooms['Objection Room ID'] == self.room.room_id, 'SC Room ID']
        if sc_room_id.empty: return;
        sc_room_id = sc_room_id.values[0]

        # if self.event.source:dict has property content.m.relates_to then grab the object otherwise return
        if 'content' not in self.event.source or 'm.relates_to' not in self.event.source['content']: return;
        if 'rel_type' not in self.event.source['content']['m.relates_to']: return;

        rel_type = self.event.source['content']['m.relates_to']['rel_type']
        if rel_type != 'm.thread': return;
        if 'event_id' not in self.event.source['content']['m.relates_to']: return;

        obj_thread_id = self.event.source['content']['m.relates_to']['event_id']

        cursor = self.store.vconn.cursor()
        db_response = cursor.execute('''
            SELECT 
                sc_thread_id
            FROM
                listening_threads
            WHERE obj_room_id = ? 
                AND sc_room_id = ?
                AND obj_thread_id = ?
        ''', [self.room.room_id, sc_room_id, obj_thread_id]).fetchall()


        if len(db_response) == 0 or type(await self.client.room_get_event(sc_room_id, db_response[0][0])) is RoomGetEventError:
            await react_to_event(self.client, self.room.room_id, self.event.event_id, "❌ failed")
            return  

        sc_thread = db_response[0][0];
        objection_comment = (
            '##### Comment  \n\n'
            f'{self.message_content}  \n\n'
            f'Objection from <a href="https://matrix.to/#/{self.event.sender}">user</a>  \n'
        )

        await send_text_to_thread(
            self.client, sc_room_id,
            objection_comment,
            reply_to_event_id = sc_thread,
        )

        await react_to_event(self.client, self.room.room_id, self.event.event_id, "✅ sent to SC")
