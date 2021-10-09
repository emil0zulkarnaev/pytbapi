#-*- coding:utf-8 -*-

import aiohttp
import asyncio
from dataclasses import dataclass
from enum import Enum, unique
from threading import Lock as tLock, Thread as tThread

METHODS_URL = "https://api.telegram.org/bot"
UPDATE_ID = 0
STOP = False

@unique
class MessageType(Enum):
    M_TEXT = 1
    M_CALLBACK = 2
    M_COMMAND = 3

@dataclass
class Workers:
    current_count: int
    count: int
    mu: object

@dataclass
class Message:
    first_name: str
    username: str
    id_: str
    chat_id: str
    text: str
    type_m: MessageType
    message_id: str
    data: str
    callback_query_id: str

def CALLBACK(func):
    def worker_out(message, worker):
        func(message, worker)
        worker.mu.acquire()
        worker.current_count -= 1
        worker.mu.release()
    return worker_out


async def Controller(workers, queue, stopMessage, callback):
    global UPDATE_ID, STOP

    worker = Workers(0, workers, tLock())

    while True:
        resp_data = await queue.get()
        type_m = MessageType.M_TEXT
        for message in resp_data:
            await asyncio.sleep(0.01)
            if worker.current_count > 0: continue
            type_m = MessageType.M_TEXT
            data = ""
            callback_query_id = ""
            row = message
            if "message" not in message:
                if "callback_query" in message:
                    row = message["callback_query"]
                    data = row["data"]
                    callback_query_id = row["id"]
                    type_m = MessageType.M_CALLBACK
                else: continue
            message_ = row["message"]
            from_ = message_["from"]
            chat  = message_["chat"]

            ####################################
            # временная мера
            if "text" not in message_: continue
            if "entities" in message_ and type_m != MessageType.M_CALLBACK:
                entities = message_["entities"]
                lst = entities[0]
                if lst["type"] == "bot_command":
                    type_m = MessageType.M_COMMAND
                else: continue
            ####################################

            if message_["text"] == stopMessage:
                STOP = True
                break

            while worker.current_count == worker.count: await asyncio.sleep(0.01)
            worker.current_count += 1
            tThread(target=callback, args=(Message(
                from_["first_name"],
                from_["username"],
                from_["id"],
                chat["id"],
                message_["text"],
                type_m,
                message_["message_id"],
                data,
                callback_query_id
                ), worker,)).start()
        if STOP: break
        if len(resp_data) > 0:
            UPDATE_ID = resp_data[-1]["update_id"]
        queue.task_done()

async def GetUpdate(queue, delay):
    global UPDATE_ID, METHODS_URL, STOP

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
            if STOP: break

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

@CALLBACK
def testCallback(message, worker):
    print("here!", worker)

def test():
    token = ""
    Listener(token, testCallback, 4, "quit")

if __name__ == "__main__":
    test()
