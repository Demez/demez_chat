import os
import uuid
import urllib.request
import urllib.error
from http.client import HTTPResponse
from ssl import CertificateError
from enum import Enum, auto
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import ftplib
from time import sleep

from api2.shared import PrintError, PrintException
from api2.video_player import VideoPlayer
from threading import Thread


class EmbedType(Enum):
    IMAGE = auto()
    VIDEO = auto()
    AUDIO = auto()
    URL = auto()
    NONE = auto()  # if there is no embed for the url


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".tga", ".pbm", ".tiff", ".svg", ".xbm", ".bmp"}
VIDEO_EXTS = {".mkv", ".webm", ".mp4", ".mov"}
AUDIO_EXTS = {".opus", ".ogg", ".wav", ".flac", ".mp3", ".aac", ".ac3"}


def GetEmbedTypeExt(path: str) -> Enum:
    path_ext = os.path.splitext(path)[1]
    if path_ext in IMAGE_EXTS:
        return EmbedType.IMAGE
    elif path_ext in VIDEO_EXTS:
        return EmbedType.VIDEO
    elif path_ext in AUDIO_EXTS:
        return EmbedType.AUDIO
    
    # hack to allow the video player to use youtube stuff right now
    elif "youtube.com/watch?v=" in path or "youtu.be/" in path:
        return EmbedType.VIDEO
    
    else:
        return EmbedType.URL


# TODO: finish this
#  maybe a dict with the values being the bytes needed for the header or something
def GetEmbedTypeBytes(opened_url) -> Enum:
    first_bytes = opened_url.read(24)
    if CheckImage(first_bytes):
        return EmbedType.IMAGE
    return EmbedType.NONE


def CheckImage(_bytes: bytes) -> bool:
    for ext in IMAGE_EXTS:
        if ext[1:] in str(_bytes).lower():
            return True
    return False


# TODO: make url downloading and stuff separate from the main thread (new thread)
#  and then have a callback on the main thread when if downloads successfully
def OpenURL(url: str, bad_callback: classmethod):
    user_agent = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.0.7) Gecko/2009021910 Firefox/3.0.7'
    headers = {'User-Agent': user_agent, }

    request = urllib.request.Request(url, None, headers)
    try:
        response = urllib.request.urlopen(request)
    except urllib.error.URLError as F:
        PrintException(F, "Error Opening URL: ", url)
        return
    except CertificateError:
        return
    
    try:
        bad_callback(url, response)
    except TypeError as F:
        PrintException(F, "TypeError Calling Callback for Downloading URL: ", url)
    except Exception as F:
        PrintException(F, "Error Calling Callback for Downloading URL: ", url)
        
        
class DataStorage:
    def __init__(self):
        self.data = b""
        
    def AddData(self, *args):
        self.data += added_data
        
        
class FTPDownloadThread(Thread):
    def __init__(self):
        super().__init__()
        self.queue = []
        self.ftp = {}
        
    def run(self):
        while True:
            if self.queue:
                ftp_address, url, bad_callback = self.queue[0]
                
                if not url.startswith("ftp://server/"):
                    self.queue.remove(self.queue[0])
                    sleep(0.1)
                    continue
                
                address = f"ftp://{self.ftp[ftp_address].host}:{self.ftp[ftp_address].port}/"
                
                url = url.replace("ftp://server/", address)
                    
                base_path = url.split(address)[1]
                if self.ftp[ftp_address].isfile(base_path):
                    dl_name = f"tmp_download/{base_path}"  # i don't care right now
                    if not os.path.isfile(dl_name):
                        with open(dl_name, "wb") as dl_file:
                            self.ftp[ftp_address].retrbinary(f"RETR {base_path}", dl_file.write, 1024)
                        # self.ftp.retrbinary(f"RETR {base_path}", data.AddData, 1024)
            
                    data = b""
                    with open(dl_name, "rb") as dl_file:
                        data += dl_file.read()
                    
                    try:
                        bad_callback(url, data)
                    except TypeError as F:
                        PrintException(F, "TypeError Calling Callback for Downloading URL: ", url)
                    except Exception as F:
                        PrintException(F, "Error Calling Callback for Downloading URL: ", url)
                        
                self.queue.remove(self.queue[0])
            sleep(0.1)
            
            
