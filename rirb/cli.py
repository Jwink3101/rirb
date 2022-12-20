import sys, os
import time
import uuid
from pathlib import Path
import tempfile
import argparse
import shutil
import copy

from . import __version__

_TEMPDIR = False # Just used in testing

class Log:
    def __init__(self):
        pass

    def _init(self, *, tmpdir, debugmode = False):
        self.tmpdir = tmpdir = Path(tmpdir)
        tmpdir.mkdir(parents=True, exist_ok=True)

        self.set_mode(debugmode)  # call before debug
        debug(f"log started. {tmpdir = }")

    def set_mode(self, debugmode: bool) -> None:
        self.debugmode = debugmode

        self.log_file = self.tmpdir / "log.log"
        if self.debugmode:
            self.debug_file = self.log_file
        else:
            self.debug_file = self.tmpdir / "debug.log"

    def log(self, *args, **kwargs):
        """print() to the log with date"""
        __debug = kwargs.pop("__debug", False)
        t = time.strftime("%Y-%m-%d %H:%M:%S:", time.localtime())
        if __debug:
            t = t + "DEBUG:"

        kwargs.pop("file", None)

        if __debug:
            with open(self.debug_file, mode="at") as fobj:
                print(t, *args, file=fobj, **kwargs)
            if self.debugmode:
                print(t, *args, **kwargs)
        else:
            with open(self.log_file, mode="at") as fobj:
                print(t, *args, file=fobj, **kwargs)
            print(t, *args, **kwargs)

    __call__ = log

    def debug(self, *args, **kwargs) -> None:
        return self.log(*args, __debug=True, **kwargs)


log = Log()  # Still needs to be _init. Done in the config
debug = log.debug


class ConfigError(ValueError):
    pass


class Config:
    def __init__(self, configpath, debugmode= False):
        self._config = {"_configpath": configpath}
        self.configpath = Path(configpath).resolve()  # make it absolute

        if _TEMPDIR:  # Testing
            self.tmpdir = Path(_TEMPDIR)
        else:
            self.tmpdir = Path(tempfile.TemporaryDirectory().name)
        self.tmpdir.mkdir(parents=True, exist_ok=True)

        # Start the logging
        log._init(tmpdir=self.tmpdir, debugmode=debugmode)

        log(r"┌────────────────────────────┐")  # Monodraw
        log(r"│    ____  ___ ____  ____    │")
        log(r"│   |  _ \|_ _|  _ \| __ )   │")
        log(r"│   | |_) || || |_) |  _ \   │")
        log(r"│   |  _ < | ||  _ <| |_) |  │")
        log(r"│   |_| \_\___|_| \_\____/   │")
        log(r"│                            │")
        log(r"└────────────────────────────┘")
        log(f"rirb ({__version__})")
        log(f"config path: '{self.configpath}'")
        log(f"tmpdir: {str(self.tmpdir)}")

        templatepath = os.path.join(os.path.dirname(__file__), "config_example.py")

        try:
            with open(templatepath, "rt") as file:
                self._template = file.read()
        except:
            # This is a hack for when it is in an egg file. I need to figure
            # out a better way
            from zipfile import ZipFile

            # Allow for more than one .egg as long as THIS repo doesn't have the name
            eggs = __file__.split(".egg")
            eggpath = ".egg".join(eggs[:-1]) + ".egg"
            templatepath = os.path.join(os.path.dirname(eggs[-1]), "config_example.py")
            if templatepath.startswith("/"):
                templatepath = templatepath[1:]

            with ZipFile(eggpath) as zf:
                self._template = zf.read(templatepath).decode()

    def _write_template(self):
        txt = self._template
        txt = txt.replace("__VERSION__", __version__)
        txt = txt.replace("__UUID4__", str(uuid.uuid4()))

        if self.configpath.exists():
            raise ValueError(
                f"Path '{self.configpath}' exists. "
                "Specify a different path or move the existing file"
            )
        self.configpath.parent.mkdir(parents=True, exist_ok=True)
        self.configpath.write_text(txt)

        debug(f"Wrote template config to {self.configpath}")

    def parse(self, override_txt=""):
        if self.configpath is None:
            raise ValueError("Must have a config path")

        # Passed there
        self._config["os"] = os
        self._config["Path"] = Path
        self._config["log"] = self._config["print"] = log
        self._config["debug"] = debug
        self._config["print"] = log
        self._config["__file__"] = os.path.abspath(self.configpath)
        self._config["__dir__"] = os.path.dirname(self._config["__file__"])
        self._config["__CPU_COUNT__"] = os.cpu_count()

        self._hidden_keys = set(self._config)  # to be removed in repr

        junk = {}
        exec("", junk)

        exec(self._template, self._config)  # Defaults
        self._config_keys = [
            k
            for k in self._config
            if (k not in junk and k not in self._hidden_keys and not k.startswith("_"))
        ]
        self._config_keys.append("destpaths")

        debug(f"""chdir from '{os.getcwd()}' to '{self._config["__dir__"]}'""")

        # Read then change dir
        config_txt = self.configpath.read_text()
        os.chdir(self._config["__dir__"])
        # Set the override_txt before AND after so that you can set other things
        exec(override_txt + "\n" + config_txt + "\n" + override_txt, self._config)

        for key in junk:
            self._config.pop(key, 0)

        self._validate()

        debug(f"Read config {self.configpath}")
        for k in self._config_keys:
            if k not in self._config:
                continue
            dispval = self._config[k]
            if k == "rclone_env":
                dispval = {
                    n: (k if n != "RCLONE_CONFIG_PASS" else "**REDACTED**")
                    for n, k in dispval.items()
                }
            debug(f"   {k} = {dispval}")

    def _validate(self):
        """
        Validate config
        """
        from .rclone import FILTER_FLAGS

        if self.src == "<<MUST SPECIFY>>":
            raise ConfigError("Must specify 'src'")
        if self.dst == "<<MUST SPECIFY>>":
            raise ConfigError("Must specify 'dst'")

        allowed = {
            "compare": {"mtime", "size", "hash"},
            "dst_compare": {"mtime", "size", "hash", None},
            "renames": {"size", "mtime", "hash", False, None},
            "reuse_hashes": {"size", "mtime", False, None},
            #             "hash_fail_fallback": {"size", "mtime", False, None},
            "cleanup_empty_dirs": {True, False, "auto"},
        }

        for key, values in allowed.items():
            val = self._config[key]
            if val not in values:
                raise ConfigError(
                    f"Allowed values for '{key}' are {values}. Specified '{val}'"
                )

        badflags = FILTER_FLAGS.intersection(self.rclone_flags)
        if badflags:
            raise ConfigError(
                f"May not have {badflags} in 'rclone_flags'. Use 'filter_flags'"
            )

    def __getattr__(self, attr):
        return self._config[attr]

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return super(Config, self).__setattr__(attr, value)

        self._config[attr] = value

    def __repr__(self):
        # Need to watch out for RCLONE_CONFIG_PASS in rclone_env
        # make a copy of the dict fixing that one but do not
        # just do a deepcopy in case the user imported modules
        cfg = copy.copy(self._config)
        cfg["rclone_env"] = cfg["rclone_env"].copy()

        if "RCLONE_CONFIG_PASS" in cfg["rclone_env"]:
            cfg["rclone_env"]["RCLONE_CONFIG_PASS"] = "**REDACTED**"

        contents = ", ".join(
            f"{k}={repr(cfg[k])}" for k in self._config_keys if k in self._config
        )
        return f"Config({contents})"


