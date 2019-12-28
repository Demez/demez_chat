import pickle
import socket
from threading import Thread
from api2.shared import Command, TimePrint
from time import sleep


def Print(string: str) -> None:
    TimePrint(f"Listener: {string}")


class SocketListener:
    def __init__(self, client_listener, connection: socket, address: str, name: str = "") -> None:
        self.client = client_listener
        self.server = connection
        self.name = name
        self.combined_address = address  # wait wouldn't this be the same as ip? right now it's ip:port
        self.connected = False
        self._recv_buf = b''
        
    def SetConnected(self, connected: bool):
        self.connected = connected
        self.server.setblocking(not connected)

    def Print(self, string: str) -> None:
        TimePrint(f"Listener - {self.combined_address}: {string}")

    # TODO: make a secure pickle loader, so it can only unload what we want, a Command object
    def UnpickleBuffer(self) -> bool:
        if not self._recv_buf:
            return True
        char = 3
        while True:
            try:
                client_bytes = self._recv_buf[:char]
                client_command = pickle.loads(client_bytes)
                self.client.command_queue[self.combined_address].append(client_command)
                self.ClearBuffer(char)
                self.Print("received object: " + str(client_command))
                return True
            
            except pickle.UnpicklingError:
                char += 1
                continue
                
            except EOFError:
                char += 1
                continue
    
    def _CheckConnection(self, _bytes: bytes) -> bool:
        if not _bytes:
            self.connected = False
            return False
        self.connected = True
        return True

    def ClearBuffer(self, amount: int = 8192) -> None:
        self._recv_buf = self._recv_buf[amount:]

    def ReceiveData(self) -> bool:
        try:
            add_bytes = self.server.recv(8192)
            if not self._CheckConnection(add_bytes):
                return False
            self._recv_buf += add_bytes
            return True
        except BlockingIOError:
            return True

    def CheckForCommand(self):  # -> Command:
        while True:
            try:
                if not self.ReceiveData():
                    break
                if self.UnpickleBuffer():
                    break
                        
            # except BlockingIOError:
            #     return None
            
            except EOFError:
                break
                
            except ConnectionResetError:
                self.connected = False
                break
        
            except Exception as F:
                self.Print(str(F))


class ClientListener(Thread):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client
        self.server_init_list = []
        self.server_list = []
        self.command_queue = {}
        self._stop = False
        
    # def AddServer(self, connection: socket, combined_address: str, name: str) -> None:
    #     self.server_init_list.append(SocketListener(connection, combined_address, name))

    def AddServer(self, connection: socket, address: str, name: str) -> SocketListener:
        socket_listener = SocketListener(self, connection, address, name)
        self.command_queue[socket_listener.combined_address] = []
        self.server_list.append(socket_listener)
        # self.server_init_list.append(socket_listener)
        return socket_listener

    def ReplaceSocket(self, connection: socket, address: str, name: str) -> None:
        for server in self.server_list:
            if server.combined_address == address and server.name == name:
                server.server = connection
    
    def Stop(self) -> None:
        self._stop = True
    
    # is this slowing the program down?
    def run(self) -> None:
        while True:
            if self._stop:
                break
                
            for server in self.server_list:
                if server.connected:
                    server.CheckForCommand()
                    
            sleep(0.1)
