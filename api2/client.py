import pickle
import socket
import os
from uuid import UUID
from threading import Thread
from time import sleep

from api2.shared import *
from api2.client_user_config import UserConfig
from api2.client_listener import ClientListener

# TODO: try using name decorators here
# TODO: maybe use some sync thing? maybe change client init to sync?


# IDEA: maybe connect to all bookmarked servers so you can be pinged or see if there are new messages or not
# or be in a call while looking at stuff in another server
# i also want to do direct messages, except i don't know how i would handle that
# was thinking of a p2p client, but then you would connect to potentially way too many people
# maybe some modified server you can connect to that will only have direct messages
# or maybe tracker servers or something to host direct messages,
# except the servers would need to sync the info somehow, which seems like it would not work at all


# TODO: maybe move to another file? like client_server_cache.py?
class ServerCache:
    def __init__(self, client, ip: str, port: int, name: str):
        self.client = client
        self.name = name
        self.ip = ip
        self.port = port
        self.address = ip + ":" + str(port)
        self.socket = self.NewSocket()
        self.message_channels = {}  # channel_id: channel_info
        self._connected = False

        self.server_listener = self.client.listener.AddServer(self.socket, self.address, "")

        # TODO: maybe make this an enum?
        # these are _commands the server can call on the client, not for use in the client (maybe?)
        self._commands = {
            "connected": self.IsConnected,
            
            "init_channel_list": self.InitChannelList,
            "recv_server_name": self.UnfinishedCommand,
    
            # "send_profile_pic": self.UnfinishedCommand,
            # "send_username": self.UnfinishedCommand,
    
            "list_channels": self.UnfinishedCommand,
            # "view_channel": self.UnfinishedCommand,
            # "request_channel_messages": self.RequestChannelMessageRange,
            "receive_channel_messages": self.ReceiveChannelMessageRange,
            "receive_message": self.ReceiveMessage,
            # "update_message": self.UpdateMessage,
            # "remove_message": self.RemoveMessage,
        }

    def SendObject(self, obj) -> None:
        self.SendBytes(pickle.dumps(obj))

    def SendBytes(self, _bytes: bytes) -> None:
        try:
            self.socket.send(_bytes)
        except ConnectionResetError:
            self.Disconnect()
        
    def GetCommandList(self) -> list:
        return list(self._commands)
        
    def GetCommandFunction(self, command: str) -> classmethod:
        try:
            return self._commands[command]
        except KeyError:
            pass
        
    def RunCommand(self, cmd: Command) -> bool:
        try:
            self._commands[cmd.command](*cmd.args)
            return True
        except KeyError:
            return False

    def UnfinishedCommand(self, *args) -> None:
        print("unfinished command")
        
    def IsConnected(self) -> bool:
        return self._connected

    # TODO: this is slowing the main loop down a lot
    # maybe have another connect loop thread, for checking connections and shit?
    def Connect(self) -> None:
        try:
            TimePrint("Trying to connect to \"" + self.address + '"')
            self.socket.connect_ex((self.ip, self.port))
            # maybe have some setup stuff here? idk
            # send or request a uuid
            if not self._InitServerKey():
                return
        
            TimePrint("Connected to {0}:{1}".format(self.ip, self.port))
            self._ClientInit()
            self._connected = True
            self.client.RunServerConnectionChangeCallback(self.address, True)
        except TimeoutError:
            return
        
        except socket.timeout:
            return
        
        except ConnectionRefusedError:
            self._connected = False
            return
    
        except Exception as F:
            # self.socket.close()
            print(str(F))

    def _InitServerKey(self) -> bool:
        server_key = self.client.user_config.GetServerKey(self.ip, self.port)
        if server_key:
            self.socket.send(server_key.bytes)
            is_accepted = self.socket.recv(1)
            if is_accepted == b"1":
                return True
            elif is_accepted == b"0":
                return False
            else:
                return False
        else:
            self.socket.send(b'request_uuid')
            new_uuid_bytes = self.socket.recv(16)
            new_uuid = UUID(bytes=new_uuid_bytes)
            self.client.user_config.SetServerKey(self.ip, self.port, new_uuid)
            return True

    def _ClientInit(self) -> bool:
        # TODO: this won't work for IPv6
        address_port = self.ip + ":" + str(self.port)
        self.server_listener.SetConnected(True)
        listener = self.client.listener
        while True:
            end_init = False
            while len(listener.command_queue[address_port]) > 0:
                command = listener.command_queue[address_port][0]
                if command.command == "init_finish":
                    end_init = True
                else:
                    self.RunCommand(command)
                listener.command_queue[address_port].remove(listener.command_queue[address_port][0])
            if end_init:
                break
            elif not self.server_listener.connected:
                return False
        return True

    def Disconnect(self) -> None:
        self._connected = False
        TimePrint("Disconnected")
        self.client.RunServerConnectionChangeCallback(self.address, False)
        self.socket.close()
        self.socket = self.NewSocket()
        self.client.listener.ReplaceSocket(self.socket, self.address, "")
        
    # detach and close doesn't work
    @staticmethod
    def NewSocket() -> socket:
        socket_ = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_.settimeout(1)  # might be too short of a timeout, idk
        socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return socket_

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

    def SendMessage(self, channel_name: str, message, file: str = "") -> None:
        command_value = {
            "channel": channel_name,
            "time": GetTimeUnix(),
            "name": self.client.name,
            "text": message,
            "file": file,
        }
        command = Command("send_message", command_value)
        self.SendObject(command)


