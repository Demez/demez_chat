import os
import json
import base64
import socket
from threading import Thread
from api2.shared import Decode, TimePrint
from time import sleep


def Print(string: str) -> None:
    TimePrint(f"Listener: {string}")


class SocketListener:
    def __init__(self, client_listener, connection: socket, address: str, name: str, private_uuid, public_uuid) -> None:
        self.client = client_listener
        self.private_uuid = private_uuid
        self.public_uuid = public_uuid
        self.server = connection
        self.name = name
        self.combined_address = address  # wait wouldn't this be the same as ip? right now it's ip:port
        self.connected = False
        self.uuid_verified = False
        self.receiving_data = False
        # self.event_queue = []
        self._encoded_buffer = b''
        self._buffer = b''
        
    def SetConnected(self, connected: bool) -> None:
        self.connected = connected
        self.uuid_verified = False if not connected else self.uuid_verified
        self.server.setblocking(not connected)

    def Print(self, string: str) -> None:
        TimePrint(f"{self.combined_address}: {string}")

    def DecodeData(self, encoded_string: bytes):
        # TODO: finish this, need to decode, get json end char,
        #  and add anything after back to the start of the buffer
        #  same with server, except it needs some more changes from this
        #  commenting out right now just because this commit is already massive enough
        '''
        if self.uuid_verified:
            return Decode(self.private_uuid, encoded_string)
        else:
        '''
        return base64.b64decode(encoded_string)

    # IDEA: use regex (maybe?) to split by "{" and "}",
    #  and store the indexes for them, and then count them
    #  instead of going by each character
    @staticmethod
    def GetEndCharIndex(buffer: str) -> int:
        char_index = 0
        depth = 0
        # buffer = self._recv_buf.decode()
        in_quote = False
        
        def PrevChar() -> str:
            if 0 < char_index < len(buffer):
                return buffer[char_index - 1]
            return ""
        
        while char_index < len(buffer):
            char = buffer[char_index]
            if char == '"' and PrevChar() != "\\":
                in_quote = not in_quote
                
            if not in_quote:
                if char in {"{", "["}:
                    depth += 1
                elif char in {"}", "]"}:
                    depth -= 1
        
            char_index += 1
            if depth == 0:
                break
        return char_index

    def JsonBuffer(self) -> bool:
        if not self._buffer:
            return True
        
        char_index = self.GetEndCharIndex(self._buffer.decode("utf-8"))
        try:
            client_command_dict = json.loads(self._buffer[:char_index].decode())
            # self.event_queue.append(client_command_dict)
            self.client.event_queue[self.combined_address].append(client_command_dict)
            self.ClearBuffer(char_index)
            self.Print("received event: " + client_command_dict["event"])
            self.receiving_data = False
            return True
            
        except json.JSONDecodeError as F:
            raise F
            
        except EOFError:
            return False
            
        except Exception as F:
            print(str(F))
            return False
        
    def DecodeBuffer(self) -> None:
        try:
            self._buffer += self.DecodeData(self._encoded_buffer)
            self._encoded_buffer = b''
        except Exception as F:
            print(str(F))
    
    def _CheckConnection(self, _bytes: bytes) -> bool:
        if not _bytes:
            self.connected = False
            self.receiving_data = False
            return False
        self.receiving_data = True
        self.connected = True
        return True

    def ClearBuffer(self, amount: int = 8192) -> None:
        self._buffer = self._buffer[amount:]

    def ReceiveData(self) -> bool:
        try:
            add_bytes = self.server.recv(8192)
            if not self._CheckConnection(add_bytes):
                return False
            self._encoded_buffer += add_bytes
            return True
        except BlockingIOError:
            return True

    def CheckForCommand(self):  # -> Command:
        while True:
            try:
                if not self.ReceiveData():
                    break
                if self._encoded_buffer:
                    self.DecodeBuffer()
                if self.JsonBuffer():
                    break
                
            except (EOFError, ConnectionResetError, ConnectionAbortedError, socket.timeout) as F:
                print(F)
                self.connected = False
                break
                
            except OSError as F:
                # if windows, probably WinError 10038 (An operation was attempted on something that is not a socket)
                if os.name == "nt" and F.errno in (10038, 10057):
                    self.connected = False
                    break
                else:
                    self.Print(str(F))
                    
            except Exception as F:
                self.Print(str(F))
                self.connected = False
                break


class ClientListener(Thread):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client
        self.server_init_list = []
        self.server_list = []
        self.event_queue = {}
        self._stop = False
        
    # def AddServer(self, connection: socket, combined_address: str, name: str) -> None:
    #     self.server_init_list.append(SocketListener(connection, combined_address, name))

    def AddServer(self, connection: socket, address: str, name: str, private_uuid, public_uuid) -> SocketListener:
        socket_listener = SocketListener(self, connection, address, name, private_uuid, public_uuid)
        self.event_queue[socket_listener.combined_address] = []
        self.server_list.append(socket_listener)
        self.server_init_list.append(socket_listener.combined_address)
        return socket_listener
    
    def GetServer(self, address: str) -> SocketListener:
        for server in self.server_list:
            if server.combined_address == address:
                return server

    def ReplaceSocket(self, connection: socket, address: str, name: str) -> None:
        for server in self.server_list:
            if server.combined_address == address:
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
