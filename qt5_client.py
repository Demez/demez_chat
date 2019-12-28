import sys

from qt5_bookmark_manager import BookmarkManager
from api2.client import Client, ServerCache
from api2.shared import Command, TimePrint, GetTime24Hour, UnixToDateTime, UnixTo24Hour

# for pycharm, install pyqt5-stubs, so you don't get 10000 errors for no reason
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

from time import perf_counter, sleep


DEFAULT_PFP_PATH = "doge.png"


def ThreadPrint(thread, *args):
    print("[{0} - {1}] {2}".format(GetTime24Hour(), thread, str(*args)))


def RemoveWidgets(layout: QLayout) -> None:
    try:
        [layout.itemAt(i).widget().setParent(None) for i in reversed(range(layout.count()))]
    except AttributeError:
        return
    except Exception as F:
        print(F)


class ChatBox(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(QMargins(0, 0, 0, 0))

        # TODO: use something better than QLineEdit, for multi-line stuff
        #  and maybe even support markdown in the future
        self.text_input = QLineEdit()
        self.text_input.setReadOnly(True)
        self.text_input.returnPressed.connect(self.SendMessage)

        # send_button = QPushButton("send")
        # send_button.pressed.connect(self.SendMessage)

        self.layout().addWidget(self.text_input)
        # self.layout().addWidget(send_button)
    
    def Enable(self):
        self.text_input.setReadOnly(False)
    
    def Disable(self):
        self.text_input.setReadOnly(True)

    @pyqtSlot()
    def SendMessage(self):
        if self.text_input.text():
            server_cache = main_window.server_list.GetSelectedServerCache()
            server_cache.SendMessage(main_window.chat_view.current_channel, self.text_input.text())
            self.text_input.setText("")
            # TODO: have ChatView scroll down to bottom


class MessageView(QWidget):
    def __init__(self, unix_time, sender: str, text: str, file: str = ""):
        super().__init__()
        self.setLayout(QHBoxLayout())

        self.user_image_layout = QVBoxLayout()
        self.content_layout = QVBoxLayout()
        self.header_layout = QHBoxLayout()
        self.message_layout = QVBoxLayout()

        # image_label = QLabel(self)
        # image_label.setPixmap(QPixmap(DEFAULT_PFP_PATH))

        self.user_image = QLabel()
        self.name = QLabel(sender)
        self.time = QLabel(UnixToDateTime(unix_time).strftime("%Y-%m-%d - %H:%M:%S"))
        self.text = QLabel(text)
        # self.text.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # self.text.setWordWrap(True)  # why does this not work correctly

        self.user_image_layout.addWidget(self.user_image)
        # self.user_image_layout.setContentsMargins(QMargins(0, 0, 0, 0))
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
        # self.message_layout.setSpacing(4)
        # self.message_layout.setContentsMargins(QMargins(0, 0, 0, 0))
        # self.message_layout.addStretch(0)

        # self.layout().addWidget(self.name)
        # self.layout().addWidget(self.time)
        # self.layout().addWidget(self.text)
        self.layout().addStretch(0)

        self.layout().setContentsMargins(QMargins(0, 0, 0, 0))
        self.layout().setSpacing(6)
        self.setContentsMargins(QMargins(0, 0, 0, 0))

        # self.setStyleSheet("border: 2px solid; border-color: #660000;")
        
        
# TODO: when the scrollbar reaches the top, request more messages
#  maybe some event section on the socket api to request
#  maybe get the amount of event sections, and we set page numbers we are viewing
#  could view all pages probably
# also have this somehow remember where we were on each channel for scrolling
#  also have this
# TODO: maybe use QTableView, though i don't think i can just use normal widgets for that
#  like i can't add a video player in QTableView probably
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
        self.setContentsMargins(QMargins(0, 0, 0, 0))
        self.message_contents_widget.setContentsMargins(QMargins(0, 0, 0, 0))
        
        self.current_channel = ""
        self.messages = {}
        self.messages_list = []

        self.verticalScrollBar().valueChanged.connect(self.ScrollUpdate)

        self.sig_add_message.connect(self.AddMessage)
        
        # self.message_contents_layout.setContentsMargins(QMargins(0, 0, 0, 0))
        # self.message_contents_layout.setSpacing(0)
        # self.message_contents_widget.setStyleSheet("border: 2px solid; border-color: #660000;")

    def GetLayout(self):
        return self.widget().layout()
    
    def GetMainWindow(self):
        return self.parent().parent().parent()  # ew
        
    def SetChannel(self, channel_name: str) -> None:
        self.current_channel = channel_name
        self.messages.clear()
        RemoveWidgets(self.GetLayout())
        main_window.chat_box.Enable()
        
    def Clear(self):
        self.messages.clear()
        RemoveWidgets(self.GetLayout())
        main_window.chat_box.Disable()

    # TODO: use QListModel or something and prepend and append messages to it
    #  get the min and max indexes from the dictionary and use a while loop to get the messages sorted
    #  for removing messages, just remove it from QListModel, easy (hopefully)
    #  also need to make adding messages more efficient, the current way is way too slow
    # total message count
    def MessageUpdate(self, channel: dict) -> None:
        if not channel["messages"]:
            return
        start_time = perf_counter()
        dict_index = 0
        index = min(channel["messages"])
        while index <= max(channel["messages"]):
            message = channel["messages"][index]
            # msg_start_time = perf_counter()
            # self.AddMessage(index, message)
            self.sig_add_message.emit(index, message)
            # print("made message view in " + str(perf_counter() - msg_start_time) + " seconds")
            index += 1
            dict_index += 1
        TimePrint("adding messages time: " + str(perf_counter() - start_time))
    
    def AddMessage(self, index: int, message: tuple) -> None:
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
        message_qt = MessageView(*message)
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
    
    # TODO: this isn't really working the way i want it to right now
    #  need to be able to prepend messages (that QModel thing?)
    #  also need to check if we already have the messages, just grabs the message again for some reason
    def ScrollUpdate(self, value: int) -> None:
        server = main_window.server_list.GetSelectedServerCache()
        if not self.messages or len(self.messages) == server.message_channels[self.current_channel]["message_count"]:
            return
        
        # top/left end
        if value == self.verticalScrollBar().minimum():
            # request older messages
            if min(self.messages) > 0:
                server.RequestChannelMessageRange(self.current_channel, min(self.messages))

        # bottom/right end
        elif value == self.verticalScrollBar().maximum():
            # request newer messages
            if max(self.messages) < server.message_channels[self.current_channel]["message_count"] - 1:
                server.RequestChannelMessageRange(self.current_channel, max(self.messages), "forward")


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

    @pyqtSlot()
    def ServerSelected(self) -> None:
        server_cache = self.GetSelectedServerCache()
        main_window.channel_list.SetChannels(server_cache.message_channels)

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
        self.channel_name_list = []

    def SetChannels(self, room_id_list: list) -> None:
        self.clear()
        self.channel_name_list = room_id_list
        for room in room_id_list:
            self.addItem(QListWidgetItem(room))

    @pyqtSlot()
    def ChannelSelected(self, *ass) -> None:
        channel_name = self.GetSelectedChannelName()
        main_window.chat_view.SetChannel(channel_name)
        server_cache = main_window.server_list.GetSelectedServerCache()
        server_cache.RequestChannelMessageRange(
            channel_name, server_cache.message_channels[channel_name]["message_count"])
        # self.sig_enter_room.emit(room_name)
        
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


class MainWindow(QWidget):
    sig_callback = pyqtSignal(str, dict)
    sig_connection_callback = pyqtSignal(str, bool)

    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.setWindowTitle("Demez Chat")
        self.client = Client()
        self.client.start()
        self.bookmarks_manager = BookmarkManager(self)
        self.menu_bar = MenuBar(self)

        self.server_list = ServerList()
        self.chat_view = ChatView(self)
        self.channel_list = ChannelList()
        
        server_address_dict = {}
        for server in self.client.server_list:
            server_address_dict[server.address] = server.name
        
        self.server_list.SetServers(server_address_dict)

        channel_chat_layout = QHBoxLayout()
        channel_layout_widget = QWidget()
        channel_layout_widget.setLayout(channel_chat_layout)

        self.chat_box = ChatBox(self)
        self.chat_box.show()

        chat_layout = QVBoxLayout()
        chat_layout.addWidget(self.chat_view)
        chat_layout.addWidget(self.chat_box)
        chat_layout.setContentsMargins(QMargins(0, 0, 0, 0))

        chat_layout_widget = QWidget()
        chat_layout_widget.setLayout(chat_layout)

        self.layout().addWidget(self.menu_bar)
        self.layout().addWidget(channel_layout_widget)

        channel_chat_layout.addWidget(self.server_list)
        channel_chat_layout.addWidget(self.channel_list)
        channel_chat_layout.addWidget(chat_layout_widget)

        self.setMinimumSize(QSize(100, 100))
        self.resize(800, 600)
        self.layout().setContentsMargins(QMargins(0, 0, 0, 0))

        # self.sig_view_channel.connect(self.chat_view.MessageUpdate)
        self.sig_callback.connect(self.HandleSignal)
        self.sig_connection_callback.connect(self.RunServerConnectionChangeCallback)

        self.callbacks = {}

        self.AddCallback("receive_channel_messages", self.chat_view.MessageUpdate)
        self.AddCallback("receive_message", self.ReceiveMessage)
        
        self.client.SetServerConnectionChangeCallback(self.EmitServerConnectionChangeCallback)

        self.show()

    def AddCallback(self, command: str, function: classmethod) -> None:
        self.callbacks[command] = function
        self.client.AddCallback(command, self.RunCallback)
        
    def RunCallback(self, command: str, *fuck) -> None:
        self.sig_callback.emit(command, *fuck)

    def HandleSignal(self, command: str, *args) -> None:
        if command in self.callbacks:
            self.callbacks[command](*args)
        
    def EmitServerConnectionChangeCallback(self, address: str, connected: bool) -> None:
        self.sig_connection_callback.emit(address, connected)
        
    def RunServerConnectionChangeCallback(self, address: str, connected: bool) -> None:
        if connected:
            self.server_list.GetServerButton(address).Enable()
        else:
            current_server = self.server_list.GetSelectedServerAddress()
            server_button = self.server_list.GetServerButton(address)
            server_button.setSelected(False)
            server_button.Disable()
            if current_server == address:
                self.channel_list.clear()
                self.chat_view.Clear()

    def ReceiveMessage(self, message) -> None:
        server_cache = self.server_list.GetSelectedServerCache()
        channel = server_cache.message_channels[message["channel"]]
        message_tuple = (message["time"], message["name"], message["text"], message["file"])
        self.chat_view.AddMessage(channel["message_count"], message_tuple)
        channel["message_count"] += 1
        print("uhhh")
        
    
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


if __name__ == "__main__":
    APP = QApplication(sys.argv)
    APP.setDesktopSettingsAware(True)
    main_window = MainWindow()
    try:
        sys.exit(APP.exec_())
    except Exception as F:
        print(F)
        quit()
