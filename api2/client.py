import os
import json
import socket
import ipaddress
# from uuid import UUID
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


PROTOCOL_VERSION = 1
PACKET_VERSION = 1


# TODO: maybe move to another file? like client_server_cache.py?
class ServerCache:
    def __init__(self, client, ip: str, port: int, name: str, user_tag: int, private_uuid: str, public_uuid: str):
        self.client = client
        self.name = name
        self.user_tag = user_tag

        # TODO: test ipv6 support, iirc some changes are needed
        self.ip = ip
        self.port = port
        self._ipv6 = True if ipaddress.ip_address(ip).version == 6 else False
        self.address = f"[{self.ip}]:{self.port}" if self._ipv6 else f"{self.ip}:{self.port}"
        self.socket = self._NewSocket()
        
        self._closing = False
        self._connected = False
        self._uuid_verified = False
        self.private_uuid = private_uuid
        self.public_uuid = public_uuid
        # self.cipher = AES.new(bytes(self.private_uuid), AES.MODE_ECB)
        self.server_listener = self.client.listener.AddServer(self.socket, self.address, self.name,
                                                              self.private_uuid, self.public_uuid)
        
        self.message_channels = {}  # channel_id: channel_info
        self.channels_voice = {}  # channel_id: channel_info
        self.channels_categories = {}  # category_name: list of channel names in specific order (or freely move them?)
        self.member_list = {}  # public_uuid: user_info

        self._event_function_dict = {
            "disconnect": self.HandleDisconnect,
            "channel_list": self.ChannelListUpdate,
            "member_list": self.MemberListUpdate,
            "server_info": self.ReceiveServerInfo,
            # "send_uuid": self.ReceiveServerInfo,
            "user_tag": self.ReceiveUserTag,
    
            "channel_messages": self.ReceiveChannelMessageRange,
            "receive_message": self.ReceiveMessage,
            "message_sent": self.ReceiveMessage,
            # "message_updated": self.UpdateMessage,
            # "message_removed": self.RemoveMessage,

            # "user_join": self.UserJoin,
            # "user_leave": self.UserLeave,
            # "user_banned": self.UserBanned,
            # "user_kicked": self.UserKicked,
            # "user_display_name_changed": self.UserDisplayNameChanged,
            # "user_profile_pic_changed": self.UserProfilePicChanged,
            # "user_status_changed": self.UserStatusChanged,
            
            # "channel_added": self.ChannelAdded,
            # "channel_edited": self.ChannelEdited,
            # "channel_removed": self.ChannelRemoved,
        }
        
    def SendPacket(self, content: str, kwargs: dict = None) -> bool:
        if self._closing:
            return False
        if not kwargs:
            kwargs = {}
        cmd_dict = {
            "event": content,
            "content": kwargs,
            "time_sent": time(),
            "time_received": None,
            "packet_version": PACKET_VERSION,
        }
        try:
            string = self.EncodeData(json.dumps(cmd_dict))
        except Exception as F:
            print(str(F))
            return False
        return self.SendBytes(string)

    def SendBytes(self, _bytes: bytes) -> bool:
        try:
            self.socket.send(_bytes)
            return True
        except ConnectionResetError:
            self.Disconnect()
            return False
            
    def EncodeData(self, json_string: str):
        # look at listener decode function
        '''
        if self._uuid_verified:
            encoded = Encode(self.private_uuid, json_string)
        else:
        '''
        # use base64 until the server verifies/sends the UUID
        encoded = base64.b64encode(json_string.encode("utf-8"))
        return encoded
        
    def GetEventList(self) -> list:
        return list(self._event_function_dict)
        
    def GetEventFunction(self, event: str) -> classmethod:
        try:
            return self._event_function_dict[event]
        except KeyError:
            pass
        
    def HandleEvent(self, cmd: dict) -> bool:
        try:
            self._event_function_dict[cmd["event"]](cmd["content"])
            return True
        except KeyError as F:
            print(F)
            return False
        
    def IsConnected(self) -> bool:
        return self._connected
        
    def IsClosing(self) -> bool:
        return self._closing

    # how would you add connecting to the ftp server here?
    def Connect(self) -> None:
        try:
            TimePrint("Trying to connect to \"" + self.address + '"')
            # self.socket.connect((self.ip, self.port))
            thing = self.socket.connect_ex((self.ip, self.port))
            if thing != 0 and thing != 10035:
                # maybe?
                self._UpdateSocket()
                return
            # send or request a uuid
            self.server_listener.SetConnected(True)
            if not self._InitServerKey():
                self.server_listener.SetConnected(False)
                if not self._closing:
                    self.Disconnect()
                return
            self._uuid_verified = True
            self.server_listener.uuid_verified = True
            TimePrint("Connected to {0}".format(self.address))

            user_info_dict = {
                "username": self.client.name,
                # "profile_picture_path": self.client.profile,
            }
            
            if self.user_tag:
                user_info_dict.update({"user_tag": self.user_tag})
            
            if not self.SendPacket("user_info", user_info_dict):
                self.Disconnect()
                return
            
            # wait for the server to give us a tag
            if self.user_tag is None:
                self.HandleEvent(self.WaitForServerResponse())
            
            self.RequestFullUpdateWait()
            self._connected = True
            if not self.server_listener.connected:
                self.Disconnect()
                return
            self.client.RunServerConnectionChangeCallback(self.address, True)
            
            # the server only now stores the uuid, as it also stores the user info with it
            self.client.user_config.SetServerInfo(self.ip, self.port, self.private_uuid,
                                                  self.public_uuid, self.user_tag, self.name)

        except (TimeoutError, socket.timeout, ConnectionRefusedError, ConnectionResetError, ConnectionAbortedError):
            self._connected = False
            self._uuid_verified = False
            self.server_listener.SetConnected(False)
            return

        except OSError as F:
            if os.name == "nt" and F.errno in (10038, 10057):
                self._connected = False
                self._uuid_verified = False
                self.server_listener.SetConnected(False)
                return
            else:
                print(str(F))
    
        except Exception as F:
            print(str(F))
        
    def WaitForServerResponse(self) -> dict:
        try:
            while True:
                if self.server_listener.receiving_data:
                    print("receiving data oh shit")
                elif self.client.listener.event_queue[self.address]:
                    event = self.client.listener.event_queue[self.address][0]
                    self.client.listener.event_queue[self.address].remove(event)
                    return event
                elif not self.server_listener.connected:
                    return {}
                sleep(0.1)
        except Exception as F:
            print(str(F))
            return {}
        
    def _InitServerKey(self) -> bool:
        try:
            if self.private_uuid and self.public_uuid:
                if not self.SendPacket("init_uuid", {"private": self.private_uuid, "public": self.public_uuid}):
                    return False
                response = self.WaitForServerResponse()
                if not response:
                    return False
                self.client.listener.server_init_list.remove(self.address)
                if response["event"] == "valid_uuid":
                    return True
                else:
                    self.SendPacket("fuck")
                    self.Disconnect(response["event"])
                    return False
            else:
                if not self.SendPacket("request_uuid"):
                    return False
                response = self.WaitForServerResponse()
                self.client.listener.server_init_list.remove(self.address)
                if response["event"] == "send_uuid":
                    self.private_uuid = response["content"]["private"]
                    self.public_uuid = response["content"]["public"]
                    return True

        except KeyError as F:
            print(str(F))

    # useless?
    def RequestFullUpdateWait(self) -> None:
        self.SendPacket("full_update")
        '''
        while True:
            event = self.WaitForServerResponse()
            if event["event"] == "full_update_finished":
                break
            else:
                self.HandleEvent(event)
        '''
        
    def Disconnect(self, reason: str = "") -> None:
        self._closing = True
        self._connected = False
        self._uuid_verified = False
        self.server_listener.uuid_verified = False
        if reason:
            TimePrint("Disconnected: " + reason)
        else:
            TimePrint("Disconnected")
        self.client.RunServerConnectionChangeCallback(self.address, False)
        self._UpdateSocket()
        self._closing = False
        
    def _UpdateSocket(self):
        self.socket.close()
        self.socket = self._NewSocket()
        self.client.listener.server_init_list.append(self.address)
        self.client.listener.ReplaceSocket(self.socket, self.address, "")
        
    # detach and close doesn't work
    @staticmethod
    def _NewSocket() -> socket:
        socket_ = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_.settimeout(1)  # might be too short of a timeout, idk
        socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return socket_
    
    def HandleDisconnect(self, disconnect: dict) -> None:
        self.Disconnect(disconnect["reason"])

    def ReceiveServerInfo(self, server_info: dict) -> None:
        self.name = server_info["server_name"]

    def ChannelListUpdate(self, channel_list: dict) -> None:
        self.message_channels = channel_list
        for message_channel in self.message_channels:
            self.message_channels[message_channel]["messages"] = {}
            
    def MemberListUpdate(self, member_dict: dict) -> None:
        # self.member_list = member_dict
        self.member_list.update(member_dict["member_list"])
            
    def ReceiveUserTag(self, user_tag: dict) -> None:
        self.user_tag = user_tag["user_tag"]

    def RequestChannelMessageRange(self, channel_name: str, message_index: int, direction: str = "back") -> None:
        if direction not in {"back", "forward"}:
            raise Exception("direction can only be 'back' or 'forward' for message history")
        self.SendPacket("channel_messages", {
            "channel_name": channel_name,
            "message_index": message_index,
            "direction": direction
        })

    def ReceiveChannelMessageRange(self, channel_page: dict) -> None:
        # channel = self.message_channels[channel_page["channel_name"]]
        self.AddMessages(channel_page["channel_name"], channel_page["messages"])
        
    def AddMessages(self, channel: str, messages: dict) -> None:
        self.message_channels[channel]["messages"].update({int(k): v for k, v in messages.items()})
        self.message_channels[channel]["messages"] = dict(sorted(self.message_channels[channel]["messages"].items()))

    def ReceiveMessage(self, message: dict) -> None:
        content = message["content"]
        channel = self.message_channels[content["channel"]]
        add_message = {channel["message_count"]: (content["time"], content["name"], content["text"], content["file"])}
        self.AddMessages(content["channel"], add_message)

    def SendMessage(self, channel_name: str, message, file: str = "") -> None:
        command_value = {
            "channel": channel_name,
            "time": GetTimeUnix(),  # probably useless
            "name": self.public_uuid,
            "text": message,
            "file": file,
        }
        self.SendPacket("send_message", command_value)


