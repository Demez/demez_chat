from dkv import demez_key_values as dkv
import os
from uuid import UUID


USER_CONFIG_PATH = "user_config.dkv"


class ServerBookmark:
    def __init__(self, ip: str, port: int, name: str = "", key: UUID = None):
        self.ip = ip
        self.port = port
        self.name = name
        self.key = key


class UserInfo:
    def __init__(self, name: str = "default", picture: str = "default.png"):
        self.name = name
        self.picture = picture


class UserConfig:
    def __init__(self):
        try:
            self.dkv_input = dkv.ReadFile(USER_CONFIG_PATH)
        except FileNotFoundError:
            with open(USER_CONFIG_PATH, "w", encoding="utf-8") as file:
                pass
            self.dkv_input = dkv.DemezKeyValueRoot()
            
        self.bookmarks = []
        bookmarks_dkv = self.dkv_input.GetItem("bookmarks")
        if bookmarks_dkv:
            for server in bookmarks_dkv.GetAllItems("server"):
                server_obj = ServerBookmark(
                    server.GetItemValue("ip"), server.GetItemIntValue("port"), server.GetItemValue("name"))
                self.bookmarks.append(server_obj)
                
        user = self.dkv_input.GetItem("user")
        if user:
            self.user = UserInfo(user.GetItemValue("name"), user.GetItemValue("picture"))
        else:
            self.user = UserInfo()
            
    def WriteChanges(self) -> None:
        if os.path.isfile(USER_CONFIG_PATH):
            os.rename(USER_CONFIG_PATH, USER_CONFIG_PATH + ".bak")
        with open(USER_CONFIG_PATH, "w", encoding="utf-8") as file:
            file.write(self.dkv_input.ToString())
        if os.path.isfile(USER_CONFIG_PATH + ".bak"):
            os.remove(USER_CONFIG_PATH + ".bak")
            
    def GetUsername(self) -> str:
        return self.user.name
        
    def GetPicturePath(self) -> str:
        return self.user.picture
        
    def GetServerDKV(self, server: ServerBookmark) -> dkv.DemezKeyValue:
        bookmarks_dkv = self.dkv_input.GetItem("bookmarks")
        if bookmarks_dkv:
            for srvr in bookmarks_dkv.GetAllItems("server"):
                if srvr.GetItemValue("ip") == server.ip and srvr.GetItemValue("port") == str(server.port):  # \
                    # and srvr.GetItemValue("name") == server.name: and srvr.GetItemValue("key") == str(server.key):
                    return srvr  # server_dkv
                
    def GetServerBookmark(self, ip: str, port: int, name: str = "", key: UUID = None) -> ServerBookmark:
        for server in self.bookmarks:
            if server.ip == ip and server.port == port:
                if name and server.name == name:
                    return server
                else:
                    return server
        
    def GetServerKey(self, ip: str, port: int, name: str = "", key: UUID = None) -> UUID:
        server = self.GetServerDKV(self.GetServerBookmark(ip, port, name))
        if server.HasItem("key"):
            return UUID(server.GetItemValue("key"))
        
    def SetServerKey(self, ip: str, port: int, key: UUID, name: str = "") -> None:
        server = self.GetServerDKV(self.GetServerBookmark(ip, port, name))
        key_dkv = server.AddItemSingle("key", str(key))
        # if not key_dkv:
        #     key_dkv = server.AddItem("key")
        # key_dkv.value = str(key)
        self.WriteChanges()
    
    def SetUsername(self, new_name: str) -> None:
        self.user.name = new_name
        user_name = self.dkv_input.GetItem("user").GetItem("name")
        user_name.value = new_name
        self.WriteChanges()
        
    def AddBookmark(self, ip: str, port: int, name: str) -> None:
        server_bookmark = ServerBookmark(ip, port, name)
        self.bookmarks.append(server_bookmark)
    



