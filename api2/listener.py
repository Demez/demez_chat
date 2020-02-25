import json
import base64
import socket
from time import time
from threading import Thread
from api2.shared import TimePrint, Decode


class SocketListener(Thread):
    def __init__(self, server, connection: socket) -> None:
        super().__init__()
        self.server = server
        self.socket = connection
        self.connected = False
        self.uuid_verified = False
        self.event_queue = []
        self._stop = False
    
    def Stop(self) -> None:
        self.connected = False
        self._stop = True
    
    def Print(self, string: str) -> None:
        # put ip address here
        # TimePrint(f"Listener - {self.protocol}: {string}")
        TimePrint(f"Listener: {string}")

    def DecodeData(self, encoded_string: bytes) -> bytes:
        # TODO: finish this, need to decode, get json end char,
        #  and add anything after back to the start of the buffer
        #  needs some more changes from the client_listener
        #  commenting out right now just because this commit is already massive enough
        '''
        if self.uuid_verified:
            return Decode(self.server.private_uuid, encoded_string)
        else:
        '''
        final_string = b""
        for string in encoded_string.split(b"=="):
            if not string:
                continue
            final_string += base64.b64decode(string + b"==")
        return final_string
    
    def JsonLoads(self, obj_bytes: bytes) -> bool:
        client_command_json = json.loads(obj_bytes)
        client_command_json["time_received"] = time()
        self.event_queue.append(client_command_json)
        ping = str(round(client_command_json["time_received"] - client_command_json["time_sent"], 6))
        self.Print("Received Packet in " + ping + ": " + str(client_command_json["event"]))
        return True
    
    def _CheckConnection(self, _bytes: bytes) -> bool:
        if not _bytes:
            self.connected = False
            return False
        return True
    
    def run(self) -> None:
        self.connected = True
        while True:
            try:
                client_bytes = self.socket.recv(8192)
                if not self._CheckConnection(client_bytes):
                    break
                self.JsonLoads(self.DecodeData(client_bytes))
            
            # TODO: have this thread be killed when we get here
            except (EOFError, ConnectionAbortedError, ConnectionResetError):
                self.connected = False
                break

            except Exception as F:
                self.Print(str(F))
                # break
                
            if self._stop:
                self.connected = False
                break
