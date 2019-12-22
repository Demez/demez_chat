import sys

from qt5_bookmark_manager import BookmarkManager
from api2.client import Client
from api2.shared import Command, TimePrint, GetTime24Hour, UnixToDateTime, UnixTo24Hour

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
        self.text_input.returnPressed.connect(self.SendMessage)

        # send_button = QPushButton("send")
        # send_button.pressed.connect(self.SendMessage)

        self.layout().addWidget(self.text_input)
        # self.layout().addWidget(send_button)
        
    def GetMainWindow(self):
        return self.parent().parent().parent()  # ew

    @pyqtSlot()
    def SendMessage(self):
        if self.text_input.text():
            # main_window = self.GetMainWindow()
            main_window.client.SendMessage(main_window.chat_view.current_channel, self.text_input.text())
            self.text_input.setText("")
            # self.sig_send_message.emit(message_obj, main_window.chat_view.current_channel)
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
        # self.text.setWordWrap(True)

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
        
        
class LabelMessageTest(QLabel):
    def __init__(self, unix_time, sender: str, text: str, file: str = ""):
        super().__init__()
        self.setText(f"[{UnixToDateTime(unix_time).strftime('%Y-%m-%d - %H:%M:%S')} - {sender}] {text}")


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
        client = main_window.client
        if not self.messages or len(self.messages) == client.message_channels[self.current_channel]["message_count"]:
            return
        
        # top/left end
        if value == self.verticalScrollBar().minimum():
            # request older messages
            if min(self.messages) > 0:
                client.RequestChannelMessageRange(self.current_channel, min(self.messages))

        # bottom/right end
        elif value == self.verticalScrollBar().maximum():
            # request newer messages
            if max(self.messages) < client.message_channels[self.current_channel]["message_count"] - 1:
                client.RequestChannelMessageRange(self.current_channel, max(self.messages), "forward")


class MenuBar(QMenuBar):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.bookmarks_manager = BookmarkManager(parent)
        # self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Maximum)
        self.menu_bookmarks = self.addMenu("Bookmarks")

        if self.parent().client.user_config.bookmarks:
            # spacer_01 = self.menu_bookmarks.addSeparator()
            server_list = []
            for bookmark in self.parent().client.user_config.bookmarks:
                bookmark_action = self.menu_bookmarks.addAction(bookmark.name, self.bookmark_clicked)

    @pyqtSlot()
    def bookmark_clicked(self):
        # get the bookmark index from the bookmark menu actions
        # and use that index to get the bookmark in the user config
        bookmark = self.parent().client.user_config.bookmarks[self.menu_bookmarks.actions().index(self.sender())]
        self.parent().ConnectToServer(bookmark.ip, bookmark.port)


class RoomList(QListWidget):
    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.setFixedWidth(192)
        self.itemSelectionChanged.connect(self.room_selected)
        self.room_id_list = []

    def set_rooms(self, room_id_list: list) -> None:
        self.clear()
        self.room_id_list = room_id_list
        for room in room_id_list:
            self.addItem(QListWidgetItem(room))

    @pyqtSlot()
    def room_selected(self) -> None:
        room_name = self.get_selected_room_name()
        self.main_window.chat_view.SetChannel(room_name)
        self.main_window.client.RequestChannelMessageRange(
            room_name, self.main_window.client.message_channels[room_name]["message_count"])
        # self.sig_enter_room.emit(room_name)

    # these 2 won't work, we need to have the server return a dict of the channels
    # actually, what if we just request a channel update for each channel?
    # no, just request the channel info when we click on the channel
    def get_selected_room_name(self) -> str:
        return self.item(self.currentRow()).text()
    
    # def get_selected_room_info(self):
    #     return self.room_id_list[self.get_selected_room_name()]

    def get_selected_room(self) -> tuple:
        room_id = self.room_id_list[self.currentRow()]
        room = self.room_id_list[room_id]
        return room_id, room


class MainWindow(QWidget):
    # sig_view_channel = pyqtSignal(str, dict)
    sig_callback = pyqtSignal(str, dict)

    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.setWindowTitle("Demez Chat")
        self.client = Client()
        self.bookmarks_manager = BookmarkManager(self)
        self.menu_bar = MenuBar(self)

        channel_chat_layout = QHBoxLayout()

        self.chat_view = ChatView(self)
        self.channel_list = RoomList(self)

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

        channel_chat_layout.addWidget(self.channel_list)
        channel_chat_layout.addWidget(chat_layout_widget)

        # self.network_thread = None  # MessageReceiverThread(self.server, self, name)
        # self.network_thread.start()

        self.setMinimumSize(QSize(100, 100))
        self.resize(800, 600)
        self.layout().setContentsMargins(QMargins(0, 0, 0, 0))

        # self.sig_view_channel.connect(self.chat_view.MessageUpdate)
        self.sig_callback.connect(self.HandleSignal)

        self.callbacks = {}

        self.AddCallback("receive_channel_messages", self.chat_view.MessageUpdate)
        self.AddCallback("receive_message", self.ReceiveMessage)

        self.show()

    def AddCallback(self, command: str, function: classmethod) -> None:
        self.callbacks[command] = function
        self.client.AddCallback(command, self.RunCallback)
        
    def RunCallback(self, command: str, *fuck) -> None:
        self.sig_callback.emit(command, *fuck)

    def HandleSignal(self, command: str, *args) -> None:
        if command in self.callbacks:
            self.callbacks[command](*args)
        
    def ConnectToServer(self, ip: str, port: int) -> None:
        self.client.Connect(ip, port)
        self.channel_list.set_rooms(self.client.message_channels)

    def ReceiveMessage(self, message) -> None:
        channel = self.client.message_channels[message["channel"]]
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
    main_window = MainWindow()
    try:
        sys.exit(APP.exec_())
    except Exception as F:
        print(F)
        quit()
