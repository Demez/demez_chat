import os
import json
import socket
import ftplib
# from uuid import UUID
from threading import Thread
from time import sleep

from api2.shared import *
from api2.client_user_config import UserConfig
from api2.listener import ClientListenerHandler

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
PACKET_VERSION = 2


# TODO: maybe move to another file? like client_server_cache.py?
class ServerCache(BaseClient):
    def __init__(self, client, ip: str, port: int, ftp_port: int,
                 name: str, user_tag: int, private_uuid: str, public_uuid: str):
        super().__init__(self._NewSocket(), ip, port)
        self.client = client
        self.name = name
        self.user_tag = user_tag
        
        self.ftp = FTPClient(self, ip, ftp_port)
        
        self.disabled = False
        self._closing = False
        self._connected = False
        self._uuid_verified = False
        self.private_uuid = private_uuid
        self.public_uuid = public_uuid
        # self.cipher = AES.new(bytes(self.private_uuid), AES.MODE_ECB)
        self.listener = self.client.listener.AddServer(self.socket, self.address, self.name,
                                                       self.private_uuid, self.public_uuid)
        
        self.message_channels = {}  # channel_id: channel_info
        self.channels_voice = {}  # channel_id: channel_info
        self.channels_categories = {}  # category_name: list of channel names in specific order (or freely move them?)
        self.member_list = {}  # public_uuid: user_info

        self.event_function_dict.update({
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
        })

    def SendBytes(self, _bytes: bytes) -> bool:
        try:
            self.socket.send(_bytes)
            return True
        except ConnectionResetError:
            self.Disconnect()
            return False
        
    def IsConnected(self) -> bool:
        return self._connected
        
    def IsClosing(self) -> bool:
        return self._closing

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
            self.listener.SetConnected(True)
            if not self._InitServerKey():
                self.listener.SetConnected(False)
                if not self._closing:
                    self.Disconnect()
                return
            self._uuid_verified = True
            self.listener.uuid_verified = True
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
            while self.user_tag is None:
                TimePrint("Waiting for user tag from server")
                sleep(0.1)
            
            self.RequestFullUpdateWait()
            self._connected = True
            if not self.listener.connected:
                self.Disconnect()
                return
            self.client.RunServerConnectionChangeCallback(self.address, True)
            
            # the server only now stores the uuid, as it also stores the user info with it
            self.client.user_config.SetServerInfo(self.ip, self.port, self.private_uuid,
                                                  self.public_uuid, self.user_tag, self.name)
            
            self.ftp.Connect()

        except (TimeoutError, socket.timeout, ConnectionRefusedError, ConnectionResetError, ConnectionAbortedError):
            self._connected = False
            self._uuid_verified = False
            self.listener.SetConnected(False)
            return

        except OSError as F:
            if os.name == "nt" and F.errno in (10038, 10057):
                self._connected = False
                self._uuid_verified = False
                self.listener.SetConnected(False)
                return
            else:
                print(str(F))
    
        except Exception as F:
            PrintException(F, "Unhandled Exception Connecting To Server: ")
        
    # awful
    def WaitForServerResponse(self) -> Packet:
        try:
            TimePrint("Waiting for server response")
            while True:
                if self.listener.receiving_data:
                    pass
                elif self.client.listener.event_queue[self.address]:
                    event = self.client.listener.event_queue[self.address][0]
                    self.client.listener.event_queue[self.address].remove(event)
                    TimePrint("Got server response")
                    return event
                elif not self.listener.connected:
                    return None
                sleep(0.1)
        except Exception as F:
            PrintException(F, "Unhandled Exception Connecting To Server: ")
            return None
        
    def _InitServerKey(self) -> bool:
        try:
            if self.private_uuid and self.public_uuid:
                if not self.SendPacket("init_uuid", {"private": self.private_uuid, "public": self.public_uuid}):
                    return False
                response = self.WaitForServerResponse()
                if not response:
                    return False
                self.client.listener.server_init_list.remove(self.address)
                if response.event == "valid_uuid":
                    return True
                else:
                    self.SendPacket("fuck")
                    self.Disconnect(response.event)
                    return False
            else:
                if not self.SendPacket("request_uuid"):
                    return False
                response = self.WaitForServerResponse()
                self.client.listener.server_init_list.remove(self.address)
                if response and response.event == "send_uuid":
                    self.private_uuid = response.content["private"]
                    self.public_uuid = response.content["public"]
                    return True
                return False

        except KeyError as F:
            PrintException(F, "KeyError Handling Server Key: ")

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
        self.listener.uuid_verified = False
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
        self.client.listener.ReplaceSocket(self.socket, self.address)
        
    # detach and close doesn't work
    @staticmethod
    def _NewSocket() -> socket:
        socket_ = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_.settimeout(1)  # might be too short of a timeout, idk
        socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return socket_
    
    # =============================================================================================================
    # ALL EVENTS
    
    def HandleDisconnect(self, disconnect: Packet) -> None:
        self.Disconnect(disconnect.content["reason"])

    def ReceiveServerInfo(self, server_info: Packet) -> None:
        self.name = server_info.content["server_name"]

    def ChannelListUpdate(self, channel_list: Packet) -> None:
        self.message_channels = channel_list.content
        for message_channel in self.message_channels:
            self.message_channels[message_channel]["messages"] = {}
            
    def MemberListUpdate(self, member_dict: Packet) -> None:
        # self.member_list = member_dict
        self.member_list.update(member_dict.content["member_list"])
            
    def ReceiveUserTag(self, user_tag: Packet) -> None:
        self.user_tag = user_tag.content["user_tag"]

    def RequestChannelMessageRange(self, channel_name: str, message_index: int, direction: str = "back") -> None:
        if direction not in {"back", "forward"}:
            raise Exception("direction can only be 'back' or 'forward' for message history")
        self.SendPacket("channel_messages", {
            "channel_name": channel_name,
            "message_index": message_index,
            "direction": direction
        })

    def ReceiveChannelMessageRange(self, channel_page: Packet) -> None:
        self.AddMessages(channel_page.content["channel_name"], channel_page.content["messages"])
        
    def AddMessages(self, channel: str, messages: dict) -> None:
        self.message_channels[channel]["messages"].update({int(k): v for k, v in messages.items()})
        self.message_channels[channel]["messages"] = dict(sorted(self.message_channels[channel]["messages"].items()))

    def ReceiveMessage(self, message: Packet) -> None:
        content = message.content
        channel = self.message_channels[content["channel"]]
        add_message = {channel["count"]: (content["time"], content["name"], content["text"], content["file"])}
        self.AddMessages(content["channel"], add_message)

    def SendMessage(self, channel_name: str, message, file: str = "") -> dict:
        # return the time sent
        command_value = {
            "channel": channel_name,
            "time": time(),
            "name": self.public_uuid,
            "text": message,
            "file": file,
        }
        if self.SendPacket("send_message", command_value):
            return command_value


