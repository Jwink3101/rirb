from threading import Lock

LOCK = Lock()

__version__ = "20230107.0.BETA"

from . import cli

log = cli.log
debug = cli.debug

from . import utils
