# Python program to implement server side of chat room.
import socket
import select
import sys

import pickle

from threading import Thread
from demez_chat_shared import Message, TimePrint, ClientServerCommunication, ClientServerEnums
import demez_key_values as dkv


# TODO: make a separate file for server gui,
#  so you can view all clients currently connected,
#  and have a console with ConVars and ConCommands and shit, will be used by client as well


class MessageFile:
    def __init__(self, file_path):
        self.file_path = file_path
        self.message_list = []
        self.ParseMessageFile()

    def ParseMessageFile(self):
        try:
            message_file = dkv.ReadFile(self.file_path)
        except FileNotFoundError:
            with open(self.file_path, "w", encoding="utf-8") as file:
                pass
            return

        message_block_list = message_file.GetAllItems("message")  # maybe change to FindAllItems()?

        for message_block in message_block_list:
            name = message_block.GetItemValue("name")
            time = float(message_block.GetItemValue("time"))
            text = message_block.GetItemValue("text")
            self.message_list.append(Message(name, time, text))

    def Write(self):
        with open(self.file_path, "w", encoding="utf-8") as file:
            for message_obj in self.message_list:
                file.write(message_obj.ToDemezKeyValue().ToString())

    def AddMessage(self, message: Message):
        self.message_list.append(message)
        self.Write()


MESSAGE_FILE_PATH = "messages.dkv"
MESSAGE_FILE = MessageFile(MESSAGE_FILE_PATH)


def Main():
    """The first argument AF_INET is the address domain of the
    socket. This is used when we have an Internet Domain with
    any two hosts The second argument is the type of socket.
    SOCK_STREAM means that data or characters are read in
    a continuous flow."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # TODO: replace this with argparse
    if len(sys.argv) != 3:
        print("Correct usage: script, IP address, port number")
        exit()

    ip_address = str(sys.argv[1])
    port = int(sys.argv[2])

    # temp
    # server.close()
    # quit()

    """ 
    binds the server to an entered IP address and at the 
    specified port number. 
    The client must be aware of these parameters 
    """
    server.bind((ip_address, port))

    # listens for 100 active connections. This number can be increased as per convenience.
    server.listen(100)

    TimePrint("Server started on {0}:{1}".format(ip_address, str(port)))

    try:
        while True:
            """Accepts a connection request and stores two parameters,  
            conn which is a socket object for that user, and addr  
            which contains the IP address of the client that just  
            connected"""
            conn, addr = server.accept()

            """Maintains a list of clients for ease of broadcasting 
            a message to all available people in the chatroom"""
            CLIENT_LIST.append(conn)

            # prints the address of the user that just connected
            TimePrint("-------- {0} connected --------".format(addr))

            # creates and individual thread for every user that connects
            Thread(target=ClientThread, args=(conn, addr)).start()
    except KeyboardInterrupt:
        # conn.close()
        server.close()


def ClientThread(conn, addr):
    # sends a message to the client whose user object is conn
    # TODO: make separate threads for recv and send of different things
    #  like messages, console, voice, screenshare, webcam, etc.
    for message_obj in MESSAGE_FILE.message_list:
        SendMessage(conn, pickle.dumps(message_obj))
        # make sure the client got it
        object_bytes = conn.recv(2048)
        if object_bytes:
            obj = pickle.loads(object_bytes)
            if type(obj) == ClientServerEnums.RECEIVED_MESSAGE:
                continue

    # now send an message that the chat history is finished being sent
    SendMessage(conn, pickle.dumps(ClientServerEnums.FINISHED_SENDING_HISTORY))
    TimePrint("Finished Sending Message History to {0}".format(addr))

    while True:
        try:
            object_bytes = conn.recv(2048)
            if object_bytes:
                obj = pickle.loads(object_bytes)

                if type(obj) == Message:
                    # prints the message and address of the
                    # user who just sent the message on the server terminal
                    print(obj.WriteMessageToConsole())

                    # Calls broadcast function to send message to all
                    message_to_send = pickle.dumps(obj)
                    Broadcast(message_to_send)
                    MESSAGE_FILE.AddMessage(obj)

                # TODO: set something up here so that we can get a range of messages
                #  and somehow get a starting point for it, oof
                #  ACTUALLY, just store messages in a range block,
                #  and make new range blocks once we have like 50 messages there
                # elif type(obj) == MessageRange:
                #     pass

            else:
                """message may have no content if the connection 
                is broken, in this case we remove the connection"""
                RemoveClient(conn, addr)

        except ConnectionResetError:
            RemoveClient(conn, addr)
            return
            
        except Exception as F:
            print(str(F))
            continue


# Using the below function, we broadcast the message to all
# clients who's object is not the same as the one sending the message
def Broadcast(message):
    for client in CLIENT_LIST:
        # if client != connection:
        SendMessage(client, message)


def SendMessage(client, message):
    try:
        client.send(message)
    except Exception as F:
        print(str(F))
        client.close()

        # if the link is broken, we remove the client
        RemoveClient(client)


# The following function simply removes the object
# from the list that was created at the beginning of the program
def RemoveClient(connection, addr=""):
    if connection in CLIENT_LIST:
        CLIENT_LIST.remove(connection)
        if addr:
            TimePrint("-------- {0} disconnected --------".format(addr))


if __name__ == "__main__":
    CLIENT_LIST = []
    Main()
