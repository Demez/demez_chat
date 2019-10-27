from datetime import datetime
import time
import demez_key_values as dkv
import enum


class Message:
    def __init__(self, name="", unix_time=0, text=""):
        self.time = unix_time
        self.name = name
        self.text = text

    def __bytes__(self):
        return ""

    def WriteMessageToConsole(self):
        return "[{0} - {1}] {2}".format(UnixTo24Hour(self.time), self.name, self.text)

    def ToDemezKeyValue(self):
        message_block = dkv.DemezKeyValue(None, "message", [])
        message_block.AddItem("time", self.time)
        message_block.AddItem("name", self.name)
        message_block.AddItem("text", self.text)
        return message_block


class ClientServerEnums(enum.Enum):
    RECEIVED_MESSAGE = 0
    FINISHED_SENDING_HISTORY = 1

    def __bytes__(self):
        return ""


class ClientServerCommunication:
    def __init__(self, object_type):
        self.object_type = object_type

    def __bytes__(self):
        return ""


def GetUserFromID(user_id: int):
    pass


def GetTime():
    return datetime.now()


def GetTime24Hour():
    return GetTime().strftime("%H:%M:%S")


def GetTime12Hour():
    return GetTime().strftime("%I:%M:%S")


def GetTimeUnix():
    return time.time()


def UnixToDateTime(unix_time):
    return datetime.fromtimestamp(float(unix_time))


def UnixTo12Hour(unix_time):
    return UnixToDateTime(unix_time).strftime("%I:%M:%S")


def UnixTo24Hour(unix_time):
    return UnixToDateTime(unix_time).strftime("%H:%M:%S")


def TimePrint(*args):
    print("[{0}] {1}".format(GetTime24Hour(), str(*args)))
