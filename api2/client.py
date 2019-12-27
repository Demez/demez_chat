import pickle
import socket
import os
from uuid import UUID
from threading import Thread
from time import sleep

from api2.shared import *
from api2.client_user_config import UserConfig
from api2.listener import SocketListener

# TODO: try using name decorators here
# TODO: maybe use some sync thing? maybe change client init to sync?


# IDEA: maybe connect to all bookmarked servers so you can be pinged or see if there are new messages or not
# or be in a call while looking at stuff in another server
# i also want to do direct messages, except i don't know how i would handle that
# was thinking of a p2p client, but then you would connect to potentially way too many people
# maybe some modified server you can connect to that will only have direct messages
# or maybe tracker servers or something to host direct messages,
# except the servers would need to sync the info somehow, which seems like it would not work at all


class Client(Thread):
    def __init__(self) -> None:
        super().__init__()
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ping = 0
        self.ip = ""
        self.port = 0
        self.user_config = UserConfig()  # part of this should probably be disconnected from the client api
        self.name = self.user_config.GetUsername()
        self.message_channels = {}  # channel_id: channel_info
        self.commands = {
            "init_channel_list": self.InitChannelList,
            
            "connect": self.Connect,
            "disconnect": self.Disconnect,
            
            "find": self.Find,  # TODO: move to cli_client?
            "ping": self.Ping,
            
            "add_bookmark": self.UnfinishedCommand,
            "rm_bookmark": self.UnfinishedCommand,
            "list_bookmarks": self.UnfinishedCommand,
            
            "list_channels": self.UnfinishedCommand,
            # "view_channel": self.UnfinishedCommand,
            "request_channel_messages": self.RequestChannelMessageRange,
            "receive_channel_messages": self.ReceiveChannelMessageRange,
            "receive_message": self.ReceiveMessage,
            # "send_message": self.SendMessage,
            # "edit_message": self.EditMessage,
            # "remove_message": self.RemoveMessage,
        }
        self._command_callbacks = {}
        self._stopping = False
        self._command_queue = []
        self.listener = SocketListener("client", self.server)

    def ConnectRetry(self, ip: str, port: int, retry_count: int = 4, sleep_time: int = 1) -> bool:
        retry_counter = 0
        while retry_count > retry_counter:
            if self.Connect(ip, port):
                return True
            if retry_count > 0:
                retry_counter += 1
            sleep(sleep_time)
        return False

    # TODO: move this to the seperate thread, along with modifying for multiple server connections
    def Connect(self, ip: str, port: int) -> bool:
        try:
            self.ip, self.port = ip, port
            self.server.connect((self.ip, self.port))
            # maybe have some setup stuff here? idk
            # send or request a uuid
            server_key = self.user_config.GetServerKey(ip, port)
            if server_key:
                self.SendBytes(server_key.bytes)
                is_accepted = self.server.recv(4096).decode()
                if is_accepted == "accepted":
                    pass
                elif is_accepted == "invalid_key":
                    return False
                else:
                    return False
            else:
                self.SendBytes(b'request_uuid')
                new_uuid_bytes = self.server.recv(16)
                new_uuid = UUID(bytes=new_uuid_bytes)
                self.user_config.SetServerKey(ip, port, new_uuid)
            
            TimePrint("Connected to {0}:{1}".format(ip, port))
            self.listener.start()

            while True:
                end_init = False
                while len(self.listener.command_queue) > 0:
                    command = self.listener.command_queue[0]
                    if command.command == "init_finish":
                        end_init = True
                    else:
                        self.RunCommand(command)
                    self.listener.command_queue.remove(self.listener.command_queue[0])
                if end_init:
                    break
                elif not self.listener.connected:
                    return False
            
            self.start()
            return True
        except Exception as F:
            print(str(F))
            return False

    def Disconnect(self) -> None:
        self.server.close()
        self._stopping = True
        TimePrint("Disconnected")
        
    # wait shit fuck this won't work on qt5 because ui stuff needs to be called on the main thread fuck fuck fuck fuck
    # ok bullshit time. the callbacks for qt5 will be functions to emit a signal
    def AddCallback(self, command: str, callback: classmethod) -> None:
        self._command_callbacks[command] = callback
        
    def RunCommandFromExternalThread(self, command: str, *values) -> None:
        cmd = Command(command, *values)
        self._command_queue.append(cmd)

    def RunCommand(self, cmd: Command) -> None:
        if cmd.command in self.commands.keys():
            self.commands[cmd.command](*cmd.args)
            if cmd.command in self._command_callbacks.keys():
                self._command_callbacks[cmd.command](cmd.command, *cmd.args)
        else:
            print("unknown cmd: " + cmd.command)

    def ListBookmarks(self) -> None:
        for bookmark in self.user_config.bookmarks:
            print("\"{0}\" - {1} {2}".format(bookmark.name, bookmark.ip, bookmark.port))

    def Find(self, search: str) -> None:
        result = []
        for con_command in self.commands.keys():
            if search in con_command:
                result.append(con_command)
        if result:
            print(" - " + "\n - ".join(result))
        else:
            print("No results for \"" + search + "\" found")
            
    def InitChannelList(self, channel_list: dict) -> None:
        self.message_channels = channel_list
        for message_channel in self.message_channels:
            self.message_channels[message_channel]["messages"] = {}
    
    def RequestChannelMessageRange(self, channel_name: str, message_index: int, direction: str = "back") -> None:
        if direction not in {"back", "forward"}:
            raise Exception("direction can only be 'back' or 'forward' for message history")
        command = Command("request_channel_messages", channel_name, message_index, direction)
        self.SendObject(command)
    
    def ReceiveChannelMessageRange(self, channel_page: dict) -> None:
        channel = self.message_channels[channel_page["channel_name"]]
        self.AddMessages(channel_page["channel_name"], channel_page["messages"])
        
    # @staticmethod
    def AddMessages(self, channel: str, messages: dict) -> None:
        self.message_channels[channel]["messages"].update(messages)
        self.message_channels[channel]["messages"] = dict(sorted(self.message_channels[channel]["messages"].items()))

    def ReceiveMessage(self, message: dict) -> None:
        channel = self.message_channels[message["channel"]]
        add_message = {channel["message_count"]: (message["time"], message["name"], message["text"], message["file"])}
        self.AddMessages(message["channel"], add_message)

    def SendObject(self, obj) -> None:
        self.SendBytes(pickle.dumps(obj))

    def SendBytes(self, _bytes) -> None:
        self.server.send(_bytes)

    def UnfinishedCommand(self, *args) -> None:
        print("unfinished command")

    def SendMessage(self, channel_name: str, message, file: str = "") -> None:
        command_value = {
            "channel": channel_name,
            "time": GetTimeUnix(),
            "name": self.name,
            "text": message,
            "file": file,
        }
        command = Command("send_message", command_value)
        self.SendObject(command)

    # maybe try using the socket for this?
    def Ping(self) -> int:
        return os.system("ping " + self.ip + ":" + str(self.port))

    def run(self) -> None:
        while True:
            while len(self.listener.command_queue) > 0:
                command = self.listener.command_queue[0]
                self.RunCommand(command)
                self.listener.command_queue.remove(self.listener.command_queue[0])
                
            while len(self._command_queue) > 0:
                command = self._command_queue[0]
                self.RunCommand(command)
                self._command_queue.remove(self._command_queue[0])

            # break if the program is shutting down
            if not self.listener.connected or self._stopping:
                break

            # apparently this loop was causing the cpu usage to go up to 10%
            # and slow the whole program down by a shit ton, so just sleep for 0.1 seconds
            sleep(0.1)

    def Stop(self) -> None:
        self._stopping = True


# maybe useless? idk
class Channel:
    def __init__(self, name, description=""):
        self.name = name
        self.description = description
        self.history = []
        self.pages = -1
        self.page_start = -1
        self.page_end = -1