FTP_THREAD = FTPDownloadThread()
        
        
def FTPOpenURL(ftp: ftplib.FTP, url: str, bad_callback: classmethod):
    FTP_THREAD.queue.append((ftp.address, url, bad_callback))
    
    
class BaseEmbed(QLabel):
    def __init__(self, parent: QWidget, path: str):
        super().__init__(parent)
        self.path = path
    
    
class VideoEmbed(BaseEmbed):
    def __init__(self, parent: QWidget, path: str):
        super().__init__(parent, path)
        self.UpdateImageSize(600, 800)
        
        
class BaseImageView(QGraphicsView):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.parent = parent
        self._empty = True
        self._scene = QGraphicsScene(self)
        self._photo = QGraphicsPixmapItem()
        self._scene.addItem(self._photo)
        self.setScene(self._scene)
        
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor(25, 25, 25)))
        self.setFrameShape(QFrame.NoFrame)
        self.setFocusPolicy(Qt.NoFocus)
    
    def RemovePhoto(self) -> None:
        self._empty = True
        self.setDragMode(QGraphicsView.NoDrag)
        self._photo.setPixmap(QPixmap())

    def HasPhoto(self) -> bool:
        return not self._empty
    
    def SetImageFromData(self, data: bytes) -> bool:
        pix_map = QPixmap()
        pix_map.loadFromData(data)
        
        if pix_map and not pix_map.isNull():
            self._empty = False
            self._photo.setPixmap(pix_map)
            self.fitInView(False)
            return True
        else:
            self.RemovePhoto()
            return False
        

class ImageEmbed(BaseEmbed):
    def __init__(self, parent: QWidget, path: str, data: bytes):
        super().__init__(parent, path)
        self.image_pixmap = QPixmap()
        self.image_pixmap.loadFromData(data)
        self.UpdateImageSize(800, 600)

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


class ImageEmbedWIP(BaseImageView):
    photoClicked = pyqtSignal(QPoint)
    
    def __init__(self, parent: QWidget, path: str, data: bytes):
        super().__init__(parent)
        self._zoom = 0
        # self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        # self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # self.setBackgroundBrush(QBrush(QColor(25, 25, 25)))
        # self.setFrameShape(QFrame.NoFrame)
        self.setFocusPolicy(Qt.NoFocus)
        
        if not self.SetImageFromData(data):
            print("Image doesn't exist: " + path)
    
    # TODO: this doesn't actually do anything right now when set to False, oof
    #  should reset the zoom
    def fitInView(self, scale=False, scale_down=False):
        rect = QRectF(self._photo.pixmap().rect())
        if not rect.isNull():
            self.setMaximumWidth(rect.width())
            self.setMaximumHeight(rect.height())
            self.setSceneRect(rect)
            if self.HasPhoto():
                unity = self.transform().mapRect(QRectF(0, 0, 1, 1))
                self.scale(1 / unity.width(), 1 / unity.height())
                viewrect = self.viewport().rect()
                scenerect = self.transform().mapRect(rect)
                
                if scale:
                    factor = min(viewrect.width() / scenerect.width(),
                                 viewrect.height() / scenerect.height())
                    self.scale(factor, factor)
                
                elif scale_down:
                    w_factor = 1.0
                    h_factor = 1.0
                    
                    if scenerect.width() > viewrect.width():
                        w_factor = viewrect.width() / scenerect.width()
                    
                    if scenerect.height() > viewrect.height():
                        h_factor = viewrect.height() / scenerect.height()
                    
                    factor = min(w_factor, h_factor)
                    self.scale(factor, factor)
            self._zoom = 0
    
    # might have a overlay preview window similar to discord
    # or an entirely separate window for an image viewer
    def wheelEvent(self, event):
        if False:  # self.HasPhoto():
            if event.angleDelta().y() > 0:
                factor = 1.25
                self._zoom += 1
            else:
                factor = 0.8
                self._zoom -= 1
            
            self.scale(factor, factor)
    
    # Unused?
    def toggleDragMode(self):
        if self.dragMode() == QGraphicsView.ScrollHandDrag:
            self.setDragMode(QGraphicsView.NoDrag)
        elif not self._photo.pixmap().isNull():
            self.setDragMode(QGraphicsView.ScrollHandDrag)
    
    def mousePressEvent(self, event):
        if self._photo.isUnderMouse():
            self.photoClicked.emit(QPoint(event.pos()))
        super().mousePressEvent(event)