# Wrapper class for FTP with a bit more functionality
# Somewhat based off of os.path and teamspeak 3's ftp gui
# https://www.serv-u.com/features/file-transfer-protocol-server-windows/commands
class FTPClient(ftplib.FTP):
    def __init__(self, parent: ServerCache, ip: str, port: int = 21):
        super().__init__()
        self.parent = parent
        self.ip = ip
        self.port = port
        
        self.file_list = {}
        
        self.uploader = FTPUploader(self)
        self.downloader = FTPDownloader(self)
        
    def Connect(self):
        TimePrint("Connecting to FTP Server...")
        try:
            super().connect(self.ip, self.port)
            super().login(self.parent.public_uuid, self.parent.private_uuid)
        except ftplib.error_perm as F:
            PrintException(F, "FTP Permission Error: ")
        except ftplib.all_errors as F:
            PrintException(F, "FTP Exception: ")
        
        TimePrint("Connected To FTP Server")
        
        self.list_dir()

        self.uploader.start()
        self.downloader.start()
        
    def isfile(self, path: str) -> bool:
        return self.exists(path) and self.file_list[path]["type"] == "file"
        
    def isdir(self, path: str) -> bool:
        return self.exists(path) and self.file_list[path]["type"] == "dir"
    
    def get_size(self, path: str) -> int:
        return 0 if not self.exists(path) else int(self.file_list[path]["size"])
    
    def exists(self, path: str) -> bool:
        return path in self.file_list
    
    def stat(self, path: str) -> dict:
        return self.file_list[path]
    
    def list_dir(self, path: str = "") -> dict:
        if not self.file_list:
            file_list_gen = self.mlsd()
            for file_tuple in file_list_gen:
                self.file_list[file_tuple[0]] = file_tuple[1]
        return self.file_list
        
    def cwd(self, dirname: str):
        super().cwd(dirname)
        self.file_list = {}
        self.list_dir()
        
    def rmd(self, dirname: str):
        super().rmd(dirname)
        name = os.path.basename(dirname)
        if name in self.file_list:
            self.file_list.pop(name)
        
    def download_files(self, output_dir: str, *files):
        [self.download_file(file, output_dir) for file in files]
        
    def upload_files(self, *files):
        self.uploader.queue.extend(files)
        
    def download_file(self, file_path: str, output_dir: str = ""):
        self.downloader.queue.append((file_path, output_dir))
        
    def upload_file(self, file_path: str, directory: str = ""):
        self.uploader.queue.append(file_path)