def cli(argv=None):
    from .main import RIRB

    parser = argparse.ArgumentParser(
        description="Reverse Incremental Rclone Backup (rirb)",
        # epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "configpath", help="Specify config file. Will be the destination if --new"
    )

    parser.add_argument("--debug", action="store_true", help="debug mode")
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Display the inteded actions but do not do anything. See also --interactive",
    )
    parser.add_argument(
        "--dst-list",
        action="store_true",
        help=(
            "The destination remote is listed and used for comparison (closer to a "
            "traditional `rclone sync` call). This is slower since it has to be listed "
            "but does clean up extraneous files, etc. Note that the `dst_compare` "
            "config is used for comparison. This may be set automatically if a previoys "
            "run failed."
        ),
    )

    parser.add_argument(
        "--init",
        action="store_true",
        help=(
            "Tells %(prog)s that it shouldn't look for a previous file list "
            "(or backup). Only use on the first backup, otherwise you will "
            "reupload everything again. Also sets --dst-list"
        ),
    )  # This is not needed but it makes it so that we don't re-hash things with not a need.

    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Similar to --dry-run except it will prompt if you want the backup to proceed",
    )
    parser.add_argument(
        "--new", action="store_true", help="Create a new config. Must not exist"
    )
    parser.add_argument(
        "--override",
        action="append",
        default=list(),
        metavar="'OPTION = VALUE'",
        help=(
            "Override any config option for this call only. Must be specified as "
            "'OPTION = VALUE', where VALUE should be proper Python (e.g. quoted strings). "
            """Example: --override "compare = 'mtime'". """
            "Override text is evaluated before *and* after the config file. "
            "Can specify multiple times. There is no input validation of any sort."
        ),
    )

    parser.add_argument(
        "--version", action="version", version="%(prog)s-" + __version__
    )

    if argv is None:
        argv = sys.argv[1:]

    cliconfig = parser.parse_args(argv)
    if cliconfig.init:
        cliconfig.dst_list = True

    config = Config(cliconfig.configpath, debugmode=cliconfig.debug)
    config.cliconfig = cliconfig

    try:
        if cliconfig.new:
            config._write_template()
            log(f"Config file written to '{cliconfig.configpath}'")
            return

        # NOTE: Now located in config directory
        config.parse(override_txt="\n".join(cliconfig.override))
        debug(f"{cliconfig = }")

        rirb = RIRB(config)

        # Delete the tempdir. This is ONLY done if run successfully!
        if not _TEMPDIR:  #  Do not do it while testing
            shutil.rmtree(log.tmpdir)

        return rirb

    except Exception as E:
        log("ERROR: " + str(E), file=sys.stderr)
        log(
            f"ERROR Occured. See logs (including debug) at {config.tmpdir}",
            file=sys.stderr,
        )

        if cliconfig.debug:
            raise

        sys.exit(1)
