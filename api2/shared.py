import os
import sys
import json
import base64
import platform
import socket
import ipaddress
import traceback
import datetime
from enum import Enum
from time import time


_win32_legacy_con = False
_win32_handle = None

WARNING_COUNT = 0
ERROR_COUNT = 0


class Packet:
    # speed up accessing data, faster than dict (and nicer to use)
    __slots__ = ("event", "desc", "sent", "recv", "content")

    def __init__(self):
        self.event = ""
        self.desc = ""
        self.sent = -1
        self.recv = -1
        self.content = {}
        
    def dict(self) -> dict:
        return {slot: getattr(self, slot) for slot in self.__slots__}
        
        
def PacketFromDict(packet_dict: dict) -> Packet:
    packet = Packet()
    packet.event = packet_dict["event"]
    packet.sent = packet_dict["sent"]
    packet.recv = time()
    packet.content = packet_dict["content"]
    return packet


class BaseListener:
    def __init__(self, parent, connection: socket) -> None:
        self.parent = parent
        self.socket = connection
        # self.socket.setblocking(False)
        self.connected = False
        self.uuid_verified = False
        self._stop = False
        self._encoded_buffer = b''
        self._buffer = b''
    
    def Stop(self) -> None:
        self.connected = False
        self._stop = True
    
    @staticmethod
    def Print(string: str) -> None:
        TimePrint(f"Listener: {string}")
    
    @staticmethod
    def PrintException(f: Exception, string: str) -> None:
        PrintException(f, f"Listener: {string}")
    
    def _CheckConnection(self) -> bool:
        if not self._encoded_buffer:
            self.connected = False
            return False
        return True
    
    def ReceiveData(self) -> bool:
        self._encoded_buffer += self.socket.recv(8192)
        return self._CheckConnection()
    
    @staticmethod
    def DecodeData(encoded_string: bytes) -> bytes:
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
            self.PrintException(F, "Exception Decoding Buffer: ")
            print(str(F))
    
    def ClearBuffer(self, amount: int) -> None:
        self._buffer = self._buffer[amount:]
    
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
    
    def JsonBuffer(self) -> bool:
        if not self._buffer:
            return True
        
        while self._buffer:
            char_index = self.GetEndCharIndex(self._buffer.decode("utf-8"))
            if char_index is None:
                # incomplete, need to call socket.recv again
                VerboseColor(Color.GREEN, "JsonLoads: reached end of file, returning")
                return False
            try:
                packet_dict = json.loads(self._buffer[:char_index].decode())
                packet = PacketFromDict(packet_dict)
                self.AddToEventQueue(packet)
                self.ClearBuffer(char_index)
                ping = str(round(packet.recv - packet.sent, 6))
                self.Print("Received Packet in " + ping + ": " + str(packet.event))
                return True
            
            except json.JSONDecodeError as F:
                raise F
            
            except EOFError as F:
                self.PrintException(F, "EOFError Creating Dict from JSON Packet: ")
                return False
            
            except Exception as F:
                self.PrintException(F, "Exception Creating Dict from JSON Packet: ")
                return False
    
    def AddToEventQueue(self, packet: Packet):
        pass

    def CheckForPackets(self) -> bool:
        if not self._encoded_buffer and not self.ReceiveData():
            return False
        if self._encoded_buffer:
            self.DecodeBuffer()
        self.JsonBuffer()
        return True

    def MainLoop(self):
        while True:
            try:
                result = self.CheckForPackets()
                if not result:
                    break
        
            except (EOFError, ConnectionResetError, ConnectionAbortedError, socket.timeout) as F:
                # self.PrintException(F, "Known Exception checking for Server Packets: ")
                self.Print("Disconnected: " + "".join(traceback.format_exception_only(type(F), F))[:-1])
                self.connected = False
                break
        
            except OSError as F:
                # if windows, probably WinError 10038 (An operation was attempted on something that is not a socket)
                self.PrintException(F, "OSError checking for Server Packets: ")
                if os.name == "nt" and F.errno in (10038, 10057):
                    self.connected = False
                    break
        
            except Exception as F:
                self.PrintException(F, "Exception checking for Server Packets: ")
                self.connected = False
                break


