import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
import certifi
import socket

# Force IPv4
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [response for response in responses if response[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo

async def main():
    mongo_url = "mongodb+srv://tusharc0702_db_user:MZhegFH8iAYjjn45@oditr-waitlist.ykunkhy.mongodb.net/?appName=oditr-waitlist"
    client = AsyncIOMotorClient(mongo_url, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
    try:
        info = await client.server_info()
        print("SUCCESS:", info)
    except Exception as e:
        print("ERROR:", e)

asyncio.run(main())
