from datetime import datetime
from time import time
import platform


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


def IsWindows10() -> bool:
    if platform.platform().startswith("Windows-10"):
        return True
    return False


def TimePrint(*args) -> None:
    # TODO: maybe have a check here if we installed colorama, and use colored text here
    print("[{0}] {1}".format(GetTime24Hour(), str(*args)))