# TODO: combine shared stuff from client.ServerCache and server.ServerClient into here
class BaseClient:
    def __init__(self, connection: socket.socket, ip: str, port: int):
        self.socket = connection
        self.listener = None

        # TODO: test ipv6 support, iirc some changes are needed
        self.ip = ip
        self.port = port
        self._ipv6 = True if ipaddress.ip_address(ip).version == 6 else False
        self.address = f"[{self.ip}]:{self.port}" if self._ipv6 else f"{self.ip}:{self.port}"
        
        self._stopping = False
        self.event_function_dict = {"error": self.HandleError}

    def GetEventList(self) -> list:
        return list(self.event_function_dict)

    def GetEventFunction(self, event: str) -> classmethod:
        try:
            return self.event_function_dict[event]
        except KeyError:
            pass

    def HandleEvent(self, packet: Packet) -> bool:
        if packet.event in self.event_function_dict:
            self.event_function_dict[packet.event](packet)
            return True
        return False
        
    def SendPacket(self, event: str, kwargs: dict = None) -> bool:
        if self._stopping:
            return False
        if not kwargs:
            kwargs = {}
        packet_dict = {
            "event": event,
            "content": kwargs,
            "sent": time(),
            "recv": None,
        }
        TimePrint("Sending Packet: " + event)
        try:
            string = base64.b64encode(json.dumps(packet_dict).encode("utf-8"))
        except Exception as F:
            PrintException(F, "Exception Sending Packet: ")
            return False
        return self.SendBytes(string)

    def SendBytes(self, _bytes: bytes) -> bool:
        try:
            self.socket.send(_bytes)
            return True
        except ConnectionResetError:
            self.Disconnect()
            return False
        except Exception as F:
            PrintException(F, "Exception Sending Bytes: ")
            self.Disconnect()
            return False
            
    def Disconnect(self):
        self.socket.close()
        self.listener.Stop()
        self._stopping = True
        TimePrint(f"Disconnected - {self.address}")
        
    @staticmethod
    def HandleError(packet: Packet):
        PrintError("Packet Error: " + packet.content["msg"])


# https://gist.github.com/gowhari/fea9c559f08a310e5cfd62978bc86a1a
# Vigenere Cipher, not the best for security, but this was the first thing i found and im lazy
def Encode(key, string):
    try:
        encoded_chars = []
        for i in range(len(string)):
            key_c = key[i % len(key)]
            encoded_c = chr(ord(string[i]) + ord(key_c) % 256)
            encoded_chars.append(encoded_c)
        encoded_string = ''.join(encoded_chars)
        encoded_string = encoded_string.encode('latin')  # if six.PY3 else encoded_string
        return base64.urlsafe_b64encode(encoded_string).rstrip(b'=')
    except Exception as F:
        print(str(F))


def Decode(key, string):
    string = base64.urlsafe_b64decode(string + b'===')
    string = string.decode('latin')  # if six.PY3 else string
    encoded_chars = []
    for i in range(len(string)):
        key_c = key[i % len(key)]
        encoded_c = chr((ord(string[i]) - ord(key_c) + 256) % 256)
        encoded_chars.append(encoded_c)
    encoded_string = ''.join(encoded_chars)
    return encoded_string


def GetTime() -> datetime:
    return datetime.datetime.now()


def GetTime24Hour() -> str:
    return GetTime().strftime("%H:%M:%S")


def GetTime12Hour() -> str:
    return GetTime().strftime("%I:%M:%S")


def GetDate() -> str:
    return GetTime().strftime("%Y-%m-%d")


def GetDateAndTime() -> str:
    return GetTime().strftime("%Y-%m-%d %H:%M:%S")


def UnixToDateTime(unix_time: float) -> datetime:
    return datetime.datetime.fromtimestamp(unix_time)


