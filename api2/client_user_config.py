import demez_key_values as dkv


USER_CONFIG_PATH = "user_config.dkv"


class ServerBookmark:
    def __init__(self, ip: str, port: int, name: str = ""):
        self.ip = ip
        self.port = port
        self.name = name


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
                    server.GetItemValue("ip"), int(server.GetItemValue("port")), server.GetItemValue("name"))
                self.bookmarks.append(server_obj)
                
        user = self.dkv_input.GetItem("user")
        if user:
            self.user = UserInfo(user.GetItemValue("name"), user.GetItemValue("picture"))
        else:
            self.user = UserInfo()



