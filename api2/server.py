import os
import time
import json
import socket
import sqlite3
from dkv import demez_key_values as dkv
from uuid import uuid4, UUID
from threading import Thread
from api2.shared import Command, TimePrint
from api2.listener import SocketListener
from api2.dir_tools import CreateDirectory
import math

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
        self.listener = SocketListener("server", client)
        self.listener.start()
        self._stopping = False
        self.commands = {
            "receive_message": self.ReceiveMessage,
            "send_message": self.ReceiveMessage,
            "request_channel_messages": self.SendChannelMessageRange,
        }

        self.ClientInit()

    def SendCommand(self, command: str, *args) -> None:
        cmd_dict = {
            "command": command,
            "args": [*args],
        }
        self.SendBytes(json.dumps(cmd_dict).encode())

    def SendBytes(self, _bytes: bytes) -> None:
        try:
            self.client.send(_bytes)
        except Exception as F:
            print(str(F))
            self.client.close()
            self.listener.Stop()

            # if the link is broken, we remove the socket
            self.server.RemoveClient(self.client)
            self._stopping = True

    def ClientInit(self) -> None:
        self.SendCommand("init_channel_list", self.server.GetChannelList())
        # self.SendObject("init_member_list", self.server.GetMemberList())
        self.SendCommand("init_finish")

    def ReceiveMessage(self, message: dict) -> None:
        channel = self.server.GetChannel(message["channel"])
        channel.AddMessage(message)
        self.server.Broadcast("receive_message", message)
        
    def SendChannelMessageRange(self, channel_name: str, start_message: int, direction: str = "back", message_count: int = 50) -> None:
        # ask for a section of the channel event history
        channel = self.server.GetChannel(channel_name)
        channel_page = channel.GetMessages(start_message, message_count, direction)
        # channel_page = channel.GetAllMessagesTest()
        self.SendCommand("receive_channel_messages", {
            "channel_name": channel_name,
            "start_message": start_message,
            "message_count": message_count,
            "messages": channel_page,
        })

    def RunCommand(self, cmd: Command) -> None:
        if cmd.command in self.commands.keys():
            self.commands[cmd.command](*cmd.args)
    
    def Ping(self) -> None:
        self.SendCommand("ping")

    def run(self) -> None:
        TimePrint("socket running")
        while True:
            while len(self.listener.command_queue) > 0:
                command = self.listener.command_queue[0]
                self.RunCommand(command)
                self.listener.command_queue.remove(self.listener.command_queue[0])
                
            if self._stopping or not self.listener.connected:
                break

            # apparently this loop was causing the cpu usage to go up to 10%
            # and slow the whole program down by a shit ton, so just sleep for 0.1 seconds
            time.sleep(0.1)


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
            crsr.execute("""
CREATE TABLE messages (
    time FLOAT,
    user STRING,
    text STRING,
    file STRING
);""")
        except sqlite3.OperationalError:
            pass

    def GetMessageCount(self) -> int:
        file, cursor = self.OpenFile()
        cursor.execute("select count (*) from messages;")
        message_count = cursor.fetchone()[0]
        file.close()
        return message_count

    # 20 events per page
    def GetPageCount(self) -> int:
        message_count = self.GetMessageCount()
        page_count = math.ceil(message_count / 20)
        return page_count

    # this may change, so have it be a function we can quickly change
    def GetEventTableInputs(self) -> str:
        return "(time, user, text, file)"

    def ConnectToFile(self) -> sqlite3.Connection:
        return sqlite3.connect("channels/" + self.name + ".db")

    def SaveAndClose(self, file) -> None:
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

    # TODO: fix being able to put quotes in here, it doesn't work
    def AddMessage(self, message: dict) -> None:
        file, cursor = self.OpenFile()
        cursor.execute(
            """INSERT INTO messages (time, user, text, file) VALUES (?, ?, ?, ?);""",
            (float(message["time"]), message["name"], message["text"], message["file"]))
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
        direction = "DESC" if msg_direction == "back" else "ASC"
        if direction == "DESC":
            start_message_index -= 1
        elif direction == "ASC":
            start_message_index += 1
        cursor.execute(
            f"SELECT * FROM messages ORDER BY time {direction} limit {str(message_count)} offset {str(total_message_count - start_message_index)}")
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
        # super().__init__()
        self.name = name
        self.ip = ip
        self.port = int(port)
        self.max_clients = max_clients

        self.client_uuid_list = {}
        self.channel_list = []
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
            "add_channel": self.UnfinishedCommand,
            "rm_channel": self.UnfinishedCommand,
        }

        self.Start()

    def Start(self) -> None:
        self.socket.bind((self.ip, self.port))
        Thread(target=self.ListenForClients, args=()).start()
        Thread(target=self.ListenConsole, args=()).start()  # TODO: remove this and move to cli version

    def Close(self) -> None:
        self.socket.close()
        TimePrint("Server closed")
        
    def MakeUUID(self) -> UUID:
        while True:
            new_uuid = uuid4()
            if str(new_uuid) not in self.client_uuid_list:
                self.client_uuid_list[str(new_uuid)] = new_uuid
                self.server_config.AddUserUUID(new_uuid)
                return new_uuid
            
    def GetUserInfo(self, uuid: UUID) -> dict:
        pass

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
            client.SendCommand(command, *args)

    def Find(self, search: str) -> None:
        result = []
        for con_command in self.con_command_dict.keys():
            if search in con_command:
                result.append(con_command)
        if result:
            print(" - " + "\n - ".join(result))
        else:
            print("No results for \"" + search + "\" found")

    def UnfinishedCommand(self, *values) -> None:
        print("unfinished command")

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

    def SendBytes(self, client, _bytes: bytes) -> None:
        try:
            client.send(_bytes)
        except Exception as F:
            print(str(F))
            client.close()
            self.RemoveClient(client)

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
                
                b_client_key = conn.recv(1024)
                if b_client_key == b"request_uuid":
                    new_client_uuid = self.MakeUUID()
                    self.SendBytes(conn, new_client_uuid.bytes)
                else:
                    client_key = UUID(bytes=b_client_key)
                    if str(client_key) not in self.client_uuid_list:
                        self.SendBytes(conn, b"0")
                        conn.close()
                        continue
                    else:
                        self.SendBytes(conn, b"1")

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
        
    def AddUserUUID(self, user_uuid: UUID) -> None:
        self.dkv_input.GetItem("user_uuids").AddItem(str(user_uuid))
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
