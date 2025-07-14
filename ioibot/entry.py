#!/usr/bin/env python3

import asyncio

from ioibot import http_server
from ioibot import main as bot
from ioibot.create_database import create_database

def main():
    # Create ioibot.db used in the bot and http server
    create_database()

    # Run http server and main function of the bot
    task = asyncio.gather(http_server.main(), bot.main())
    asyncio.get_event_loop().run_until_complete(task)

if __name__ == '__main__':
    main()
