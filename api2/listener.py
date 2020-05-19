import json
import base64
import socket
from time import time, sleep
from threading import Thread
from api2.shared import *


class SocketListener(BaseListener, Thread):
    def __init__(self, server, connection: socket) -> None:
        Thread.__init__(self)
        BaseListener.__init__(self, server, connection)
        self.event_queue = []

    def AddToEventQueue(self, packet: Packet):
        self.event_queue.append(packet)
    
    def run(self) -> None:
        self.connected = True
        self.MainLoop()
        
        
# Client Stuff

class ClientListener(BaseListener):
    def __init__(self, listener_handler, connection: socket, address: str, name: str, private_uuid, public_uuid):
        super().__init__(listener_handler, connection)
        self.private_uuid = private_uuid
        self.public_uuid = public_uuid
        self.name = name
        self.combined_address = address  # wait wouldn't this be the same as ip? right now it's ip:port
        self.receiving_data = False
        # self.event_queue = []
        self._encoded_buffer = b''
        self._buffer = b''
    
    def SetConnected(self, connected: bool) -> None:
        self.connected = connected
        self.uuid_verified = False if not connected else self.uuid_verified
        self.socket.setblocking(not connected)
    
    def Print(self, string: str) -> None:
        TimePrint(f"{self.combined_address}: {string}")
    
    def PrintException(self, f: Exception, string: str) -> None:
        PrintException(f, f"{self.combined_address}: {string}")
        
    def AddToEventQueue(self, packet: Packet):
        self.parent.event_queue[self.combined_address].append(packet)
    
    def _CheckConnection(self) -> bool:
        base_value = super()._CheckConnection()
        self.receiving_data = base_value
        return base_value
    
    def ReceiveData(self) -> bool:
        try:
            self._encoded_buffer = self.socket.recv(8192)
            return self._CheckConnection()
        except BlockingIOError:
            self.receiving_data = False
            return True
    
    # return whether to continue looping or not
    def CheckForPackets(self) -> bool:
        if not self.ReceiveData():
            return False
        if self._encoded_buffer:
            self.DecodeBuffer()
        if self.JsonBuffer():
            return False
        return True


class ClientListenerHandler(Thread):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client
        self.server_init_list = []
        self.server_list = []
        self.event_queue = {}
        self._stop = False
    
    # def AddServer(self, connection: socket, combined_address: str, name: str) -> None:
    #     self.server_init_list.append(SocketListener(connection, combined_address, name))
    
    def AddServer(self, connection: socket, address: str, name: str, private_uuid, public_uuid) -> ClientListener:
        socket_listener = ClientListener(self, connection, address, name, private_uuid, public_uuid)
        self.event_queue[socket_listener.combined_address] = []
        self.server_list.append(socket_listener)
        self.server_init_list.append(socket_listener.combined_address)
        return socket_listener
    
    def GetServer(self, address: str) -> ClientListener:
        for server in self.server_list:
            if server.combined_address == address:
                return server
    
    def ReplaceSocket(self, connection: socket, address: str) -> None:
        for server in self.server_list:
            if server.combined_address == address:
                server.socket = connection
    
    def Stop(self) -> None:
        self._stop = True
    
    # is this slowing the program down?
    def run(self) -> None:
        while True:
            if self._stop:
                break
            
            for server in self.server_list:
                if server.connected:
                    server.MainLoop()
            
            sleep(0.1)

