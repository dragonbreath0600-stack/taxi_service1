import asyncio
import json


class Broker:
    def __init__(self):
        self.clients = []

    def connect(self, user_id, role):
        queue = asyncio.Queue()
        self.clients.append((user_id, role, queue))
        return queue

    def disconnect(self, queue):
        self.clients = [c for c in self.clients if c[2] is not queue]

    def send(self, event, data, user_id=None, role=None, skip=None):
        message = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for uid, client_role, queue in self.clients:
            if user_id is not None and uid != user_id:
                continue
            if role is not None and client_role != role:
                continue
            if uid == skip:
                continue
            queue.put_nowait(message)


broker = Broker()
