import pickle
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
        self.command_queue = []
        self._stop = False
    
    def RecvObject(self, _bytes: int = 4096) -> Command:
        return pickle.loads(self.socket.recv(_bytes))
    
    def Stop(self) -> None:
        self._stop = True
    
    def Print(self, string: str) -> None:
        TimePrint(f"Listener - {self.protocol}: {string}")
    
    def run(self) -> None:
        while True:
            try:
                client_bytes = self.socket.recv(4096)
                
                # TODO: make a secure pickle loader, so it can only unload what we want, a Command object
                client_command = pickle.loads(client_bytes)
                self.command_queue.append(client_command)
                self.Print("received object: " + str(client_command))

            # TODO: have this thread be killed when we get here
            #  also i only get this on linux
            except EOFError:
                break

            except Exception as F:
                self.Print(str(F))
                break
                
            if self._stop:
                break
