from datetime import datetime
from time import time


class Command:
    def __init__(self, command: str, *args) -> None:
        self.command = command
        self.args = args


def GetTime() -> datetime:
    return datetime.now()


def GetTime24Hour() -> str:
    return GetTime().strftime("%H:%M:%S")


def GetTime12Hour() -> str:
    return GetTime().strftime("%I:%M:%S")


def GetTimeUnix() -> float:
    return time()


def UnixToDateTime(unix_time: float) -> datetime:
    return datetime.fromtimestamp(unix_time)


def UnixTo12Hour(unix_time: float) -> str:
    return UnixToDateTime(unix_time).strftime("%I:%M:%S")


def UnixTo24Hour(unix_time: float) -> str:
    return UnixToDateTime(unix_time).strftime("%H:%M:%S")


def TimePrint(*args) -> None:
    print("[{0}] {1}".format(GetTime24Hour(), str(*args)))

