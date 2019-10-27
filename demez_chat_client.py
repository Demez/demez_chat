import socket
import select
import sys
import os
import pickle
# TODO: maybe try `from requests import Session`

from threading import Thread
from demez_chat_shared import Message, GetTimeUnix, UnixToDateTime, TimePrint, ClientServerEnums
from client_user_config import UserConfig
from client_bookmark_manager import BookmarkManager

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *


CHAT_BG_COLOR = "#333333"
FONT_COLOR = "#CCCCCC"

BUTTON_COLOR_HOVER = "#595959"
BUTTON_COLOR_PRESSED = "#333333"
BUTTON_COLOR = "#444444"

BUTTON_CSS = f"""
QPushButton         {{ background-color: {BUTTON_COLOR}; }}
QPushButton:hover   {{ background-color: {BUTTON_COLOR_HOVER} }}
QPushButton:pressed {{ background-color: {BUTTON_COLOR_PRESSED} }}
"""


class ChatBox(QWidget):
    sig = pyqtSignal(Message)

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

        # connect the signal
        self.sig.connect(self.parent().AddMessage)

        self.hide()

    @pyqtSlot()
    def SendMessage(self):
        if self.text_input.text():
            message_obj = Message(self.parent().user_config.user.name, GetTimeUnix(), self.text_input.text())
            self.text_input.setText("")
            # self.sig.emit(message_obj)
            SendMessage(message_obj, self.parent().server)
            # TODO: have ChatView scroll down to bottom


def SendMessage(message_obj: Message, server):
    message_pickle = pickle.dumps(message_obj)
    server.send(message_pickle)


class MessageView(QWidget):
    def __init__(self, message: Message):
        super().__init__()
        self.setLayout(QHBoxLayout())

        self.time_name = QLabel("[{0} - {1}]".format(UnixToDateTime(message.time).strftime("%H:%M:%S"), message.name))
        self.text = QLabel("{}".format(message.text))
        # self.text.setWordWrap(True)

        bold_font = QFont()
        bold_font.setBold(True)
        self.time_name.setFont(bold_font)

        self.layout().addWidget(self.time_name)
        self.layout().addWidget(self.text)
        self.layout().addStretch(1)

        self.layout().setContentsMargins(QMargins(0, 0, 0, 0))
        # self.layout().setSpacing(0)
        self.setContentsMargins(QMargins(0, 0, 0, 0))

        # self.setStyleSheet("border: 2px solid; border-color: #006600;")


class ChatView(QScrollArea):
    def __init__(self, parent):
        super().__init__(parent)
        self.message_contents_widget = QWidget()
        self.message_contents_layout = QVBoxLayout()
        self.message_contents_layout.addStretch(0)
        self.message_contents_widget.setLayout(self.message_contents_layout)
        self.setWidget(self.message_contents_widget)

        self.setWidgetResizable(True)
        self.setContentsMargins(QMargins(0, 0, 0, 0))
        # self.message_contents_layout.setContentsMargins(QMargins(0, 0, 0, 0))
        # self.message_contents_layout.setSpacing(0)
        self.message_contents_widget.setContentsMargins(QMargins(0, 0, 0, 0))
        # self.setStyleSheet("border: 0px solid; border-color: #006600;")

    def GetLayout(self):
        return self.widget().layout()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.setWindowTitle("Demez Chat")
        
        self.user_config = UserConfig()
        self.bookmarks_manager = BookmarkManager(self)

        self.menu_bar = QMenuBar()
        # self.menu_bar.setFixedHeight(32)
        self.menu_bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Maximum)
        self.menu_bookmarks = self.menu_bar.addMenu("Bookmarks")
        # manage_bookmarks = self.menu_bookmarks.addAction("Manage Bookmarks")
        # manage_bookmarks.triggered.connect(self.bookmarks_manager.show)
        
        if self.user_config.bookmarks:
            spacer_01 = self.menu_bookmarks.addSeparator()
            server_list = []
            for bookmark in self.user_config.bookmarks:
                bookmark_action = self.menu_bookmarks.addAction(bookmark.name)
                bookmark_action.triggered.connect(lambda a: self.ConnectToServerBookmark(bookmark))
            
        # manage_bookmarks

        self.connect_layout = QHBoxLayout()

        self.chat_view = ChatView(self)
        self.chat_view.hide()

        self.chat_box = ChatBox(self)
        self.layout().addWidget(self.menu_bar)
        self.layout().addWidget(self.chat_view)
        self.layout().addWidget(self.chat_box)

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.network_thread = None  # MessageReceiverThread(self.server, self, name)
        # self.network_thread.start()

        self.setMinimumSize(QSize(100, 100))
        self.resize(640, 480)

        self.show()
        
    def Fuck(self, action):
        print("fuck")

    def AddMessage(self, message_obj):
        # self.chat_view.GetLayout().addWidget(QLabel(message_obj.WriteMessageToConsole()))
        self.chat_view.GetLayout().addWidget(MessageView(message_obj))

    @pyqtSlot()
    def ConnectToServerBookmark(self, bookmark):
        try:
            self.server.connect((bookmark.ip, bookmark.port))
            self.network_thread = NetworkThread(self.server, self, self.user_config.user.name)
            self.network_thread.start()
    
            self.chat_view.show()
            self.chat_box.show()
        except Exception as F:
            print(str(F))


