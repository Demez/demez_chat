import json
import socket
from threading import Thread
from api2.shared import Command, TimePrint


class SocketListener(Thread):
    def __init__(self, protocol: str, connection: socket) -> None:
        super().__init__()
        # TODO: maybe improve this?
        if protocol.casefold() not in ("client", "server"):
            raise Exception("Protocol is either \"client\" or \"server\"")
        self.protocol = protocol
        self.socket = connection
        self.connected = False
        self.command_queue = []
        self._stop = False
    
    def Stop(self) -> None:
        self._stop = True
    
    def Print(self, string: str) -> None:
        TimePrint(f"Listener - {self.protocol}: {string}")
    
    def JsonLoads(self, obj_bytes: bytes) -> bool:
        client_command_json = json.loads(obj_bytes.decode())
        client_command = Command(client_command_json["command"], *client_command_json["args"])
        self.command_queue.append(client_command)
        self.Print("received object: " + str(client_command))
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
                self.JsonLoads(client_bytes)
            
            # TODO: have this thread be killed when we get here
            #  also i only get this on linux
            except EOFError:
                break
                
            except ConnectionAbortedError:
                break

            except Exception as F:
                self.Print(str(F))
                break
                
            if self._stop:
                break