def UnixTo12Hour(unix_time: float) -> str:
    return UnixToDateTime(unix_time).strftime("%I:%M:%S")


def UnixTo24Hour(unix_time: float) -> str:
    return UnixToDateTime(unix_time).strftime("%H:%M:%S")


def IsWindows10() -> bool:
    if platform.platform().startswith("Windows-10"):
        return True
    return False


def TimePrint(*args) -> None:
    sys.stdout.write(f"[{GetDateAndTime()}] {str(*args)}\n")
    
    
def StackTraceNoStandardLib(f: Exception) -> list:
    # stack_trace = traceback.format_stack()
    stack_trace = traceback.format_exc()
    current_dir = os.getcwd()
    
    for index, line in enumerate(stack_trace):
        if os.getcwd() in line:
            new_stack_trace = [*stack_trace[index:-2]]
            return new_stack_trace
    else:
        return stack_trace


def PrintException(f: Exception, *args):
    _PrintSeverity(Severity.ERROR, "", *args, traceback.format_exc())
    global ERROR_COUNT
    ERROR_COUNT += 1


if os.name == "nt":
    if platform.release().startswith("10"):
        # hack to enter virtual terminal mode,
        # could do it properly, but that's a lot of lines and this works just fine
        import subprocess
        subprocess.call('', shell=True)
    else:
        import ctypes
        _win32_handle = ctypes.windll.kernel32.GetStdHandle(-11)
        _win32_legacy_con = True


class Color(Enum):
    if _win32_legacy_con:
        RED = "4"
        DGREEN = "2"
        GREEN = "10"
        YELLOW = "6"
        BLUE = "1"
        MAGENTA = "13"
        CYAN = "3"  # or 9
    
        DEFAULT = "7"
    else:  # ansi escape chars
        RED = "\033[0;31m"
        DGREEN = "\033[0;32m"
        GREEN = "\033[1;32m"
        YELLOW = "\033[0;33m"
        BLUE = "\033[0;34m"
        MAGENTA = "\033[1;35m"
        CYAN = "\033[0;36m"
        
        DEFAULT = "\033[0m"


class Severity(Enum):
    WARNING = Color.YELLOW
    ERROR = Color.RED


def PrintWarning(*text):
    _PrintSeverity(Severity.WARNING, "\n          ", *text)
    global WARNING_COUNT
    WARNING_COUNT += 1


def PrintError(*text):
    _PrintSeverity(Severity.ERROR, "\n        ", *text)
    global ERROR_COUNT
    ERROR_COUNT += 1


def PrintVerbose(*text):
    TimePrint(*text)


def VerboseColor(color: Color, *text):
    PrintColor(color, "".join(text))


def _PrintSeverity(level: Severity, spacing: str, *text):
    PrintColor(level.value, f"[{level.name}] {spacing.join(text)}\n")
    
    
def win32_set_fore_color(color: int):
    if not ctypes.windll.kernel32.SetConsoleTextAttribute(_win32_handle, color):
        print(f"[ERROR] WIN32 Changing Colors Failed, Error Code: {str(ctypes.GetLastError())},"
              f" color: {color}, handle: {str(_win32_handle)}")
    
    
def PrintColor(color: Color, *text):
    if _win32_legacy_con:
        win32_set_fore_color(int(color.value))
        print("".join(text))
        win32_set_fore_color(int(Color.DEFAULT.value))
    else:
        print(color.value + "".join(text) + Color.DEFAULT.value)
    
    
def TimePrintColor(color: Color, *text):
    if _win32_legacy_con:
        sys.stdout.write(f"[{GetDateAndTime()}] ")
        win32_set_fore_color(int(color.value))
        sys.stdout.write(f"{''.join(text)}\n")
        win32_set_fore_color(int(Color.DEFAULT.value))
    else:
        sys.stdout.write(f"[{GetDateAndTime()}] {color.value}{''.join(text)}{Color.DEFAULT.value}\n")

