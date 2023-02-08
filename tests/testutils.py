"""
Testing Util
"""
import os, sys
import uuid
from pathlib import Path
import shutil
import time
import random
import hashlib
import subprocess, signal
import atexit

PWD0 = os.path.abspath(os.path.dirname(__file__))
os.chdir(PWD0)

p = os.path.abspath("../")
if p not in sys.path:
    sys.path.insert(0, p)

import rirb.cli
import rirb.utils
import rirb.rclone

rirb.rclone._TESTMODE = True


class WebDAV:
    def __init__(self, path, port=45678):
        self.path = path = os.path.abspath(path)
        self.remote = f":webdav,url='http://localhost:{int(port)}':"

        cmd = [
            "rclone",
            "serve",
            "webdav",
            path,
            "-v",
            "--addr",
            f"localhost:{int(port)}",
        ]

        atexit.register(self.close)  # Make sure it gets shut down
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.check(retries=10)

    def check(self, retries=6, dt=0.1):
        checkcmd = [
            "rclone",
            "lsf",
            self.remote,
            "--retries",
            "1",
            "--low-level-retries",
            "1",
        ]

        for c in range(retries):
            stat = subprocess.Popen(
                checkcmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            ).wait()
            if stat == 0:
                return True
            time.sleep(dt)
        else:
            return False

    def close(self):
        # print(f'SHUTDOWN {self.path}')
        self.proc.send_signal(signal.SIGINT)


class Tester:
    def __init__(self, *, name, src=None, dst=None, seed=1):
        os.chdir(PWD0)

        rirb.cli._TEMPDIR = "TEMP"

        self.pwd = Path(os.path.abspath(f"testdirs/{name}"))
        self.make_ignore()

        if src is None:
            src = os.path.join(self.pwd, "src")
        if dst is None:
            dst = os.path.join(self.pwd, "dst")

        self.src = src
        self.dst = dst

        self.config = {
            "src": self.src,
            "dst": self.dst,
            "_uuid": str(uuid.uuid4()),
        }

        try:
            shutil.rmtree(self.pwd)
        except OSError:
            pass

        os.makedirs(self.pwd)

        # Will also append additional rclone???
        shutil.copy2("rclone.cfg", self.pwd / "rclone.cfg")

        os.chdir(self.pwd)

        self.config["rclone_env"] = {"RCLONE_CONFIG": "rclone.cfg"}

        self.logs = []

    def cli(self, *args):
        rirb_obj = rirb.cli.cli(args)
        logfile = rirb_obj.config.tmpdir / "log.log"
        debugfile = rirb_obj.config.tmpdir / "debug.log"

        self.logs.append(
            (
                (logfile.read_text() if logfile.exists() else ""),
                (debugfile.read_text() if debugfile.exists() else ""),
            )
        )

        if logfile.exists():
            shutil.move(logfile, f"{logfile}.{time.time_ns()}")
        if debugfile.exists():
            shutil.move(debugfile, f"{debugfile}.{time.time_ns()}")
        return rirb_obj

    def write_config(self):
        with open(self.pwd / "config.py", "wt") as fobj:
            for key, val in self.config.items():
                print(f"{key} = {repr(val)}", file=fobj)

    def write(self, path, content, mode="wt", dt=0):
        try:
            os.makedirs(os.path.dirname(path))
        except:
            pass

        with open(path, mode) as file:
            file.write(content)

        if dt:
            change_time(path, dt)

    def write_pre(self, path, content, mode="wt", dt=None):
        """Write items randomly in the past"""
        dt = dt if not None else -5 * (1 + random.random())
        if path.startswith("B"):
            raise ValueError("No pre on B")
        self.write(path, content, mode=mode, dt=dt)

    def write_post(self, path, content, mode="wt", add_dt=0):
        """
        Write items randomly in the future. Can add even more if forcing
        newer
        """
        dt = 5 * (1 + random.random()) + add_dt
        self.write(path, content, mode=mode, dt=dt)

    def read(self, path):
        with open(path, "rt") as file:
            return file.read()

    def sha1(self, path):
        hh = hashlib.sha1()
        with open(path, "rb") as file:
            while dat := file.read(1024):
                hh.update(dat)
        return hh.hexdigest()

    def globread(self, globpath):
        paths = glob.glob(globpath)
        if len(paths) == 0:
            raise OSError("No files matched the glob pattern")
        if len(paths) > 1:
            raise OSError(f"Too many files matched the pattern: {paths}")

        return self.read(paths[0])

    def move(self, src, dst):
        try:
            os.makedirs(os.path.dirname(dst))
        except OSError:
            pass

        shutil.move(src, dst)

    def compare_tree(self):
        """All file systems are identical"""
        src = "src"
        dst = "dst/curr"
        result = set()

        files_src = set(os.path.relpath(f, src) for f in tree(src))
        files_dst = set(os.path.relpath(f, dst) for f in tree(dst))

        files = files_src.union(files_dst)
        for file in sorted(list(files), key=str.lower):
            file_src = os.path.join(src, file)
            file_dst = os.path.join(dst, file)
            try:
                srctxt = open(file_src, "rb").read()
            except IOError:
                result.add(("missing_in_src", file))
                continue

            try:
                dsttxt = open(file_dst, "rb").read()
            except IOError:
                result.add(("missing_in_dst", file))
                continue

            if not srctxt == dsttxt:
                result.add(("disagree", file))

        return result

    def backup_dirs(self, dst=None):
        dst = dst if dst else self.dst
        backs = rirb.utils.pathjoin(dst, "back")
        return sorted(rirb.utils.pathjoin(backs, d) for d in os.listdir(backs))

    def log_dirs(self, dst=None):
        dst = dst if dst else self.dst
        backs = rirb.utils.pathjoin(dst, "logs")
        return sorted(rirb.utils.pathjoin(backs, d) for d in os.listdir(backs))

    def make_ignore(self, file=".ignore"):
        ignore = self.pwd.parent / file
        if not ignore.exists():
            self.pwd.parent.mkdir(exist_ok=True, parents=True)
            with ignore.open(mode="a"):
                pass


def change_time(path, time_adj):
    """Change the time on a file path"""
    stat = os.stat(path)
    os.utime(path, (stat.st_atime + time_adj, stat.st_mtime + time_adj))


def tree(path):
    files = []
    for dirpath, dirnames, filenames in os.walk(path, followlinks=True):
        exc = {".DS_Store"}
        files.extend(
            os.path.join(dirpath, filename)
            for filename in filenames
            if filename not in exc
        )

    return files