class FTPBaseTransferThread(Thread):
    def __init__(self, parent: FTPClient):
        super().__init__()
        self.ftp = parent
        self.queue = []
        self.progress = 0.0
        self.file_size = 0
        self.cur_file_path = ""
        self.callback = staticmethod
        
    def process_file(self, file_path: str):
        pass
    
    def run_progress_callback(self, file_path: str, file_progress: float):
        if self.callback:
            self.callback(file_path)
        
    def run(self):
        while True:
            if self.queue:
                self.progress = 0.0
                self.process_file(self.queue[0])
                self.queue.remove(self.queue[0])
            sleep(0.1)
            
            
# TODO: DO THIS CORRECTLY, this is only because this is due tomorrow for senior project,
#  except this will clearly be here for a long time
AWFUL_DL_PATH = "C:/" if os.name == "nt" else "/"


class FTPDownloader(FTPBaseTransferThread):
    def __init__(self, parent: FTPClient):
        super().__init__(parent)
        self.out_file = ""
        self.output_file = ""
        self.out_file_io = None
        
    def file_write(self, data: bytes):
        self.out_file_io.write(data)
        self.progress = os.path.getsize(self.cur_file_path) / int(self.file_size)
        self.run_progress_callback(self.cur_file_path, self.progress)
        
    def process_file(self, file_tuple: tuple):
        # PLACEHOLDER, GET FROM UserInfo IN Client CLASS BELOW
        self.cur_file_path, self.output_file = file_tuple[0], file_tuple[1]
        self.file_size = self.ftp.file_list[self.cur_file_path]["size"]
        with open(self.output_file, "wb") as self.out_file_io:
            self.ftp.retrbinary("RETR " + file_path, self.file_write)


class FTPUploader(FTPBaseTransferThread):
    def __init__(self, parent: FTPClient):
        super().__init__(parent)
        self.blocks_written = 0
        
    def file_read(self, block):
        self.blocks_written += 1024
        self.progress = self.blocks_written / int(self.file_size)
        self.run_progress_callback(self.cur_file_path, self.progress)
        
    def process_file(self, file_path: str):
        self.file_size = self.ftp.file_list[file_path]["size"]
        self.cur_file_path = file_path
        if file_path and os.path.isfile(file_path):
            with open(file_path, "rb") as file_read:
                self.ftp.storbinary(f"STOR {os.path.basename(file_path)}", file_read, 1024, self.file_read)


class Client(Thread):
    def __init__(self) -> None:
        super().__init__()
        self.server_list = []
        self.user_config = UserConfig()  # part of this should probably be disconnected from the client api
        
        self.name = self.user_config.GetUsername()
        self.profile_pic_path = self.user_config.GetProfilePicturePath()
        global AWFUL_DL_PATH
        AWFUL_DL_PATH = self.user_config.user.download
        
        self._event_callbacks = {}
        self._connected_callback = None
        self._is_started = False  # would be _started, but that's used by threading
        self._stopping = False
        self._command_queue = []
        self.listener = ClientListenerHandler(self)
        
        for saved_server in self.user_config.bookmarks:
            self.server_list.append(ServerCache(
                # PLACEHOLDER PORT NUMBER
                self, saved_server.ip, saved_server.port, saved_server.port + 1, saved_server.name,
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
                PrintException(F, "ConnectThread Exception: ")
    
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

    def HandleServerCacheEvent(self, address: str, packet: Packet) -> None:
        server_cache = self.GetServerCache(address)
        if server_cache.HandleEvent(packet):
            if packet.event in self._event_callbacks.keys():
                self._event_callbacks[packet.event](packet)
        else:
            TimePrint("Unknown Event: " + packet.event)
            server_cache.SendPacket("error", {"msg": f"Unknown Event: {packet.event}"})

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
                # listener = self.listener.GetServer(address)
                if not server_cache.listener.connected and server_cache.IsConnected():
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


