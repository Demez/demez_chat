from argparse import ArgumentParser
from api2.server import Server


def ParseArgs():
    cmd_parser = ArgumentParser()
    cmd_parser.add_argument("--name", "-n", default="default", help="Enter the server name")
    cmd_parser.add_argument("--ip", "-i", required=True, help="Enter the server address")
    cmd_parser.add_argument("--port", "-p", required=True, help="Enter the server port")
    cmd_parser.add_argument("--max", "-m", default=100, help="Max number of connections we can have")
    return cmd_parser.parse_args()


def Find(search):
    result = []
    for con_command in server.con_command_dict.keys():
        if search in con_command:
            result.append(con_command)
    if result:
        print(" - " + "\n - ".join(result))
    else:
        print("No results for \"" + search + "\" found")


if __name__ == "__main__":
    ARGS = ParseArgs()
    # CreateDirectory("channels")
    # Thread(target=Server, args=()).start()
    server = Server(
        ARGS.name,
        ARGS.ip,
        ARGS.port,
        ARGS.max)

