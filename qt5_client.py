import sys
import datetime
import uuid

from threading import Thread
from urllib.parse import urlparse
from urllib.response import addinfourl
from qt5_bookmark_manager import BookmarkManager
from qt5_client_embed import *
from api2.client import Client, ServerCache
from api2.shared import TimePrint, GetTime24Hour, UnixToDateTime, Packet, PrintWarning, PrintError
from api2.video_player import VideoPlayer

import ftplib

from time import sleep, perf_counter

# for pycharm, install pyqt5-stubs, so you don't get 10000 errors for no reason
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget

# also need to install PyQtWebEngine
# for linux, do apt-get install python3-pyqt5.qtwebengine
# from PyQt5.QtWebEngineWidgets import *
# from PyQt5.QtWebEngineCore import *

from time import perf_counter, sleep


DEFAULT_PFP_PATH = "doge.png"
UPLOADING_FILES = set()


# JUST DIE
if not os.path.isdir("tmp_upload"):
    os.mkdir("tmp_upload")


def ThreadPrint(thread, *args):
    print("[{0} - {1}] {2}".format(GetTime24Hour(), thread, str(*args)))


def RemoveWidgets(layout: QLayout) -> None:
    try:
        for i in reversed(range(layout.count())):
            try:
                layout.itemAt(i).widget().setParent(None)
            except AttributeError:
                continue
    except Exception as F:
        PrintException(F, "Error Removing Widgets")


def IsValidURL(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False
    
    
def CheckForURLs(text: str) -> dict:
    url_dict = {}
    text_split_lines = text.splitlines()
    for text_line in text_split_lines:
        text_split = text_line.split(" ")
        start = 0
        end = 1
        current_url = ""
        while end < len(text_split) + 1:
            string = " ".join(text_split[start:end])
            if IsValidURL(string):
                current_url = string
                end += 1
            elif current_url:
                url_dict[string] = GetEmbedTypeExt(string)
                start = end
                end += 1
            else:
                start += 1
                end += 1
        if current_url:
            url_dict[current_url] = GetEmbedTypeExt(current_url)
    return url_dict
    
    
def RemoveVideoPlayer(embed: VideoPlayer):
    if type(embed) == VideoPlayer:
        embed.player.quit()
        if embed.player.handle:
            embed.player.terminate()
        del embed.player
        embed.position_thread.stop()
    del embed
    
    
class TextBox(QTextEdit):
    sig_send = pyqtSignal()
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setReadOnly(True)
        # self.text_input.setMaximumHeight(200)
        
    def canInsertFromMimeData(self, source: QMimeData) -> bool:
        return source.hasImage() or source.hasText() or super().canInsertFromMimeData(source)
        
    def insertFromMimeData(self, source: QMimeData):
        if source.hasText():
            self.insertPlainText(source.text())
        elif source.hasImage():
            # JUST DIE
            rng_name = "tmp_upload/unknown_" + str(uuid.uuid4()) + ".png"  # i don't care right now
            ass = source.imageData().save(rng_name)
            self.insertPlainText("file:///" + os.getcwd().replace("\\", "/") + "/" + rng_name)
    
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if Qt.ShiftModifier != event.modifiers():
            if key in {Qt.Key_Return, Qt.Key_Enter}:
                self.sig_send.emit()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)
    