class Client(Thread):
    def __init__(self) -> None:
        super().__init__()
        self.server_list = []
        self.user_config = UserConfig()  # part of this should probably be disconnected from the client api
        
        self.name = self.user_config.GetUsername()
        self.profile_pic_path = self.user_config.GetProfilePicturePath()
        self._event_callbacks = {}
        self._connected_callback = None
        self._is_started = False  # would be _started, but that's used by threading
        self._stopping = False
        self._command_queue = []
        self.listener = ClientListener(self)
        
        for saved_server in self.user_config.bookmarks:
            self.server_list.append(ServerCache(
                self, saved_server.ip, saved_server.port, saved_server.name,
                saved_server.user_tag, saved_server.private_uuid, saved_server.public_uuid))
            
        self.listener.start()
        
    def _ConnectThread(self):
        while True:
            try:
                for server in self.server_list:
                    if not server.IsConnected() and not server.IsClosing():
                        if server.address not in self.listener.server_init_list:
                            self.listener.server_init_list.append(server.address)
                        server.Connect()
                sleep(4)
            except Exception as F:
                print("ConnectThread: " + str(F))
    
    def SetServerConnectionChangeCallback(self, func: classmethod) -> None:
        self._connected_callback = func
        
    def HasServerConnectionChangeCallback(self) -> bool:
        return bool(self._connected_callback)
        
    def RunServerConnectionChangeCallback(self, address: str, connected: bool) -> None:
        if self._connected_callback:
            self._connected_callback(address, connected)
        
    def AddCallback(self, command: str, callback: classmethod) -> None:
        self._event_callbacks[command] = callback
        
    def GetServerCache(self, address: str) -> ServerCache:
        for server in self.server_list:
            if server.address == address:
                return server

    def HandleServerCacheEvent(self, address: str, cmd: dict) -> None:
        server_cache = self.GetServerCache(address)
        if server_cache.HandleEvent(cmd):
            if cmd["event"] in self._event_callbacks.keys():
                self._event_callbacks[cmd["event"]](cmd["event"], cmd["content"])
        else:
            TimePrint("unknown event: " + cmd["event"])

    def run(self) -> None:
        connect_thread = Thread(name="ConnectThread", target=self._ConnectThread)
        connect_thread.start()
        while True:
            for server_cache in self.server_list:
                address = server_cache.address
                # maybe change to server_wait_list, for if we are waiting for a response and don't want it caught here
                # or could just run a function to set a bool, but that's ugly
                if address in self.listener.server_init_list:
                    continue
                    
                # check if server is still up through listener
                # server_listener = self.listener.GetServer(address)
                if not server_cache.server_listener.connected and server_cache.IsConnected():
                    self.listener.event_queue[address].clear()
                    server_cache.Disconnect()
                    continue
                    
                while len(self.listener.event_queue[address]) > 0:
                    command = self.listener.event_queue[address][0]
                    self.HandleServerCacheEvent(address, command)
                    self.listener.event_queue[address].remove(self.listener.event_queue[address][0])

                # break if the program is shutting down
                # if not self.listener.connected or self._stopping:
                if self._stopping:
                    break

            # apparently this loop was causing the cpu usage to go up to 10%
            # and slow the whole program down by a shit ton, so just sleep for 0.1 seconds
            sleep(0.1)

    def Stop(self) -> None:
        self._stopping = True


