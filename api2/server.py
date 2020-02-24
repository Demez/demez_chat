import os
import json
import base64
import socket
import sqlite3
import datetime
from time import time, sleep
from dkv import demez_key_values as dkv
from uuid import uuid4, UUID
from threading import Thread
from api2.shared import Encode, TimePrint
from api2.listener import SocketListener
from api2.dir_tools import CreateDirectory

# ----- These are needed for comparing client and server version -----
# update this whenever the json dict format or encoding/decoding is changed,
#  like something that won't be compatible across versions in SendPacket and/or Listener is changed
PROTOCOL_VERSION = 1
PACKET_VERSION = 1

# how messages are sent/displayed,
MESSAGE_VERSION = 1
USER_INFO_VERSION = 1

SERVER_CONFIG_PATH = "server_config.dkv"
CreateDirectory("channels")


class ServerClient(Thread):
    def __init__(self, server, client, address) -> None:
        super().__init__()
        # we can wait for events on multiple sockets and then read and write data when it’s ready
        client.setblocking(True)  # maybe try designing this with this set to false?
        self.client = client
        self.address = address
        self.server = server

        self.private_uuid = None
        self.public_uuid = None
        self.username = None
        self.user_tag = None
        self._uuid_verified = False

        self.listener = SocketListener(self, client)
        self.listener.start()
        self._stopping = False
        self.event_function_dict = {
            "init_uuid": self.InitCheckUUID,
            "request_uuid": self.InitRequestUUID,
            "init_version": self.InitVersionCheck,
            "user_info": self.ReceiveUserInfo,
            "full_update": self.FullUpdate,

            "receive_message": self.ReceiveMessage,
            "send_message": self.ReceiveMessage,
            "channel_messages": self.SendChannelMessageRange,
        }
        
        # self.FullUpdate()

    def SendPacket(self, event: str, kwargs: dict = None) -> None:
        if self._stopping:
            return
        if not kwargs:
            kwargs = {}
        cmd_dict = {
            "event": event,
            "content": kwargs,
            # "time_sent": datetime.datetime.now().timestamp(),
            "time_sent": time(),
            "time_received": None,
            "packet_version": PACKET_VERSION,
        }
        TimePrint("Sending Packet: " + event)
        try:
            string = self.EncodeData(json.dumps(cmd_dict))
        except Exception as F:
            print(str(F))
            return
        self.SendBytes(string)

    def SendBytes(self, _bytes: bytes) -> None:
        try:
            self.client.send(_bytes)
        except Exception as F:
            print(str(F))
            self.Close()

    def EncodeData(self, json_string: str):
        # look at listener decode function
        '''
        if self._uuid_verified:
            # cipher = AES.new(bytes(self.private_uuid), AES.MODE_ECB)
            # encoded = base64.b64encode(cipher.encrypt(json_string.encode("utf-8")))
            encoded = Encode(self.private_uuid, json_string)
        else:
        '''
        # just use base64 until we verify/send the UUID
        encoded = base64.b64encode(json_string.encode("utf-8"))
        return encoded
    
    def WaitForResponse(self) -> dict:
        try:
            while True:
                if self.listener.event_queue:
                    event = self.listener.event_queue[0]
                    self.listener.event_queue.remove(event)
                    return event
                elif not self.listener.connected:
                    return {}
                sleep(0.1)
        except Exception as F:
            print(str(F))
            return {}

    def InitCheckUUID(self, uuid: dict) -> None:
        self.private_uuid = uuid["content"]["private"]
        self.public_uuid = uuid["content"]["public"]

        if self.private_uuid not in self.server.user_info_file.GetAllPrivateUUIDS():  # and \
            #     str(self.public_uuid) not in self.server.user_info_file.GetAllPublicUUIDS():
            self.SendPacket("wrong_uuid")
            self.WaitForResponse()
            self.Close()
        else:
            self.SendPacket("valid_uuid")
            self._uuid_verified = True
            self.listener.uuid_verified = True

    def InitRequestUUID(self) -> None:
        self.private_uuid = str(self.server.user_info_file.MakePrivateUUID())
        self.public_uuid = str(self.server.user_info_file.MakePublicUUID())
        self.SendPacket("send_uuid", {"private": self.private_uuid, "public": self.public_uuid})
        self._uuid_verified = True
        self.listener.uuid_verified = True

    def InitVersionCheck(self, client_version: int) -> None:
        pass

    def FullUpdate(self, placeholder=None) -> None:
        self.SendPacket("channel_list", self.server.GetChannelList())
        self.SendPacket("member_list", {"member_list": self.server.user_info_file.GetAllUsersPublic()})
        self.SendPacket("server_info", {"server_name": self.server.name})
        # self.SendEvent("full_update_finished")

    def ReceiveUserInfo(self, user_info: dict) -> None:
        self.username = user_info["content"]["username"]
        if "user_info" not in user_info["content"]:
            self.user_tag = self.server.user_info_file.MakeUserTag(self.username)
            self.SendPacket("user_tag", {"user_tag": self.user_tag})
        else:
            self.user_tag = user_info["user_tag"]
        self.server.user_info_file.AddUser(self.username, self.user_tag, str(self.private_uuid), str(self.public_uuid))
        # self.FullUpdate()

    def ReceiveMessage(self, message: dict) -> None:
        channel = self.server.GetChannel(message["content"]["channel"])
        channel.AddMessage(message)
        message["content"]["time_received"] = message["time_received"]
        self.server.Broadcast("receive_message", message)
        
    def SendChannelMessageRange(self, event_dict: dict) -> None:
        # ask for a section of the channel event history
        channel = self.server.GetChannel(event_dict["content"]["channel_name"])
        channel_page = channel.GetMessages(event_dict["content"]["message_index"],
                                           50,  # might allow client to request more than 50 messages at a time
                                                # also would need to check across event function versions
                                           event_dict["content"]["direction"])
        # channel_page = channel.GetAllMessagesTest()
        self.SendPacket("channel_messages", {
            "channel_name": event_dict["content"]["channel_name"],
            "start_message": event_dict["content"]["message_index"],
            "message_count": 50,
            "messages": channel_page,
        })

    def HandleEvent(self, event: dict) -> None:
        if event["event"] in self.event_function_dict.keys():
            if event["content"]:
                self.event_function_dict[event["event"]](event)
            else:
                self.event_function_dict[event["event"]]()
        else:
            TimePrint("Unknown Event: " + event["event"])

    def Ping(self) -> None:
        self.SendPacket("ping")
        
    def SendDisconnect(self, reason: str):
        self.SendPacket("disconnect", {"reason": reason})
        
    def Close(self):
        self.client.close()
        self.listener.Stop()
        self.server.RemoveClient(self.client)
        self._stopping = True

    def run(self) -> None:
        TimePrint("socket running")
        try:
            while True:
                while len(self.listener.event_queue) > 0:
                    event = self.listener.event_queue[0]
                    self.listener.event_queue.remove(event)
                    self.HandleEvent(event)
                    
                if self._stopping or not self.listener.connected:
                    break
    
                # apparently this loop was causing the cpu usage to go up to 10%
                # and slow the whole program down by a shit ton, so just sleep for 0.1 seconds
                sleep(0.1)
                
        except Exception as F:
            self.SendDisconnect(str(F))
            print(F)
            self.Close()


