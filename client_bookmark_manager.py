from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *


class BookmarkManager(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setLayout(QVBoxLayout())

        self.ip_address_box = QLineEdit()
        self.port = QLineEdit()
        self.server_name = QLineEdit()

        self.bookmark_list_info_layout = QHBoxLayout()

        self.server_info_layout = QVBoxLayout()
        self.server_info_layout.setContentsMargins(QMargins(0, 0, 0, 0))
        self.server_info_layout.addWidget(QLabel("IP:"))
        self.server_info_layout.addWidget(self.ip_address_box)
        self.server_info_layout.addWidget(QLabel("Port:"))
        self.server_info_layout.addWidget(self.port)
        self.server_info_layout.addWidget(QLabel("Server Name:"))
        self.server_info_layout.addWidget(self.server_name)

        bookmark_list_info_widget = QWidget()
        bookmark_list_info_widget.setLayout(self.bookmark_list_info_layout)

        button_container_widget = QWidget()
        button_container_layout = QHBoxLayout()
        button_container_widget.setLayout(button_container_layout)

        self.save_bookmark = QPushButton("Save")
        # self.save_bookmark.pressed.connect(self.ConnectToServer)

        self.server_list = QListWidget()
        self.server_list.setWindowTitle("Server List")
        self.server_list.itemSelectionChanged.connect(self.OnServerSelect)

        for server in parent.user_config.bookmarks:
            server_item = QListWidgetItem(server.name)
            self.server_list.addItem(server_item)
            pass

        self.bookmark_list_info_layout.addWidget(self.server_list)
        self.bookmark_list_info_layout.addLayout(self.server_info_layout)
        self.layout().addWidget(bookmark_list_info_widget)
        self.layout().addWidget(button_container_widget)

    def GetSelectedServer(self):
        server_index = self.server_list.currentRow()
        server = self.parent.user_config.bookmarks[server_index]
        return server

    @pyqtSlot()
    def OnServerSelect(self):
        server = self.GetSelectedServer()
        self.ip_address_box.setText(server.ip)
        self.port.setText(str(server.port))
        self.server_name.setText(server.name)