class ChatBox(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(QMargins(0, 0, 0, 0))
        self.setFixedHeight(64)
        # self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        # TODO: use something better than QLineEdit, for multi-line stuff
        #  and maybe even support markdown in the future
        self.text_input = TextBox(self)
        self.text_input.sig_send.connect(self.SendMessage)
        # self.text_input.returnPressed.connect(self.SendMessage)

        # send_button = QPushButton("send")
        # send_button.pressed.connect(self.SendMessage)

        self.layout().addWidget(self.text_input)
        # self.layout().addWidget(send_button)
    
    def Enable(self):
        self.text_input.setReadOnly(False)
    
    def Disable(self):
        self.text_input.setReadOnly(True)
        
    @staticmethod
    def GetFilesForUpload(text: str) -> list:
        file_list = []
        text_split_lines = text.splitlines()
        for text_line in text_split_lines:
            if "file:///" in text_line:
                text_split = text_line.split(" ")
                start = 0
                end = 1
                while end < len(text_split) + 1:
                    file_path = " ".join(text_split[start:end])
                    # file:/// = 8 chars
                    bruh = os.path.isfile(os.path.normpath(file_path[8:]))
                    if file_path not in file_list and os.path.isfile(os.path.normpath(file_path[8:])):
                        file_list.append(file_path)
                        start = end
                    end += 1
        return file_list
        
    def AutoUploadFromMessageText(self, text: str) -> str:
        ftp = GET_SERVER_CACHE().ftp
        if "file:///" in text:
            ftp_url = ftp.get_var_url() + ftp.get_attachments_folder()
        
            file_list = self.GetFilesForUpload(text)
            
            for file_url in file_list:
                file_name = os.path.basename(file_url)
                ftp_path = ftp_url + file_name
                text = text.replace(file_url, ftp_path)
                file = file_url[8:]
                main_window.ftp_explorer.ui_file_transfer.add_item(file, os.path.getsize(file), os.path.basename(file))
                ftp.upload_file(file, ftp.get_attachments_folder())
                UPLOADING_FILES.add(ftp_path)
        
        return text

    @pyqtSlot()
    def SendMessage(self):
        text = self.text_input.toPlainText()
        if text:
            server = main_window.server_list.GetSelectedServerCache()
            text = self.AutoUploadFromMessageText(text)
            message_dict = server.SendMessage(main_window.chat_view.current_channel, text)
            main_window.chat_view.SendMessage(message_dict)
            self.text_input.setText("")


class MessageView(QWidget):
    sig_embed = pyqtSignal(str, HTTPResponse)
    sig_embed_ftp = pyqtSignal(str, bytes)

    def __init__(self, msg_id: int, unix_time, sender: str, text: str, client_is_sender: bool = False):
        super().__init__()
        self.msg_id = msg_id
        self.setLayout(QHBoxLayout())

        self.user_image_layout = QVBoxLayout()
        self.content_layout = QVBoxLayout()
        self.header_layout = QHBoxLayout()
        self.message_layout = QVBoxLayout()
        
        self.setLayout(self.message_layout)

        # image_label = QLabel(self)
        # image_label.setPixmap(QPixmap(DEFAULT_PFP_PATH))

        self.user_image = QLabel()
        self.user_id = sender
        
        server = main_window.server_list.GetSelectedServerCache()
        try:
            self.user = server.member_list[sender]
            self.name = QLabel(self.user[0])
        except KeyError:
            PrintWarning("WARNING: member doesn't exist? " + sender)
            self.user = sender
            self.name = QLabel(sender)
        
        if client_is_sender:
            self.time = QLabel("message sending...")
        else:
            # TODO: format time based on computer settings
            self.time = QLabel(UnixToDateTime(unix_time).strftime("%Y-%m-%d - %H:%M:%S"))
        
        self.text = QLabel(text)
        if client_is_sender:
            # TODO: need something for different themes, like disabled text color or something
            # palette = self.palette()
            # palette.setColor(self.backgroundRole(), Qt.red)
            # self.setPalette(palette)
            self.text.setStyleSheet("color: #737373;")
        
        self.name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.time.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.text.setWordWrap(True)

        self.user_image_layout.addWidget(self.user_image)
        self.user_image_layout.addStretch(1)

        self.layout().addLayout(self.user_image_layout)
        self.layout().addLayout(self.content_layout)

        self.content_layout.addLayout(self.header_layout)
        self.content_layout.addLayout(self.message_layout)
        self.content_layout.setContentsMargins(QMargins(0, 0, 0, 0))

        profile_pic_size = 32
        profile_pic = QPixmap(DEFAULT_PFP_PATH).scaledToHeight(profile_pic_size).scaledToWidth(profile_pic_size)
        self.user_image.setPixmap(profile_pic)

        bold_font = QFont()
        bold_font.setBold(True)
        self.name.setFont(bold_font)

        self.header_layout.addWidget(self.name)
        self.header_layout.addWidget(self.time)
        self.header_layout.addStretch(1)

        self.message_layout.addWidget(self.text)
        self.message_layout.addStretch(1)
        # self.text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.layout().setContentsMargins(QMargins(0, 0, 0, 0))
        self.layout().setSpacing(6)
        self.setMaximumWidth(900)
        self.setContentsMargins(QMargins(0, 0, 0, 0))

        self.sig_embed.connect(self.EmbedDownloadCallbackHTTP)
        self.sig_embed_ftp.connect(self.EmbedAddImage)

        self.embed_urls = set()
        self.embed_list = []
        self.url_dict = CheckForURLs(self.text.text())
        
        # TODO: limit the max download thread count
        self.text.setOpenExternalLinks(True)
        if self.url_dict:
            ftp = GET_SERVER_CACHE().ftp
            for url in self.url_dict:
                if url.startswith("ftp://server/"):
                    ftp_url = ftp.add_address(url)
                    self.EmbedReplaceURL(url, ftp_url)
                    if url not in UPLOADING_FILES:
                        self.EmbedAdd(url)
                else:
                    self.EmbedReplaceURL(url, url)
                    self.EmbedAdd(url)

    def FinishedSending(self, new_time=None):
        self.time.setText(UnixToDateTime(new_time).strftime("%Y-%m-%d - %H:%M:%S"))
        self.text.setStyleSheet("")
        
    def EmbedReplaceURL(self, url: str, link_url: str):
        text = self.text.text()
        text = text.replace(url, f"<a href=\"{link_url}\">{url}</a>").replace("\n", "<br>")
        self.text.setText(text)
        
    def EmbedAdd(self, url: str):
        # awful
        if url in self.embed_urls:
            return

        self.embed_urls.add(url)
        embed_type = GetEmbedTypeExt(url)
        if embed_type in {EmbedType.IMAGE, EmbedType.VIDEO, EmbedType.AUDIO}:
            
            # TODO: check if this is one of our ~~holograms~~ ftp servers saved
            if url.startswith("ftp://"):
                # HACKY
                embed_type = GetEmbedTypeExt(url)
                
                if embed_type == EmbedType.IMAGE:
                    bad_download_thread = Thread(target=FTPOpenURL, args=(GET_SERVER_CACHE().ftp, url, self.sig_embed_ftp.emit))
                    bad_download_thread.start()
                    
                elif embed_type in {EmbedType.VIDEO, EmbedType.AUDIO}:
                    self.EmbedAddVideo(url)
            else:
                bad_download_thread = Thread(target=OpenURL, args=(url, self.sig_embed.emit))
                bad_download_thread.start()
            
    def EmbedAddVideo(self, url: str):
        video_embed = VideoPlayer(self)
        # video_embed.set_video_path(url)
        video_embed.load_video(url)
        # video_embed.show()
        self.embed_list.append(video_embed)
        self.message_layout.addWidget(video_embed)
            
    def EmbedAddImage(self, url, data: bytes):
        image_embed = ImageEmbed(main_window.chat_view, url, data)
        self.embed_list.append(image_embed)
        self.message_layout.addWidget(image_embed)

    def EmbedDownloadCallbackFTP(self, url: str, opened_url: bytes) -> None:
        self.EmbedDownloadCallback(url, opened_url)

    def EmbedDownloadCallbackHTTP(self, url: str, opened_url: HTTPResponse) -> None:
        self.EmbedDownloadCallback(url, opened_url)

    def EmbedDownloadCallback(self, url: str, opened_url) -> None:
        # will use when finished
        # embed_type = GetEmbedTypeBytes(opened_url)
        embed_type = GetEmbedTypeExt(url)
        
        if embed_type == EmbedType.IMAGE:
            self.EmbedAddImage(url, opened_url.read())
        elif embed_type in {EmbedType.VIDEO, EmbedType.AUDIO}:
            self.EmbedAddVideo(url)


class ChatView(QScrollArea):
    sig_add_message = pyqtSignal(int, tuple)
    
    def __init__(self, parent):
        super().__init__(parent)
        # QtWidgets.QAbstractItemView.ExtendedSelection
        self.message_contents_widget = QWidget()
        self.message_contents_layout = QVBoxLayout()
        self.message_contents_layout.addStretch(1)
        self.message_contents_widget.setLayout(self.message_contents_layout)
        self.setWidget(self.message_contents_widget)
        
        self.setWidgetResizable(True)
        # self.setContentsMargins(QMargins(0, 0, 0, 0))
        self.message_contents_widget.setContentsMargins(QMargins(0, 0, 0, 0))
        
        self.current_channel = ""
        self.messages = {}
        self.sending_messages = []
        self.messages_list = []
        
        self._last_scroll_value = -1
        self._last_scroll_max = -1
        self._scroll_stay_in_place = False

        self.verticalScrollBar().rangeChanged.connect(self.ScrollRangeChanged)
        self.verticalScrollBar().valueChanged.connect(self.ScrollValueChanged)

        self.sig_add_message.connect(self.AddMessage)
        
        # self.message_contents_layout.setContentsMargins(QMargins(0, 0, 0, 0))
        # self.message_contents_layout.setSpacing(0)
        self.message_contents_layout.addStretch(0)
        # self.message_contents_widget.setStyleSheet("border: 2px solid; border-color: #660000;")

    def GetLayout(self):
        # return self.widget().layout()
        return self.message_contents_layout
    
    def GetMainWindow(self):
        return self.parent().parent().parent()  # ew
        
    def SetChannel(self, channel_name: str) -> None:
        self.current_channel = channel_name
        self.messages.clear()
        self.RemoveEmbeds()
        RemoveWidgets(self.GetLayout())
        main_window.chat_box.Enable()
        self._last_scroll_value = -1
        self._last_scroll_max = -1
        self._scroll_stay_in_place = False
        
    # This is required thanks to mpv, or maybe just python, not functioning the way i expect
    # if you play a video with mpv, and then switch to a different channel, qt just freezes,
    # but not in the not responding way, just you can't interact with anything
    # i noticed that the mpv deconstructor is just not being called with del,
    # so i just copy the 2 lines in it's deconstructor, and guess what? that solves the problem
    # so that means i just have to manually deconstruct it just to get it to function correctly lmao
    def RemoveEmbeds(self):
        for i in reversed(range(self.GetLayout().count())):
            try:
                widget = self.GetLayout().itemAt(i).widget()
                if type(widget) == MessageView:
                    for embed in widget.embed_list:
                        RemoveVideoPlayer(embed)
                widget.setParent(None)
            except AttributeError:
                continue
        
    def Clear(self):
        self.messages.clear()
        self.RemoveEmbeds()
        RemoveWidgets(self.GetLayout())
        main_window.chat_box.Disable()
        
    # json stores keys for dictionaries as a string only, and min in python for strings
    @staticmethod
    def GetMinMessageIndex(messages: dict) -> int:
        return min(map(int, messages.keys()))
        
    @staticmethod
    def GetMaxMessageIndex(messages: dict) -> int:
        return max(map(int, messages.keys()))
    
    def GetNewestMessageIndex(self) -> int:
        return max(map(int, self.messages.keys())) + 1

    # TODO: use QListModel or something and prepend and append messages to it
    #  get the min and max indexes from the dictionary and use a while loop to get the messages sorted
    #  for removing messages, just remove it from QListModel, easy (hopefully)
    #  also need to make adding messages more efficient, the current way is way too slow
    # total message count
    def MessageUpdate(self, packet: Packet) -> None:
        channel = packet.content
        if not channel["messages"]:
            return
        start_time = perf_counter()
        dict_index = 0
        channel["messages"] = {int(k): v for k, v in channel["messages"].items()}
        index = int(min(channel["messages"]))
        # index = self.GetMinMessageIndex(channel["messages"])
        # while index <= self.GetMaxMessageIndex(channel["messages"]):
        while index <= max(channel["messages"]):
            message = channel["messages"][index]
            # msg_start_time = perf_counter()
            self.AddMessage(index, message)
            # print("made message view in " + str(perf_counter() - msg_start_time) + " seconds")
            index += 1
            dict_index += 1
        TimePrint("adding messages time: " + str(perf_counter() - start_time))
    
    def AddMessage(self, index: int, message: list, message_sending: bool = False) -> None:
        if index in self.messages:
            TimePrint(f"message already added? {message}")
        # what this does is go through all the messages in a list of the message indexes
        # this is so we can insert a message in the correct spot
        # probably slow and very messy, but idc right now, it works, i can change it later
        # i only do this because of how the messages are stored in the qt layout
        # can't use models (i think) because those seem to be for basic things
        # and i want to be able to view images, videos, and other embedded content in here
        min_index = -1
        # make a list of the message indexes
        message_list = list(self.messages.keys())
        # sort that list by smallest to biggest
        message_list.sort()
        # go through each message index
        for list_index, message_index in enumerate(message_list):
            if message_index < index:
                # set the min_index to the index of the message_index
                # so we can insert this message after that one
                min_index = list_index
            elif message_index > index:
                # break if we find a message index greater than this one
                # so we can insert this message before it
                break
            else:
                # must be the same message index (somehow), so don't add it
                print("message already added")
                return

        # insert the message after this one (+1) and skip the spacer (another +1)
        insert_index = min_index + 2
        message_qt = MessageView(index, *message, message_sending)
        self.messages[index] = message_qt
        # increment by 1 to skip the spacer we have
        self.message_contents_layout.insertWidget(insert_index, message_qt)
        
    def RemoveMessage(self, event) -> None:
        pass
        
    # editing a message
    def EditMessage(self, event) -> None:
        pass
    
    # message has been updated
    def UpdateMessage(self, event) -> None:
        pass
    
    def SendMessage(self, message_dict: dict) -> None:
        # msg_id: int, unix_time, sender: str, text: str, file: str = "", client_is_sender
        msg_id = 0 if not self.messages else max(map(int, self.messages.keys())) + 1
        message_qt = MessageView(msg_id, message_dict["time"], message_dict["name"], message_dict["text"], True)
        self.messages[msg_id] = message_qt
        self.sending_messages.append((message_dict, message_qt))
        self.message_contents_layout.addWidget(message_qt)
            
    def CheckForSendingMessage(self, message_dict: dict) -> bool:
        message_compare = message_dict.copy()
        del message_compare["recv"]
        
        for message_list in self.sending_messages:
            if message_list[0] == message_compare:
                message_qt = message_list[1]
                message_qt.FinishedSending(message_dict["recv"])
                return True
        return False
    
    # TODO: this isn't really working the way i want it to right now
    #  need to be able to prepend messages (that QModel thing?)
    #  also need to check if we already have the messages, just grabs the message again for some reason
    def ScrollValueChanged(self, value: int) -> None:
        if not main_window.server_list.IsServerSelected():
            return
        
        server = main_window.server_list.GetSelectedServerCache()
        self._last_scroll_value = value
        if not self.messages or len(self.messages) == server.message_channels[self.current_channel]["count"]:
            return
        
        # top/left end
        if value == self.verticalScrollBar().minimum():
            # request older messages
            if min(self.messages) > 0:
                server.RequestChannelMessageRange(self.current_channel, min(self.messages))
                self._scroll_stay_in_place = True

        # bottom/right end
        elif value == self.verticalScrollBar().maximum():
            # request newer messages
            if max(self.messages) < server.message_channels[self.current_channel]["count"] - 1:
                server.RequestChannelMessageRange(self.current_channel, max(self.messages), "forward")
                self._scroll_stay_in_place = True

    def ScrollRangeChanged(self, min_value: int, max_value: int) -> None:
        if self._last_scroll_value == -1:
            self.verticalScrollBar().setValue(max_value)
        elif self._last_scroll_max != -1:
            if self._scroll_stay_in_place:
                self.verticalScrollBar().setValue(max_value - self._last_scroll_max)
                self._scroll_stay_in_place = False
            elif self._last_scroll_max == self._last_scroll_value:
                self.verticalScrollBar().setValue(max_value)
                
        self._last_scroll_max = max_value
        
    def IsScrollBarAtMax(self) -> bool:
        return self.verticalScrollBar().value() == self.verticalScrollBar().maximum()
        
    def IsScrollBarAtMin(self) -> bool:
        return self.verticalScrollBar().value() == self.verticalScrollBar().minimum()


class MenuBar(QMenuBar):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.bookmarks_manager = BookmarkManager(parent)
        # self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Maximum)
        '''
        self.menu_bookmarks = self.addMenu("Bookmarks")

        if self.parent().client.user_config.bookmarks:
            # spacer_01 = self.menu_bookmarks.addSeparator()
            server_list = []
            for bookmark in self.parent().client.user_config.bookmarks:
                bookmark_action = self.menu_bookmarks.addAction(bookmark.name, self.bookmark_clicked)
        '''

    @pyqtSlot()
    def bookmark_clicked(self):
        pass
        # get the bookmark index from the bookmark menu actions
        # and use that index to get the bookmark in the user config
        # bookmark = self.parent().client.user_config.bookmarks[self.menu_bookmarks.actions().index(self.sender())]
        # self.parent().ConnectToServer(bookmark.ip, bookmark.port)
        
        
class ServerButton(QListWidgetItem):
    def __init__(self, server_name: str, address: str) -> None:
        super().__init__()
        self._server_name = server_name
        self._address = address
        self.setText(server_name)
        self._enabled_flags = self.flags()
        self.Disable()
        
    def GetServerAddress(self) -> str:
        return self._address
        
    def GetServerName(self) -> str:
        return self._server_name
        
    def GetServerCache(self) -> ServerCache:
        return main_window.client.GetServerCache(self._address)
        
    def SetServerName(self, server_name: str) -> None:
        self._server_name = server_name
        self.setText(server_name)
        
    def Enable(self) -> None:
        self.setFlags(self._enabled_flags)
        
    def Disable(self) -> None:
        self.setFlags(Qt.NoItemFlags)


class ServerList(QListWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(160)  # TODO: make this able to resize
        self.itemSelectionChanged.connect(self.ServerSelected)
        self.server_address_dict = {}

    def SetServers(self, server_address_dict: dict) -> None:
        self.clear()
        self.server_address_dict = server_address_dict
        for address, server_name in server_address_dict.items():
            self.addItem(ServerButton(server_name, address))
            
    def GetServerButton(self, address: str) -> ServerButton:
        for i in range(self.count()):
            server_button = self.item(i)
            if server_button.GetServerAddress() == address:
                return server_button
            
    def GetSelectedServerCache(self) -> ServerCache:
        return main_window.client.GetServerCache(self.GetSelectedServerAddress())
    
    def IsServerSelected(self) -> bool:
        return self.currentRow() != -1

    @pyqtSlot()
    def ServerSelected(self) -> None:
        server_cache = self.GetSelectedServerCache()
        if self.IsServerSelected():
            main_window.ftp_explorer_button.setEnabled(True)
            main_window.ftp_explorer.ui_file_transfer.SwitchServer()
            main_window.channel_list.SetChannels(server_cache.message_channels)
        else:
            main_window.ftp_explorer_button.setEnabled(False)
            main_window.ftp_explorer.hide()
            main_window.channel_list.clear()

    def GetSelectedServerName(self) -> str:
        return self.item(self.currentRow()).text()
    
    def GetSelectedServerAddress(self) -> str:
        return self.item(self.currentRow()).GetServerAddress()
        
        
class ChannelList(QListWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(160)
        self.itemActivated.connect(self.ChannelSelected)
        self.itemClicked.connect(self.ChannelSelected)
        self.channel_name_list = {}

    def SetChannels(self, channel_dict: dict) -> None:
        self.clear()
        self.channel_name_list = channel_dict
        for room in channel_dict:
            self.addItem(QListWidgetItem(room))

    @pyqtSlot()
    def ChannelSelected(self, *ass) -> None:
        channel_name = self.GetSelectedChannelName()
        main_window.chat_view.SetChannel(channel_name)
        server = main_window.server_list.GetSelectedServerCache()
        server.RequestChannelMessageRange(channel_name, server.message_channels[channel_name]["count"])
        
    def GetChannelButton(self, channel_name: str) -> QListWidgetItem:
        for i in range(self.count()):
            channel_button = self.item(i)
            if channel_button.text() == channel_name:
                return channel_button

    def GetSelectedChannelName(self) -> str:
        return self.item(self.currentRow()).text()

    def GetSelectedChannel(self) -> tuple:
        room_id = self.channel_name_list[self.currentRow()]
        room = self.channel_name_list[room_id]
        return room_id, room
    
    
class BaseFileListView(QTreeView):
    def __init__(self, parent, file_list: QStandardItemModel):
        super().__init__(parent)
        self.setModel(file_list)

        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        
        self.header().setMinimumSectionSize(40)
        self.header().setStretchLastSection(False)
        
    def SetColumnProperties(self, index: int = 0):
        while index < self.header().count():
            # self.header().setSectionResizeMode(index, QHeaderView.ResizeToContents)
            self.header().resizeSection(index, 200)
            index += 1
        
    def GetSelectedFiles(self) -> list:
        file_list = [item.data() for item in self.selectedIndexes() if item.column() == 0]
        return file_list
    
    def EnterEvent(self):
        pass
    
    def keyPressEvent(self, event: QKeyEvent) -> None:
        super().keyPressEvent(event)
        if event.key() in {Qt.Key_Enter, Qt.Key_Return}:
            self.EnterEvent()
        
    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        super().mouseDoubleClickEvent(e)
        if self.selectedIndexes():
            self.EnterEvent()


class FileListView(BaseFileListView):
    def __init__(self, parent, file_list: QStandardItemModel):
        super().__init__(parent, file_list)
        self.parent = parent
        self.setModel(file_list)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.header().resizeSection(1, 120)
        self.header().resizeSection(2, 80)
        self.header().resizeSection(3, 80)
        
        self.header().setMinimumSectionSize(40)
        self.header().setStretchLastSection(False)
    
    def EnterEvent(self):
        file_list = self.GetSelectedFiles()
        
        ftp = GET_SERVER_CACHE().ftp
        if len(file_list) == 1:
            file_path = file_list[0]
            
            if ftp.isfile(file_path):
                ftp.download_file(file_path, self.GetOutputFile(file_path))
                self.parent.ui_file_transfer.add_item(
                    file_path, ftp.file_list[file_path]["size"], self.GetOutputFile(file_path))
                pass
                
            elif ftp.isdir(file_path):
                ftp.cwd(file_path)
                self.parent.SetDir("/" + file_path)
        else:
            for file_path in file_list:
                if ftp.isfile(file_path):
                    ftp.download_file(file_path, self.GetOutputFile(file_path))
                    self.parent.ui_file_transfer.add_item(
                        file_path, ftp.file_list[file_path]["size"], self.GetOutputFile(file_path))
                    
    def GetOutputFile(self, file_path: str) -> str:
        return self.parent.dl_folder.text() + "/" + os.path.basename(file_path)


class FileTransferView(BaseFileListView):
    def __init__(self, parent, file_list: QStandardItemModel):
        super().__init__(parent, file_list)
        self.setModel(file_list)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.header().resizeSection(1, 300)
        self.header().resizeSection(2, 80)
        self.header().resizeSection(3, 80)
        self.header().resizeSection(4, 80)
        
        self.header().setMinimumSectionSize(40)
        self.header().setStretchLastSection(False)


class BaseFileList(QStandardItemModel):
    def __init__(self, *names):
        super().__init__()
        self.setColumnCount(len(names))
        
        index = 0
        while index < len(names):
            self.setHorizontalHeaderItem(index, QStandardItem(names[index]))
            index += 1
            
    def SwitchServer(self):
        pass
    
    def reset(self) -> None:
        self.removeRows(0, self.rowCount())
    
    def remove_item(self, file_path: str) -> None:
        pass
    
    def add_item(self, file_path: str, file_info: dict) -> None:
        self._add_item_row(self.rowCount(), file_path, file_info)
    
    def insert_item(self, row_index: int, file_path: str, file_info: dict) -> None:
        self.insertRow(row_index)
        self._add_item_row(row_index, file_path, file_info)
    
    def _add_item_row(self, row: int, file_path: str, file_info: dict) -> None:
        pass
        
    def _add_items_to_row(self, row, *items):
        for index, item in enumerate(items):
            item.setEditable(False)
            self.setItem(row, index, item)
    
    def _get_iter(self) -> iter:
        return range(0, self.rowCount())
    
    def get_file_item(self, file_path: str) -> QStandardItem:
        for file_index in self._get_iter():
            item = self.item(file_index)
            if item and item.text() == file_path:
                return item
    
    def get_file_row(self, file_path: str) -> int:
        return self.get_file_item(file_path).row()


class FileList(BaseFileList):
    def __init__(self):
        super().__init__("Name", "Date modified", "Type", "Size")
        
    def _add_item_row(self, row: int, file_path: str, file_info: dict) -> None:
        item_file_path = QStandardItem(file_path)
    
        ftp = GET_SERVER_CACHE().ftp
        if ftp.isdir(file_path):
            item_type = QStandardItem("Folder")
            size = ""
        else:
            item_type = QStandardItem(os.path.splitext(file_path)[1])
            size = str(bytes_to_megabytes(file_info["size"])) + " MB"
    
        # 20200516165223
        # 2020/05/16 - 16:52:23
        date_mod = datetime.datetime.strptime(file_info["modify"], "%Y%m%d%H%M%S")
        item_date_mod = QStandardItem(str(date_mod))
    
        item_size = QStandardItem(size)
    
        self._add_items_to_row(row, item_file_path, item_date_mod, item_type, item_size)


def get_file_size_str(file_path: str) -> str:
    if os.path.isfile(file_path):
        return str(bytes_to_megabytes(os.path.getsize(file_path))) + " MB"
    else:
        return "0 MB"


def bytes_to_megabytes(bytes_: int) -> float:
    # use 1024 multiples for windows, 1000 for everything else
    return round(int(bytes_) * 0.00000095367432, 3) if os.name == "nt" else round(int(bytes_) * 0.000001, 3)


def get_date_modified(file_path: str) -> float:
    if os.path.isfile(file_path):
        if os.name == "nt":
            return os.path.getmtime(file_path)
        else:
            return os.stat(file_path).st_mtime
    return -1.0


def get_date_modified_datetime(file_path: str) -> datetime.datetime:
    unix_time = get_date_modified(file_path)
    mod_time = datetime.datetime.fromtimestamp(unix_time)
    return mod_time
    
    
# based off of teamspeak 3's ftp gui
class FTPFileExplorer(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.main_window = parent
        self.setLayout(QVBoxLayout())
        self.setWindowTitle("FTP File Explorer")
        self.resize(1000, 600)
        # self.file_manager = QListWidget()
        
        self.header = FileExplorerHeader(self)
        
        # download folder
        self.dl_folder = QLineEdit(self.main_window.client.dl_path)
        
        self.ui_file_list = FileList()
        self.ui_file_list_view = FileListView(self, self.ui_file_list)
        
        self.ui_file_transfer = FileTransferList()
        self.ui_file_transfer_view = FileTransferView(self, self.ui_file_transfer)

        self.layout().addWidget(self.header)
        self.layout().addWidget(self.ui_file_list_view)
        self.layout().addWidget(self.ui_file_transfer_view)
        self.layout().addWidget(self.dl_folder)
        
        self._file_dialog = QFileDialog()
        self.current_server = None
        
    def show(self):
        self.UpdateFileList()
        super().show()
        self.raise_()
        
    def ClearFiles(self):
        self.ui_file_list.reset()
        
    def DownloadFile(self, file_path: str, output_dir: str = ""):
        server = GET_SERVER_CACHE()
        
        if output_dir:
            if file_path in server.ftp.file_list:
                file_size = server.ftp.file_list[file_path]["size"]
            else:
                PrintWarning("File does not exist on FTP Server: ", file_path)
                return
            self.ui_file_transfer.add_item(file_path, file_size, output_dir)
            server.ftp.download_file(file_path, output_dir)
            
        else:
            server.ftp.download_file(file_path, self.dl_folder.text())
        
    def SetDir(self, directory: str):
        self.UpdateFileList()
        self.header.txt_path.setText(directory)
        
    def DeleteFile(self, path: str):
        ftp = GET_SERVER_CACHE().ftp
        if ftp.isfile(path):
            try:
                ftp.delete(path)
                self.UpdateFileList()
            except ftplib.error_perm:
                PrintError(f"Cannot Delete File: \"{path}\"")
        elif ftp.isdir(path):
            try:
                ftp.rmd(path)
                self.UpdateFileList()
            except ftplib.error_perm:
                PrintError(f"Cannot Delete Folder: \"{path}\"")
        
    def DeleteSelected(self):
        [self.DeleteFile(file) for file in self.ui_file_list_view.GetSelectedFiles()]
        
    @staticmethod
    def CreateDir(directory: str):
        ftp = GET_SERVER_CACHE().ftp
        if not ftp.isdir(directory):
            ftp.mkd(directory)
        
    def ChangeDir(self, directory: str):
        server = GET_SERVER_CACHE()
        base_path, folder_name = os.path.split(directory)
        if server.ftp.isdir(folder_name) or directory in {"/", ""}:
            server.ftp.cwd(directory)
            if not base_path.endswith("/"):
                base_path += "/"
            self.SetDir(base_path + folder_name)
        
    def UpdateFileList(self):
        server_cache = GET_SERVER_CACHE()
    
        # get list of filenames on server
        server_cache.ftp.list_dir()

        self.ClearFiles()
        for file_path, file_stat in server_cache.ftp.file_list.items():
            self.ui_file_list.add_item(file_path, file_stat)
        
    def BrowseFileForUpload(self):
        filename, path_filter = self._file_dialog.getOpenFileName()
        if filename:
            server_cache = GET_SERVER_CACHE()
            server_cache.ftp.upload_file(filename)
    
    
class FileExplorerHeader(QWidget):
    def __init__(self, file_explorer: FTPFileExplorer):
        super().__init__(file_explorer)
        self.parent = file_explorer
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        
        self.btn_del = QPushButton("del")
        self.btn_upload = QPushButton("upload")
        self.btn_up = QPushButton("up")
        self.btn_enter = QPushButton("enter")  # enter directory specified below
        self.btn_new_dir = QPushButton("new dir")  # create directory below (lazy)
        self.txt_path = QLineEdit("/")  # current directory
        
        self.btn_del.clicked.connect(self.parent.DeleteSelected)
        self.btn_upload.clicked.connect(self.parent.BrowseFileForUpload)
        self.btn_up.clicked.connect(self.BtnPressLeaveFolder)
        self.btn_enter.clicked.connect(self.BtnPressEnter)
        self.btn_new_dir.clicked.connect(self.BtnPressNewDir)

        self.btn_del.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_upload.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_up.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_enter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_new_dir.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        self.layout().addWidget(self.btn_del)
        self.layout().addWidget(self.btn_upload)
        self.layout().addWidget(self.btn_up)
        self.layout().addWidget(self.txt_path)
        self.layout().addWidget(self.btn_enter)
        self.layout().addWidget(self.btn_new_dir)
        
    def BtnPressNewDir(self):
        self.parent.CreateDir(self.txt_path.text())
        
    def BtnPressLeaveFolder(self):
        folder = self.txt_path.text()
        if folder != "/":
            self.parent.ChangeDir(os.path.split(folder)[0])
        
    def BtnPressEnter(self):
        self.parent.ChangeDir(self.txt_path.text())
        
        
class FileTransferProgress(QWidget):
    def __init__(self, parent: FTPFileExplorer):
        super().__init__(parent)
        self.parent = parent
        self.file_list = FileTransferList()
        
    def DownloadFile(self, file_path: str, output_dir: str = ""):
        server = GET_SERVER_CACHE()
        file_stat = server.ftp.file_list["file_path"]

        output_file = output_dir + "/" + os.path.basename(file_path)
        
        with open(output_dir + "/" + os.path.basename(file_path), "wb") as out_file:
            server.ftp.retrbinary("RETR " + file_path, out_file.write, 8 * 1024)


class ProgressBarItem(QStandardItem):
    def __init__(self):
        super().__init__()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.setData(self.progress_bar)
        
    def data(self, role=None, *args, **kwargs) -> QProgressBar:
        return self.progress_bar


class FileTransferList(BaseFileList):
    sig_progress = pyqtSignal(str, float)
    
    def __init__(self):
        super().__init__("Name", "Output File", "Size", "Transfer", "Progress")
        self.sig_progress.connect(self.update_progress)
        
    def SwitchServer(self):
        ftp = GET_SERVER_CACHE().ftp
        ftp.uploader.callback = self.sig_progress.emit
        ftp.downloader.callback = self.sig_progress.emit
        
    def update_progress(self, file_path: str, progress: float):
        file_item = self.get_file_item(file_path)
        item_progress = self.item(file_item.row(), 4)
        # item_progress_bar = self.item(file_item.row(), 5)
        
        progress_str = f"{round(progress * 100, 2)}%"
        item_progress.setText(progress_str)
        # item_progress_bar.data().setValue(int(progress * 100))
        
        # awful, add the embed for it after it's finished being uploaded
        if progress * 100 >= 100:
            ftp = GET_SERVER_CACHE().ftp
            ftp_url_end = ftp.get_attachments_folder() + os.path.basename(file_path)
            ftp_url = ftp.get_base_url() + ftp_url_end
            for message in main_window.chat_view.messages.values():
                if type(message) == MessageView:
                    if ftp_url in message.text.text():
                        message.EmbedAdd(ftp.get_var_url() + ftp_url_end)
    
    def add_item(self, file_path: str, file_size: int, output_file: str) -> None:
        if not self.get_file_item(file_path):
            self._add_item_row(self.rowCount(), file_path, file_size, output_file)

    def _add_item_row(self, row: int, file_path: str, file_size: int, output_file: str) -> None:
        item_file_path = QStandardItem(file_path)
        item_output_file = QStandardItem(output_file)
    
        size = str(bytes_to_megabytes(file_size)) + " MB"
        item_size = QStandardItem(size)
        item_progress = QStandardItem("0.0%")
        
        # item_progress_bar = ProgressBarItem()
    
        self._add_items_to_row(
            row, item_file_path, item_output_file, item_size, QStandardItem(""), item_progress)


class MainWindow(QWidget):
    # sig_callback = pyqtSignal(str, dict)
    sig_callback = pyqtSignal(Packet)
    sig_connection_callback = pyqtSignal(str, bool)

    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.setWindowTitle("Demez Chat")
        self.client = Client()
        
        self.sig_connection_callback.connect(self.RunServerConnectionChangeCallback)
        self.client.SetServerConnectionChangeCallback(self.sig_connection_callback.emit)
        
        self.client.start()
        self.bookmarks_manager = BookmarkManager(self)
        # self.menu_bar = MenuBar(self)

        self.server_list = ServerList()
        self.chat_view = ChatView(self)
        self.channel_list = ChannelList()
        
        self.ftp_explorer_button = QPushButton("FTP File Explorer")
        self.ftp_explorer = FTPFileExplorer(self)
        self.ftp_explorer_button.clicked.connect(self.ftp_explorer.show)
        self.ftp_explorer_button.setEnabled(False)
        
        server_address_dict = {}
        for server in self.client.server_list:
            server_address_dict[server.address] = server.name
        
        self.server_list.SetServers(server_address_dict)

        # channel_chat_splitter = QSplitter()
        channel_chat_layout = QHBoxLayout()
        channel_layout_widget = QWidget()
        channel_layout_widget.setLayout(channel_chat_layout)

        self.chat_box = ChatBox(self)
        self.chat_box.show()

        chat_layout = QVBoxLayout()
        # chat_layout = QSplitter()
        chat_layout.addWidget(self.chat_view)
        chat_layout.addWidget(self.chat_box)
        # chat_layout.setOrientation(Qt.Vertical)
        # chat_layout.setCollapsible(0, False)
        # chat_layout.setCollapsible(1, False)
        # chat_layout.setStretchFactor(0, 2)
        # chat_layout.setStretchFactor(1, 0)
        # chat_layout.setMinimumSize(0, 160)
        # chat_layout.setContentsMargins(QMargins(0, 0, 0, 0))

        # chat_layout_widget = QWidget()
        # chat_layout_widget.setLayout(chat_layout)

        # self.layout().addWidget(self.menu_bar)
        # self.layout().addLayout(channel_chat_layout)
        self.layout().addWidget(channel_layout_widget)
        
        channel_layout = QVBoxLayout()
        channel_layout.addWidget(self.server_list)
        channel_layout.addWidget(self.channel_list)
        channel_layout.addWidget(self.ftp_explorer_button)

        channel_chat_layout.addLayout(channel_layout)
        channel_chat_layout.addLayout(chat_layout)
        # channel_chat_layout.addWidget(chat_layout)

        self.setMinimumSize(QSize(100, 100))
        self.resize(1200, 720)
        self.layout().setContentsMargins(QMargins(0, 0, 0, 0))

        # self.sig_view_channel.connect(self.chat_view.MessageUpdate)
        self.sig_callback.connect(self.HandleSignal)

        self.callbacks = {}

        self.AddCallback("channel_messages", self.chat_view.MessageUpdate)
        self.AddCallback("receive_message", self.ReceiveMessage)
        self.AddCallback("channel_list", self.Callback_SetChannels)

        self.show()

    def AddCallback(self, command: str, function: classmethod) -> None:
        self.callbacks[command] = function
        self.client.AddCallback(command, self.sig_callback.emit)

    def HandleSignal(self, packet: Packet) -> None:
        if packet.event in self.callbacks:
            self.callbacks[packet.event](packet)
        
    def RunServerConnectionChangeCallback(self, address: str, connected: bool) -> None:
        if connected:
            self.server_list.GetServerButton(address).Enable()
        else:
            server_button = self.server_list.GetServerButton(address)
            server_button.setSelected(False)
            server_button.Disable()
            if server_button.isSelected():
                self.channel_list.clear()
                self.chat_view.Clear()

    def ReceiveMessage(self, message: Packet) -> None:
        server_cache = self.server_list.GetSelectedServerCache()
        content = message.content
        channel = server_cache.message_channels[content["channel"]]
        message_tuple = [content["time"], content["name"], content["text"]]
        if content["name"] == server_cache.public_uuid:
            if not self.chat_view.CheckForSendingMessage(content):
                self.chat_view.AddMessage(channel["count"], message_tuple)
        else:
            self.chat_view.AddMessage(channel["count"], message_tuple)
        channel["count"] += 1
        
    def Callback_SetChannels(self, channel_list: Packet):
        if self.server_list.IsServerSelected():
            self.channel_list.SetChannels(channel_list.content)
        
    
# Back up the reference to the exceptionhook
sys._excepthook = sys.excepthook


def QtExceptionHook(exctype, value, traceback):
    # Print the error and traceback
    print(exctype, value, traceback)
    # Call the normal Exception hook after
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)


# Set the exception hook to our wrapping function
sys.excepthook = QtExceptionHook


def GET_SERVER_CACHE():
    server = main_window.server_list.GetSelectedServerCache()
    if server.ftp.address not in FTP_THREAD.ftp:
        FTP_THREAD.ftp[server.ftp.address] = server.ftp
    return server


if __name__ == "__main__":
    APP = QApplication(sys.argv)
    APP.setDesktopSettingsAware(True)
    main_window = MainWindow()
    FTP_THREAD.start()
    
    try:
        sys.exit(APP.exec_())
    except Exception as F:
        print(F)
        quit()