# do i need to have the socket have the channels or some shit?
# no, just connect to the file whenever you need to read/write something
class Channel:
    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        file = sqlite3.connect("channels/" + name + ".db")
        crsr = file.cursor()

        # do we have a message table here?
        try:
            # why does this not work
            # CHECK(TYPEOF(time) == 'FLOAT')
            # CHECK(TYPEOF(user) == 'CHAR')
            # CREATE TABLE if not exists messages
            crsr.execute("""
CREATE TABLE messages (
    time FLOAT,
    user CHAR(36) NOT NULL,
    text TEXT(4096),
    file TEXT(1024)
);""")
        except sqlite3.OperationalError as F:
            print(str(F))
            pass

    def GetMessageCount(self) -> int:
        file, cursor = self.OpenFile()
        cursor.execute("select count (*) from messages;")
        message_count = cursor.fetchone()[0]
        file.close()
        return message_count

    def ConnectToFile(self) -> sqlite3.Connection:
        return sqlite3.connect("channels/" + self.name + ".db")

    @staticmethod
    def SaveAndClose(file: sqlite3.Connection) -> None:
        file.commit()
        file.close()

    def GetCursor(self) -> sqlite3.Cursor:
        return self.ConnectToFile().cursor()

    def OpenFile(self) -> tuple:
        file = self.ConnectToFile()
        return file, file.cursor()

    def DeleteEvent(self, event) -> None:
        file, cursor = self.OpenFile()
        # delete
        # cursor.execute("""DROP TABLE employee;""")
        
    def ExceptExcute(self, ):
        pass

    # TODO: fix being able to put quotes in here, it doesn't work
    def AddMessage(self, message: dict) -> None:
        file, cursor = self.OpenFile()
        # time_received = str(datetime.datetime.fromtimestamp(message["time_received"]))
        cursor.execute(
            """INSERT INTO messages (time, user, text, file) VALUES (?, ?, ?, ?);""",
            # """INSERT INTO messages VALUES (?, ?, ?, ?);""",
            (message["time_received"], message["content"]["name"],
             message["content"]["text"], message["content"]["file"]))
        self.SaveAndClose(file)
    
    def GetAllMessagesTest(self) -> list:
        file, cursor = self.OpenFile()
        cursor.execute("SELECT * FROM messages ORDER BY time ASC")
        messages = cursor.fetchall()
        file.close()
        return messages
    
    def GetMessages(self, start_message_index: int, message_count: int, msg_direction: str) -> dict:
        total_message_count = self.GetMessageCount() - 1
        file, cursor = self.OpenFile()

        if msg_direction == "back":
            start_message_index -= 1
            direction = "DESC"
        elif msg_direction == "forward":
            start_message_index += 1
            direction = "ASC"
        else:
            return {}

        # cmd = f"SELECT COUNT(?) from messages ORDER BY time {direction}"
        # cmd = f"SELECT COUNT(?) from messages ORDER BY time {direction} offset 0"
        cmd = f"SELECT * from messages ORDER BY time {direction} limit ?"
        # cmd = f"SELECT * from messages ORDER BY time {direction} limit ? offset ?"
        # cmd = "SELECT * from messages ORDER BY time " + direction
        try:
            # cursor.execute(cmd, (message_count, total_message_count - start_message_index))
            # cursor.execute(cmd)  # 0 SUPPLIED
            cursor.execute(cmd, (str(message_count),))  # 2 SUPPLIED
            # WHAT THE FUCK
            # cursor.execute(cmd, (direction, ))
        except Exception as F:
            print(str(F))
            return {}
        messages = cursor.fetchall()
        file.close()
        message_dict = {}

        if direction == "DESC":
            for index, message in enumerate(messages):
                message_dict[start_message_index - index] = message
        elif direction == "ASC":
            # TODO: test this
            for index, message in enumerate(messages):
                message_dict[start_message_index + index] = message
            
        return message_dict

    def RunCommand(self, command: str):
        file, cursor = self.OpenFile()
        output = cursor.execute(command)
        self.SaveAndClose(file)
        return output

    # TODO: add search tags, or make functions to call depending on the tags
    def Search(self, string: str) -> None:
        return


