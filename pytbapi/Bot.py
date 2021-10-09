#-*- coding:utf-8 -*-

import aiohttp
import asyncio

METHODS_URL = "https://api.telegram.org/bot"
UPDATE_ID = 0

async def Controller(workers, queue, stopMessage, callback):
    global UPDATE_ID
    from pprint import pprint
    while True:
        data = await queue.get()
        for message in data:
            UPDATE_ID = message["update_id"]
        pprint(data)
        queue.task_done()

async def GetUpdate(queue, delay):
    global UPDATE_ID, METHODS_URL

    async with aiohttp.ClientSession() as session:
        while True:
            if UPDATE_ID == 0:
                request = lambda: session.get(METHODS_URL+"getUpdates")
            else:
                request = lambda: session.post(METHODS_URL+"getUpdates", data={
                        "offset": UPDATE_ID + 1
                    })
            async with request() as resp:
                data = await resp.json()
                if "result" in data and len(data["result"]) > 0:
                    await queue.put(data["result"])
            await asyncio.sleep(delay)

async def Main(callback, workers:int, stopMessage:str, delay:int):
    queue = asyncio.Queue()

    await asyncio.gather(
            Controller(workers, queue, stopMessage, callback),
            GetUpdate(queue, delay)
            )

def Listener(token:str, callback, workers=1, stopMessage="exit", delay=0.5):
    global METHODS_URL
    METHODS_URL += token+"/"

    asyncio.run(Main(callback, workers, stopMessage, delay))

def test():
    token = ""
    Listener(token, lambda:print("hello"), 4, "exit")

if __name__ == "__main__":
    test()
