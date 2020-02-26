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
        # self.socket.setblocking(False)
        self.connected = False
        self.uuid_verified = False
        self.event_queue = []
        self._stop = False
        self._encoded_buffer = b''
        self._buffer = b''
    
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
        # incoming data usually has one = at the end for ones in between (for some reason)
        # but they actually need == at the end, so we split by =, and decode with adding == to the end
        for string in encoded_string.split(b"="):
            if string:
                final_string += base64.b64decode(string + b"==")
        return final_string
    
    def DecodeBuffer(self) -> None:
        try:
            self._buffer += self.DecodeData(self._encoded_buffer)
            self._encoded_buffer = b''
        except Exception as F:
            print(str(F))
            
    def ClearBuffer(self, amount: int) -> None:
        self._buffer = self._buffer[amount:]

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

        if char_index == len(buffer) and buffer[-1] != "}":
            return None
            
        return char_index

    def JsonLoads(self) -> None:
        if not self._buffer:
            return

        while self._buffer:
            char_index = self.GetEndCharIndex(self._buffer.decode("utf-8"))
            if char_index is None:
                break
            try:
                client_command_dict = json.loads(self._buffer[:char_index].decode())
                client_command_dict["time_received"] = time()
                self.event_queue.append(client_command_dict)
                self.ClearBuffer(char_index)
                ping = str(round(client_command_dict["time_received"] - client_command_dict["time_sent"], 6))
                self.Print("Received Packet in " + ping + ": " + str(client_command_dict["event"]))
    
            except json.JSONDecodeError as F:
                raise F
    
            except EOFError:
                return
    
            except Exception as F:
                print(str(F))
    
    def _CheckConnection(self) -> bool:
        if not self._encoded_buffer:
            self.connected = False
            return False
        return True
    
    def ReceiveData(self) -> bool:
        self._encoded_buffer += self.socket.recv(8192)
        return self._CheckConnection()
    
    def run(self) -> None:
        self.connected = True
        while True:
            try:
                if not self._encoded_buffer and not self.ReceiveData():
                    break
                if self._encoded_buffer:
                    self.DecodeBuffer()
                self.JsonLoads()
            
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