# TODO: make a server config file, like how we have a user config file for clients
class Server:
    def __init__(self, name: str, ip: str, port: int, max_clients: int) -> None:
        self.name = name
        self.ip = ip
        self.port = int(port)
        self.max_clients = max_clients

        self.client_uuid_list = {}
        self.channel_list = []
        self.user_info_file = UserInfoFile()
        self.server_config = ServerConfig(self)

        # The first argument AF_INET is the combined_address domain of the socket.
        # This is used when we have an Internet Domain with any two hosts.
        # The second argument is the type of socket.
        # SOCK_STREAM means that data or characters are read in a continuous flow.
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.client_list = []
        self.con_var_list = []
        self.con_command_dict = {
            "find": self.Find,  # TODO: move to cli_server?
            # "add_channel": self.AddChannel,
            # "rm_channel": self.RemoveChannel,
        }

        self.Start()

    def Start(self) -> None:
        self.socket.bind((self.ip, self.port))
        Thread(target=self.ListenForClients, args=()).start()
        Thread(target=self.ListenConsole, args=()).start()  # TODO: remove this and move to cli version

    def Close(self) -> None:
        self.socket.close()
        TimePrint("Server closed")

    # this just returns an empty dict, why?
    def GetChannelList(self) -> dict:
        channel_dict = {}
        for channel in self.channel_list:
            channel_dict[channel.name] = {
                "description": channel.description,
                "message_count": channel.GetMessageCount(),
            }
        return channel_dict

    def GetChannel(self, channel_name: str) -> str:
        for channel in self.channel_list:
            if channel.name == channel_name:
                return channel
        else:
            Exception("Channel does not exist")

    def RemoveClient(self, client: socket, address: str = "") -> None:
        if client in self.client_list:
            self.client_list.remove(client)
            if address:
                TimePrint("-------- {0} disconnected --------".format(address))

    # this will be used for when we receive a message or some shit idk
    def Broadcast(self, command: str, *args) -> None:
        for client in self.client_list:
            client.SendPacket(command, *args)

    def Find(self, search: str) -> None:
        result = []
        for con_command in self.con_command_dict.keys():
            if search in con_command:
                result.append(con_command)
        if result:
            print(" - " + "\n - ".join(result))
        else:
            print("No results for \"" + search + "\" found")

    # this will handle ConVars
    def ListenConsole(self) -> None:
        while True:
            try:
                command = input()
                # TODO: make sure we don't split by spaces in quotes
                command_split = command.split(" ")
                if command_split[0] in self.con_command_dict.keys():
                    self.con_command_dict[command_split[0]](*command_split[1:])
            except Exception as F:
                print(str(F))

    # def SendObject(self, client, obj) -> None:
    #     self.SendBytes(pickle.dumps(client, obj))

    def SendBytes(self, client, _bytes: bytes) -> bool:
        try:
            client.send(_bytes)
            return True
        except Exception as F:
            print(str(F))
            client.close()
            self.RemoveClient(client)
            return False

    def ListenForClients(self) -> None:
        # self.socket.setblocking(False)
        self.socket.listen(self.max_clients)
        TimePrint("Server started on {0}:{1}".format(self.ip, str(self.port)))
        while True:
            try:
                """Accepts a connection request and stores two parameters,
                conn which is a socket object for that user, and addr
                which contains the IP combined_address of the socket that just
                connected"""
                conn, addr = self.socket.accept()

                # prints the combined_address of the user that just connected
                TimePrint("-------- {0} connected --------".format(addr))
                
                # creates and individual thread for every user that connects
                client = ServerClient(self, conn, addr)
                client.start()
                self.client_list.append(client)

            except KeyboardInterrupt:
                self.Close()
                break
    
            except Exception as F:
                print(str(F))
                continue


