import os
import logging

from api2.dir_tools import CreateDirectory
from api2.shared import TimePrintColor, Color

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer


FTP_LOG_DIR = "server_logs/ftp_log.log"
FTP_DIR = "./ftp_server/"
# R/W permissions?
# PERM_RW = "elradfmwMT"

CreateDirectory(os.path.split(FTP_LOG_DIR)[0])
# CreateDirectory(os.path.split(PROFILE_PIC_DIR)[0])
CreateDirectory(os.path.split(FTP_DIR)[0])


class FTPServerAPI:
    def __init__(self, server, max_clients: int, ip: str, port: int, banner: str = ""):
        self.server = server
        self.auth = DummyAuthorizer()
        self.AddAnonymous()
        
        # Instantiate FTP handler class
        self.handler = FTPHandler
        self.handler.authorizer = self.auth

        logging.basicConfig(filename=FTP_LOG_DIR, level=logging.INFO)

        # Instantiate FTP server class and set listener address and port
        address = (ip, port)
        self.ftp_server = FTPServer(address, self.handler)

        # set a limit for connections
        self.ftp_server.max_cons = max_clients
        self.ftp_server.max_cons_per_ip = 5
    
    def StartServer(self):
        TimePrintColor(Color.CYAN, "FTP: Starting FTP Server")
        self.ftp_server.serve_forever()
    
    # Full Read/Write Perms
    def AddUser(self, user_id: str, private_id: str):
        TimePrintColor(Color.CYAN, "FTP: Adding New User: " + user_id)
        self.auth.add_user(user_id, private_id, FTP_DIR, "elradfmwMT")
        
    # Read Only
    def AddAnonymous(self):
        self.auth.add_anonymous(FTP_DIR)


