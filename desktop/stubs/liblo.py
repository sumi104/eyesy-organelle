"""Stand-in for pyliblo, so the engine imports on a Mac.

eyesy.py imports oled, oled imports osc, and osc imports liblo, which is a C
library the instrument has and a laptop does not. Nothing here has to carry a
message: the simulator drives the engine in process, and oled.py is a no-op
unless EYESY_PLATFORM is organelle_s.

Only on sys.path for the simulator. The instrument still gets the real liblo.
"""


class AddressError(Exception):
    pass


class ServerError(Exception):
    pass


class Address:
    def __init__(self, *args, **kwargs):
        pass


class Server:
    def __init__(self, *args, **kwargs):
        pass

    def add_method(self, *args, **kwargs):
        pass

    def recv(self, timeout=0):
        return False

    def free(self):
        pass


def send(target, path, *args):
    pass
