#-*- coding:utf-8 -*-

import aiohttp
import asyncio
from dataclasses import dataclass, is_dataclass as dis_dataclass, asdict as dasdict
from enum import Enum, unique
from threading import Lock as tLock, Thread as tThread
from requests import post as rpost
from json import dumps as jdumps

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

@dataclass
class InlineKeyboardButton:
    text: str
    url: object = None  # str
    login_url: object = None    # str
    callback_data: object = None    # str
    switch_inline_query: object = None    # str
    switch_inline_query_current_chat: object = None    # str
    pay: object = None    # bool

@dataclass
class InlineKeyboardMarkup:
    inline_keyboard: list

def DataclassJSONEncoder(obj):
    if dis_dataclass(obj):
        obj = dasdict(obj)
    if type(obj) == dict:
        clear = {}
        for k,v in obj.items():
            if type(v) == dict or type(v) == list:
                nested = DataclassJSONEncoder(v)
                clear[k] = nested
            elif v is not None:
                clear[k] = v
        return clear
    elif type(obj) == list:
        items = []
        for item in obj:
            if type(item) in [list, dict]:
                nested = DataclassJSONEncoder(item)
                items.append(nested)
            elif item is not None:
                items.append(item)
        return items

def CALLBACK(func):
    def worker_out(message, worker):
        func(message, worker)
        worker.mu.acquire()
        worker.current_count -= 1
        worker.mu.release()
    return worker_out

def Exec(request_type:str, message:Message, text:str, params) -> int:
    URL = METHODS_URL + request_type

    data = None
    if request_type == "sendMessage":
        if text == "": return 1
        data = { "chat_id": message.chat_id, "text": text}
        if "reply_markup" in params:
            data["reply_markup"] = jdumps(DataclassJSONEncoder(params["reply_markup"]))
    elif request_type == "editMessageText":
        # повторяется, т.к. в дальнейшем будут добавлены методы, в которых
        # это поле может быть пустым
        if text == "": return 1
        data = {"chat_id": message.chat_id, "message_id": message.message_id, "text": text}
        if "reply_markup" in params:
            data["reply_markup"] = jdumps(DataclassJSONEncoder(params["reply_markup"]))

    resp = rpost(URL, data=data)
    if not resp.ok:
        print(resp.text)
        return 3
    return 0

async def Controller(workers, queue, stopMessage, callback):
    global UPDATE_ID, STOP

    worker = Workers(0, workers, tLock())

    while True:
        resp_data = await queue.get()
        type_m = MessageType.M_TEXT
        for message in resp_data:
            await asyncio.sleep(0.01)
            while worker.current_count == worker.count: await asyncio.sleep(0.01)
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
    buttons = []
    s = ""
    if message.type_m == MessageType.M_TEXT:
        buttons = [
                [InlineKeyboardButton("1", callback_data="s"),InlineKeyboardButton("2", callback_data="s"),InlineKeyboardButton("3", callback_data="s")],
                [InlineKeyboardButton("4", callback_data="s")],
                [InlineKeyboardButton("5", callback_data="s"),InlineKeyboardButton("6", callback_data="s"),InlineKeyboardButton("7", callback_data="s")],
                ]
        s = "sendMessage"
    elif message.type_m == MessageType.M_CALLBACK:
        buttons = [
                [InlineKeyboardButton("1", callback_data="s"),InlineKeyboardButton("2", callback_data="s"),InlineKeyboardButton("3", callback_data="s")],
                [InlineKeyboardButton("100", callback_data="s")],
                [InlineKeyboardButton("5", callback_data="s"),InlineKeyboardButton("6", callback_data="s"),InlineKeyboardButton("7", callback_data="s")],
                ]
        s = "editMessageText"
    reply_markup = InlineKeyboardMarkup(buttons)
    result = Exec(s, message, "Тестовое сообщение", {"reply_markup": reply_markup})
    print("exec result", result)

def test():
    token = ""
    Listener(token, testCallback, 3, "quit")

if __name__ == "__main__":
    test()
