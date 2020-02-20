from datetime import datetime
from time import time
import platform
import base64


# https://gist.github.com/gowhari/fea9c559f08a310e5cfd62978bc86a1a
# Vigenere Cipher, not the best for security, but this was the first thing i found and im lazy
def Encode(key, string):
    try:
        encoded_chars = []
        for i in range(len(string)):
            key_c = key[i % len(key)]
            encoded_c = chr(ord(string[i]) + ord(key_c) % 256)
            encoded_chars.append(encoded_c)
        encoded_string = ''.join(encoded_chars)
        encoded_string = encoded_string.encode('latin')  # if six.PY3 else encoded_string
        return base64.urlsafe_b64encode(encoded_string).rstrip(b'=')
    except Exception as F:
        print(str(F))


def Decode(key, string):
    string = base64.urlsafe_b64decode(string + b'===')
    string = string.decode('latin')  # if six.PY3 else string
    encoded_chars = []
    for i in range(len(string)):
        key_c = key[i % len(key)]
        encoded_c = chr((ord(string[i]) - ord(key_c) + 256) % 256)
        encoded_chars.append(encoded_c)
    encoded_string = ''.join(encoded_chars)
    return encoded_string


def GetTime() -> datetime:
    return datetime.now()


def GetTime24Hour() -> str:
    return GetTime().strftime("%H:%M:%S")


def GetTime12Hour() -> str:
    return GetTime().strftime("%I:%M:%S")


def GetDate() -> str:
    return GetTime().strftime("%Y-%m-%d")


def GetDateAndTime() -> str:
    return GetTime().strftime("%Y-%m-%d - %H:%M:%S")


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
    print("[{0}] {1}".format(GetDateAndTime(), str(*args)))

