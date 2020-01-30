import os
import urllib.request
import urllib.error
from http.client import HTTPResponse
from ssl import CertificateError
from enum import Enum, auto
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *


class EmbedTypes(Enum):
    IMAGE = auto(),
    VIDEO = auto(),
    AUDIO = auto(),
    URL = auto(),
    NONE = auto()  # if there is no embed for the url


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".tga", ".pbm", ".tiff", ".svg", ".xbm", ".bmp"}
VIDEO_EXTS = {".mkv", ".webm", ".mp4", ".mov"}
AUDIO_EXTS = {".opus", ".ogg", ".wav", ".flac", ".mp3", ".aac", ".ac3"}


def GetEmbedTypeExt(path: str) -> Enum:
    path_ext = os.path.splitext(path)[1]
    if path_ext in IMAGE_EXTS:
        return EmbedTypes.IMAGE
    elif path_ext in VIDEO_EXTS:
        return EmbedTypes.VIDEO
    elif path_ext in AUDIO_EXTS:
        return EmbedTypes.AUDIO
    else:
        return EmbedTypes.URL


# TODO: finish this
#  maybe a dict with the values being the bytes needed for the header or something
def GetEmbedTypeBytes(opened_url) -> Enum:
    first_bytes = opened_url.read(24)
    if CheckImage(first_bytes):
        return EmbedTypes.IMAGE
    return EmbedTypes.NONE


def CheckImage(_bytes: bytes) -> bool:
    for ext in IMAGE_EXTS:
        if ext[1:] in str(_bytes).lower():
            return True
    return False


# TODO: make url downloading and stuff separate from the main thread (new thread)
#  and then have a callback on the main thread when if downloads successfully
def DownloadURL(url: str, bad_callback: classmethod):
    user_agent = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.0.7) Gecko/2009021910 Firefox/3.0.7'
    headers = {'User-Agent': user_agent, }

    request = urllib.request.Request(url, None, headers)  # The assembled request
    try:
        response = urllib.request.urlopen(request)
    except urllib.error.URLError:
        return None
    except CertificateError:
        return None
    # data = response.read()  # The data u need
    # return response
    bad_callback(url, response)


class ImageEmbed(QLabel):
    def __init__(self, parent: QWidget, path: str, response: HTTPResponse):
        super().__init__(parent)
        self.path = path
        data = response.read()
        self.image_pixmap = QPixmap()
        self.image_pixmap.loadFromData(data)
        self.UpdateImageSize(600, 800)

    # bad code probably
    def UpdateImageSize(self, max_width: int, max_height: int) -> None:
        image_size = [self.image_pixmap.width(), self.image_pixmap.height()]
        max_side = max(image_size)
        scale_mult = 1
        if max_side == image_size[0]:
            if max_width < image_size[0]:
                scale_mult = max_width / image_size[0]
        elif max_side == image_size[1]:
            if max_height < image_size[1]:
                scale_mult = max_height / image_size[1]

        if scale_mult < 1:
            self.image_pixmap = self.image_pixmap.scaled(image_size[0] * scale_mult,
                                                         image_size[1] * scale_mult,
                                                         Qt.KeepAspectRatio)

        self.setPixmap(self.image_pixmap)

    def UpdateImagePreview(self):
        pass