class UserInfo:
    def __init__(self, username: str = "", user_tag: int = 0, user_picture: str = "", public_uuid: str = "",
                 private_uuid: str = "", join_date: float = 0.0, last_seen: float = 0.0):
        self.username = username
        self.user_tag = user_tag
        self.user_picture = user_picture
        self.public_uuid = public_uuid
        self.private_uuid = private_uuid
        self.join_date = join_date
        self.last_seen = last_seen


class UserInfoFile:
    def __init__(self) -> None:
        self.users = []
        if not os.path.isfile("user_info.db"):
            file, crsr = self.OpenFile()
    
            try:
                # username VARCHAR(48)
                crsr.execute("""
            CREATE TABLE users (
                username VARCHAR(48) NOT NULL,
                user_tag TINYINT NOT NULL,
                user_picture TEXT(2048),
                public_uuid CHAR(16) NOT NULL,
                private_uuid CHAR(16) NOT NULL,
                join_date DATETIME NOT NULL,
                last_seen DATETIME NOT NULL
            );""")
            except sqlite3.OperationalError as F:
                print(str(F))
        else:
            self.InitUsers()

    @staticmethod
    def ConnectToFile() -> sqlite3.Connection:
        return sqlite3.connect("user_info.db")

    @staticmethod
    def SaveAndClose(file) -> None:
        file.commit()
        file.close()

    def OpenFile(self) -> tuple:
        file = self.ConnectToFile()
        return file, file.cursor()

    def InitUsers(self) -> None:
        user_list = self.GetAllUsers()
        for user_tuple in user_list:
            user = UserInfo(*user_tuple)
            self.users.append(user)

    def GetUserCount(self) -> int:
        file, cursor = self.OpenFile()
        cursor.execute("select count (*) from users;")
        user_count = cursor.fetchone()[0]
        file.close()
        return user_count

    def GetAllUsers(self) -> list:
        file, cursor = self.OpenFile()
        cursor.execute("SELECT * FROM users;")
        users = cursor.fetchall()
        if type(users) != list:
            users = []
        file.close()
        return users
    
    def GetAllUsersPublic(self) -> dict:
        private_uuid_user_list = self.GetAllUsers()
        public_uuid_user_list = {}
        for user in private_uuid_user_list:
            user_info = [*user]
            public_uuid = user_info[4]
            user_info.remove(user_info[4])
            user_info.remove(user_info[3])
            public_uuid_user_list[public_uuid] = user_info
        return public_uuid_user_list
    
    def GetAllUsersPublicOld(self) -> list:
        private_uuid_user_list = self.GetAllUsers()
        public_uuid_user_list = []
        for user in private_uuid_user_list:
            user_info = [*user]
            user_info.remove(user_info[3])
            public_uuid_user_list.append(user_info)
        return public_uuid_user_list
    
    def _GetColumnInAllRows(self, column: int) -> list:
        users = self.GetAllUsers()
        items = []
        for user in users:
            items.append(user[column])
        return items

    def GetUsernames(self) -> list:
        return self._GetColumnInAllRows(0)

    def GetAllPrivateUUIDS(self) -> list:
        return self._GetColumnInAllRows(3)

    def GetAllPublicUUIDS(self) -> list:
        return self._GetColumnInAllRows(4)

    @staticmethod
    def _MakeUUID(uuid_list: list) -> UUID:
        while True:
            new_uuid = uuid4()
            if str(new_uuid) not in uuid_list:
                return new_uuid
        
    def MakePrivateUUID(self) -> UUID:
        return self._MakeUUID(self.GetAllPrivateUUIDS())

    def MakePublicUUID(self) -> UUID:
        return self._MakeUUID(self.GetAllPublicUUIDS())

    def MakeUserTag(self, username: str) -> int:
        username_list = self.GetUsernames()
        return username_list.count(username) - 1 + 1
        # if username in username_list:
            # doesn't check if the tag is taken,
            # just kind of assumes based on amount of users with that username
            # get number of times X is in list
        #     return username_list.count(username) - 1 + 1
        # else:
        #     return

    def AddUser(self, username: str, user_tag: int, public_uuid: str, private_uuid: str, user_picture: str = ""):
        file, cursor = self.OpenFile()
        join_date = datetime.datetime.now().timestamp()
        user_tuple = (username, user_tag, user_picture, public_uuid, private_uuid, join_date, join_date)
        cursor.execute(
            """INSERT INTO users (username, user_tag, user_picture, public_uuid, private_uuid, join_date, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?);""", user_tuple)
        user = UserInfo(*user_tuple)
        self.users.append(user)
        self.SaveAndClose(file)

    def GetUserInfoPrivate(self, private_uuid: str) -> UserInfo:
        pass

    def GetUserInfo(self, public_uuid: str) -> UserInfo:
        pass

    def UpdateUserInfo(self, public_uuid: str, username: str = "", user_tag: int = -1,
                       user_picture: str = "", ast_seen: float = -1.0):
        file, cursor = self.OpenFile()
        user_info = self.GetUserInfo(public_uuid)
        cursor.execute(
            """INSERT INTO users (username, user_tag, user_picture, public_uuid, private_uuid, join_date, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
            (username, user_tag, user_picture, public_uuid, private_uuid, join_date, join_date))
        self.SaveAndClose(file)


class ServerConfig:
    def __init__(self, server: Server) -> None:
        try:
            self.dkv_input = dkv.ReadFile(SERVER_CONFIG_PATH)
        except FileNotFoundError:
            # create an empty file
            with open(SERVER_CONFIG_PATH, "w", encoding="utf-8") as file:
                pass
            self.dkv_input = dkv.DemezKeyValueRoot()
            
        server_name = self.dkv_input.GetItem("name")
        if server_name:
            server.name = server_name.value
        else:
            server.name = "default"
            self.dkv_input.AddItem("name", "default")

        channel_list = self.dkv_input.GetItem("channels")
        if channel_list:
            for channel_dkv in channel_list.value:
                channel = Channel(channel_dkv.key)
                server.channel_list.append(channel)
        else:
            self.dkv_input.AddItem("channels", []).AddItem("default", [])
            channel = Channel("default")
            server.channel_list.append(channel)

        user_uuid_list = self.dkv_input.GetItem("user_uuids")
        if user_uuid_list:
            for user_uuid in user_uuid_list.value:
                server.client_uuid_list[user_uuid.key] = UUID(user_uuid.key)
        else:
            self.dkv_input.AddItem("user_uuids", [])
                
        print("server config done")
        
    def AddChannel(self, channel_name: str) -> None:
        self.dkv_input.GetItem("channels").AddItem(channel_name, [])
        self.WriteChanges()

    def SetServerName(self, server_name: str) -> None:
        self.dkv_input.GetItem("name").value = server_name
        self.WriteChanges()
        
    def WriteChanges(self) -> None:
        if os.path.isfile(SERVER_CONFIG_PATH):
            os.rename(SERVER_CONFIG_PATH, SERVER_CONFIG_PATH + ".bak")
        with open(SERVER_CONFIG_PATH, "w", encoding="utf-8") as file:
            file.write(self.dkv_input.ToString())
        if os.path.isfile(SERVER_CONFIG_PATH + ".bak"):
            os.remove(SERVER_CONFIG_PATH + ".bak")
