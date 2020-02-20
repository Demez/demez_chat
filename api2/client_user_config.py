from dkv import demez_key_values as dkv
# import os
from uuid import UUID


USER_CONFIG_PATH = "user_config.dkv"
DEFAULT_NAME = "Default Name"
DEFAULT_PFP_PATH = "doge.png"


class ServerBookmark:
    def __init__(self, ip: str, port: int, name: str = "", private_uuid: str = None,
                 public_uuid: str = None, user_tag: int = None):
        self.ip = ip
        self.port = port
        self.name = name
        self.private_uuid = private_uuid
        self.public_uuid = public_uuid
        self.user_tag = user_tag


class UserInfo:
    def __init__(self, name: str = DEFAULT_NAME, picture: str = DEFAULT_PFP_PATH):
        self.name = name
        self.picture = picture


class UserConfig:
    def __init__(self):
        try:
            self.dkv_input = dkv.ReadFile(USER_CONFIG_PATH)
        except FileNotFoundError:
            with open(USER_CONFIG_PATH, "w", encoding="utf-8") as file:
                pass
            self.dkv_input = dkv.DemezKeyValueRoot(USER_CONFIG_PATH)
            
        self.bookmarks = []
        bookmarks_dkv = self.dkv_input.GetItem("bookmarks")
        if bookmarks_dkv:
            for server in bookmarks_dkv.GetAllItems("server"):
                server_obj = ServerBookmark(
                    server.GetItemValue("ip"), server.GetItemIntValue("port"), server.GetItemValue("name"),
                    server.GetItemValue("private_uuid"), server.GetItemValue("public_uuid"))
                user_tag = server.GetItemIntValue("user_tag")
                if type(user_tag) == int:
                    server_obj.user_tag = user_tag
                self.bookmarks.append(server_obj)
        else:
            self.dkv_input.AddItem("bookmarks", [])
                
        user = self.dkv_input.GetItem("user")
        if user:
            self.user = UserInfo(user.GetItemValue("name"), user.GetItemValue("picture"))
        else:
            user = self.dkv_input.AddItem("user", [])
            self.user = UserInfo()

        if not user.HasItem("name"):
            user.AddItem("name", DEFAULT_NAME)
        if not user.HasItem("picture"):
            user.AddItem("picture", DEFAULT_PFP_PATH)
        
    def WriteChanges(self) -> None:
        self.dkv_input.UpdateFileSafe()
            
    def GetUsername(self) -> str:
        return self.user.name
    
    def SetUsername(self, new_name: str) -> None:
        self.user.name = new_name
        self.dkv_input.GetItem("user").GetItem("name").value = new_name
        self.WriteChanges()
        
    def GetProfilePicturePath(self) -> str:
        return self.user.picture
    
    def SetProfilePicturePath(self, new_path: str) -> None:
        self.user.picture = new_path
        self.dkv_input.GetItem("user").GetItem("picture").value = new_path
        self.WriteChanges()
        
    def GetServerDKV(self, ip: str, port: int, name: str = "") -> dkv.DemezKeyValue:
        for server_dkv in self.dkv_input.GetItem("bookmarks").GetAllItems("server"):
            if self._CheckServer(server_dkv, ip, port, name):
                return server_dkv
        
    def GetServerDKVBookmark(self, server: ServerBookmark) -> dkv.DemezKeyValue:
        for server_dkv in self.dkv_input.GetItem("bookmarks").GetAllItems("server"):
            if self._CheckServer(server_dkv, server.ip, server.port, server.name):
                return server_dkv
                
    @staticmethod
    def _CheckServer(server: dkv.DemezKeyValue, ip: str, port: int, name: str = "") -> bool:
        if server.GetItemValue("ip") == ip and server.GetItemIntValue("port") == port:
            if name:
                return server.GetItemValue("name") == name
            return True
                
    def GetServerBookmark(self, ip: str, port: int, name: str = "", key: UUID = None) -> ServerBookmark:
        for server in self.bookmarks:
            if server.ip == ip and server.port == port:
                if name and server.name == name:
                    return server
                else:
                    return server
        
    def GetServerPrivateUUID(self, ip: str, port: int, name: str = "") -> str:
        server = self.GetServerDKV(ip, port, name)
        private_uuid = server.GetItemValue("private_uuid")
        if private_uuid:
            try:
                return str(UUID(private_uuid))
            except Exception as F:
                print(str(F))

    def GetServerPublicUUID(self, ip: str, port: int, name: str = "") -> str:
        server = self.GetServerDKV(ip, port, name)
        public_uuid = server.GetItemValue("public_uuid")
        if public_uuid:
            try:
                return str(UUID(public_uuid))
            except Exception as F:
                print(str(F))

    def GetServerUUIDs(self, ip: str, port: int, name: str = "") -> tuple:
        return self.GetServerPrivateUUID(ip, port, name),  self.GetServerPublicUUID(ip, port, name)
        
    def SetServerInfo(self, ip: str, port: int, private_uuid: UUID, public_uuid: UUID, user_tag: int, name: str) -> None:
        server = self.GetServerDKV(ip, port, name)
        # maybe change AddItemSingle to AddItemUpdate or something
        server.AddItemSingle("name", name)
        server.AddItemSingle("user_tag", str(user_tag))
        server.AddItemSingle("private_uuid", str(private_uuid))
        server.AddItemSingle("public_uuid", str(public_uuid))
        self.WriteChanges()
        
    def AddBookmark(self, ip: str, port: int, name: str) -> None:
        server_bookmark = ServerBookmark(ip, port, name)
        bookmarks_dkv = self.dkv_input.GetItem("bookmarks")
        server_dkv = bookmarks_dkv.AddItem("server", [])
        server_dkv.AddItem("ip", ip)
        server_dkv.AddItem("port", str(port))
        server_dkv.AddItem("name", str(name))
        server_dkv.AddItem("user_tag", "")
        server_dkv.AddItem("private_uuid", "")
        server_dkv.AddItem("public_uuid", "")
        self.bookmarks.append(server_bookmark)
        self.WriteChanges()
    