# select doesn't work on windows, so here is a bad attempt at a cross platform version
# https://stackoverflow.com/questions/35889267/an-operation-was-attempted-on-something-that-is-not-a-socket-tried-fixing-a-lot
# https://docs.python.org/3/library/select.html#select.select
# https://repolinux.wordpress.com/2012/10/09/non-blocking-read-from-stdin-in-python/
class CrossPlatformSockets(Thread):
    def __init__(self, sockets_list):
        # read_sockets, write_socket, error_socket = select.select(sockets_list, [], [])
        self.read_sockets = []
        self.write_socket = []
        self.error_socket = []
        self.sockets_list = sockets_list
        pass

        if sys.platform == "win32":
            print("todo: windows")
            for thing in sockets_list:
                if type(thing) == socket:
                    self.read_sockets.append(thing)

        # elif sys.platform.startswith("linux"):
        else:
            self.read_sockets, self.write_socket, self.error_socket = select.select(sockets_list, [], [])
    
    def run(self):
        while True:
            pass


class NetworkThread(QThread):
    signal_message = pyqtSignal(Message)
    # signal_voice = pyqtSignal()
    # signal_screenshare = pyqtSignal()
    # signal_camera = pyqtSignal()

    def __init__(self, server, main_window, name):
        super().__init__()
        self.server = server
        self.main_window = main_window
        self.name = name

        # connect the signal
        self.signal_message.connect(main_window.AddMessage)

    def SetServer(self, new_server):
        self.server = new_server

    def __del__(self):
        self.wait()
        
    def SelectCrossPlatform(self, sockets_list):
        if sys.platform == "win32":
            #  https://stackoverflow.com/questions/35889267/an-operation-was-attempted-on-something-that-is-not-a-socket-tried-fixing-a-lot
            #  https://docs.python.org/3/library/select.html#select.select
            print("todo: windows")
            
        # elif sys.platform.startswith("linux"):
        else:
            read_sockets, write_socket, error_socket = select.select(sockets_list, [], [])
            return read_sockets, write_socket, error_socket

    def run(self):
        while True:
            # maintains a list of possible input streams
            sockets_list = [sys.stdin, self.server]

            """ There are two possible input situations. Either the 
            user wants to give  manual input to send to other people, 
            or the server is sending a message  to be printed on the 
            screen. Select returns from sockets_list, the stream that 
            is reader for input. So for example, if the server wants 
            to send a message, then the if condition will hold true 
            below.If the user wants to send a message, the else 
            condition will evaluate as true"""
            '''
            try:
                # TODO: this doesn't work on windows, need to have something else here
                #  https://stackoverflow.com/questions/35889267/an-operation-was-attempted-on-something-that-is-not-a-socket-tried-fixing-a-lot
                #  https://docs.python.org/3/library/select.html#select.select
                #  i'll have to make a function or class to do this shit crossplatform, ugh
                read_sockets, write_socket, error_socket = self.SelectCrossPlatform(sockets_list)
            except OSError:
                print("Windows is unsupported at the moment, because of some dumb socket thing")
                return
            except Exception as F:
                print(str(F))
                return
            '''
            
            # socket_thread = CrossPlatformSockets(sockets_list)

            read_sockets, write_socket, error_socket = self.SelectCrossPlatform(sockets_list)

            emit_message = False
            for socks in read_sockets:
                if socks == self.server:
                    message = socks.recv(2048)
                    message_obj = pickle.loads(message)
                    if type(message_obj) == Message:
                        print(message_obj.WriteMessageToConsole())
                        emit_message = True
                    elif type(message_obj) == ClientServerEnums.FINISHED_SENDING_HISTORY:
                        TimePrint("Finished Receiving Message History")
                        pass

                    self.server.send(pickle.dumps(ClientServerEnums.RECEIVED_MESSAGE))

                    # received_object = ClientServerCommunication(type(message_obj))
                    # self.server.send(received_object)
                else:
                    message_obj = Message()
                    message_obj.name = self.name
                    message_obj.time = GetTimeUnix()
                    message_obj.text = sys.stdin.readline()
                    message_pickle = pickle.dumps(message_obj)
                    self.server.send(message_pickle)
                    print(message_obj.WriteMessageToConsole())
                    emit_message = True

                if emit_message:
                    self.signal_message.emit(message_obj)

    @pyqtSlot()
    def EmitSignal(self):
        # self
        print("uhhhhhhh")


def Main():
    app = QApplication(sys.argv)
    main_window = MainWindow()
    sys.exit(app.exec_())


if __name__ == "__main__":
    Main()