class Client(Thread):
    def __init__(self) -> None:
        super().__init__()
        self.server_list = []
        self.user_config = UserConfig()  # part of this should probably be disconnected from the client api
        
        self.name = self.user_config.GetUsername()
        self._command_callbacks = {}
        self._connected_callback = None
        self._is_started = False  # would be _started, but that's used by threading
        self._stopping = False
        self._command_queue = []
        self.listener = ClientListener(self)
        
        for saved_server in self.user_config.bookmarks:
            self.server_list.append(ServerCache(self, saved_server.ip, saved_server.port, saved_server.name))
            
        self.listener.start()
        
    def _Connect(self):
        for server in self.server_list:
            if not server.IsConnected():
                server.Connect()
        
    def _ConnectThread(self):
        while True:
            for server in self.server_list:
                if not server.IsConnected():
                    server.Connect()
            sleep(4)
    
    def SetServerConnectionChangeCallback(self, func: classmethod) -> None:
        self._connected_callback = func
        
    def HasServerConnectionChangeCallback(self) -> bool:
        if self._connected_callback:
            return True
        return False
        
    def RunServerConnectionChangeCallback(self, address: str, connected: bool) -> None:
        if self._connected_callback:
            self._connected_callback(address, connected)
        
    def AddCallback(self, command: str, callback: classmethod) -> None:
        self._command_callbacks[command] = callback
        
    def GetServerCache(self, address: str) -> ServerCache:
        for server in self.server_list:
            if server.address == address:
                return server
        
    def RunCommandFromExternalThread(self, command: str, *values) -> None:
        cmd = Command(command, *values)
        self._command_queue.append(cmd)

    def RunServerCacheCommand(self, address: str, cmd: Command) -> None:
        server_cache = self.GetServerCache(address)
        if server_cache.RunCommand(cmd):
            if cmd.command in self._command_callbacks.keys():
                self._command_callbacks[cmd.command](cmd.command, *cmd.args)
        else:
            print("unknown cmd: " + cmd.command)

    def run(self) -> None:
        connect_thread = Thread(name="ConnectThread", target=self._ConnectThread)
        connect_thread.start()
        while True:
            for address in self.listener.command_queue:
                while len(self.listener.command_queue[address]) > 0:
                    command = self.listener.command_queue[address][0]
                    self.RunServerCacheCommand(address, command)
                    self.listener.command_queue[address].remove(self.listener.command_queue[address][0])

            # TODO: set this up as well with functions to AddCommandToQueue or something
            '''
            for combined_address in self._command_queue:
                while len(self._command_queue[combined_address]) > 0:
                    command = self._command_queue[combined_address][0]
                    self.RunServerCacheCommand(combined_address, command)
                    self._command_queue[combined_address].remove(self._command_queue[combined_address][0])
            '''

            # break if the program is shutting down
            # if not self.listener.connected or self._stopping:
            if self._stopping:
                break

            # apparently this loop was causing the cpu usage to go up to 10%
            # and slow the whole program down by a shit ton, so just sleep for 0.1 seconds
            sleep(0.1)

    def Stop(self) -> None:
        self._stopping = True


