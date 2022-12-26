import os, sys
import shutil
import time, datetime
from collections import defaultdict
import subprocess
from pathlib import Path

from . import log, debug
from .rclone import Rclone
from . import utils
from .utils import ReturnThread


class RIRB:
    def __init__(self, config):
        self.config = config
        # We want to be able to initialize it before running in case it fails

    def run(self):
        self.t0 = time.time()

        # Use very precise time. Adds some digits but doesn't matter in rclone's crypt
        # because of padding and is better to be exact
        self.now = (
            datetime.datetime.now(datetime.timezone.utc)
            .astimezone()  # Local
            .strftime("%Y-%m-%dT%H%M%S.%f%z")
        )

        config = self.config
        self.config.now = self.now  # Set it there to be used elsewhere
        self.logname = f"{self.now}.log"
        log(f"logname: {self.logname}")

        self.rclone = Rclone(config)

        if self.rclone.init_check_interupt():
            if config.automatic_dst_list or config.cliconfig.dst_list:
                log(
                    "Previous run did not complete. Moving to --dst-list mode (if not already set)"
                )
                config.cliconfig.dst_list = True
            else:
                log("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                log("!!!! Previous run did not complete.        !!!!")
                log("!!!! This one may fail without --dst-list! !!!!")
                log("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

        self.run_shell(mode="pre")

        self.loc_prev = self.rclone.pull_prev_list()

        # Do this in its own thread so it can run at the same time as --dst-list.
        # Joined after listing dst
        cthread = ReturnThread(
            target=self.rclone.list_source, kwargs=dict(prev=self.loc_prev),
        ).start()

        if config.cliconfig.dst_list:
            log("Using --dst-list")
            # Do this in its own thread while the above is also running
            pthread = ReturnThread(target=self.rclone.list_dest).start()
            self.prev = self.dst_prev = pthread.join()
        else:
            self.prev = self.loc_prev
            self.dst_prev = None

        self.curr = cthread.join()

        self.compare()  # sets self.new, self.modified, self.deleted
        self.renames()  # sets self.renamed and updates self.new and self.deleted

        self.diffs = {}  # Just combined to be cleaner
        for name in ["new", "modified", "deleted", "renamed"]:
            val = getattr(self, name)
            self.diffs[name] = val
            debug(f"{name}: {val}")

        if self.config.cliconfig.dry_run or self.config.cliconfig.interactive:
            log("Planned Actions")
            for name in ["new", "modified", "deleted"]:
                flist = getattr(self, name)
                for file in sorted(flist, key=str.lower):
                    log(f"  {name}: {repr(file)}")
            key = lambda a: (a[0].lower(), a[1].lower())
            for s, d in sorted(self.renamed, key=key):
                log(f"  rename: {repr(s)} --> {repr(d)}")

            if self.config.cliconfig.dry_run:
                return self.run_shell(mode="post")
            cont = input("Would you like to continue? Y/[N]: ")
            if not cont.lower().startswith("y"):
                return self.run_shell(mode="post")

        log("Actions:")
        for line in self.summary(actions=True):
            log(f"  {line}")

        # Upload the backed_up_files.json.gz and diffs.json.gz
        self.backup_list = self.build_backup_file_lists()
        self.rclone.upload_diffs_backups(
            self.diffs, self.backup_list, prefix=config.prefix_incomplete_backups
        )

        # Main backup
        self.rclone.transfer(
            curr=self.curr, new=self.new, modified=self.modified, prev=self.prev
        )

        # Moves and deletes
        self.rclone.rename(self.renamed)
        self.rclone.delete(self.deleted)

        # These "finalize" the upload
        self.rclone.upload_curr(self.curr)
        if config.prefix_incomplete_backups:
            self.rclone.remove_prefix_diffs_backups(backup=bool(self.backup_list))

        self.rclone.rmdirs(curr=self.curr, prev=self.prev)

        log("Summary:")
        self.summary_text = self.summary()
        for line in self.summary_text:
            log(f"  {line}")

        self.run_shell(mode="post", stats="\n".join(self.summary_text))

        self.rclone.end_check_interupt()

        self.savelog()

    def savelog(self, fail=False):
        if fail:
            failtxt = "FAILED_"
            logname = str(Path(self.logname).with_suffix(".FAILED.log"))
        else:
            failtxt = ""
            logname = self.logname
        logdests = [utils.pathjoin(self.rclone.destpath.logs, f"{failtxt}log.log")]
        if self.config.log_dest:
            if isinstance(self.config.log_dest, str):
                self.config.log_dest = [self.config.log_dest]
            joined = (utils.pathjoin(d, logname) for d in self.config.log_dest)
            logdests.extend(joined)

        debug(f"{logdests =}")

        logfile = self.config.tmpdir / self.logname
        log("Saving logs to:")
        for logdest in logdests:
            log(f"  {logdest}")
        log("--- End of log ---")

        shutil.copy2(log.log_file, logfile)
        for logdest in logdests:
            self.rclone.copylog(logfile, logdest)

    def summary(self, actions=False):
        """Summary. If actions is True, does not include total or time"""
        res = [f"Total: {utils.summary_text(self.curr)}"] if not actions else []
        for name in ["new", "modified", "deleted", "renamed"]:
            filelist = getattr(self, name)
            if name == "renamed":
                if not self.config.renames:  # No need for renames if not tracking
                    continue
                filelist = [s[1] for s in filelist]

            # Use if... rather that .get() to avoid eval
            pp = {
                p: (vv if (vv := self.curr.get(p, None)) else self.prev.get(p, {}))
                for p in filelist
            }
            res.append(f"{name.title()}: {utils.summary_text(pp)}")

        if not actions:
            dt = utils.time_format(time.time() - self.t0)
            res.append(f"Elapsed Time: {dt}")
        return res

    def build_backup_file_lists(self):
        backup = {}
        for name in ["modified", "deleted"]:
            for path in getattr(self, name):
                file = {"status": name}
                file.update(self.prev.get(path, {}))
                backup[path] = file
        return backup

    def compare(self):
        config = self.config
        curr = self.curr

        if config.cliconfig.dst_list:
            attrib = config.dst_compare if config.dst_compare else config.compare
        else:
            attrib = self.config.compare

        # Keep new and modified separate so that we can document the hashes of
        # the backups.
        self.new = []
        self.modified = []
        self.deleted = list(set(self.prev) - set(curr))

        for path, file in self.curr.items():
            try:
                pfile = self.prev[path]
            except KeyError:
                self.new.append(path)
                continue

            try:
                if not self.file_compare(file, pfile, attrib):
                    self.modified.append(path)
            except NoCommonHashError:
                debug(f"Failed Compare {path}")
                raise

    def renames(self):
        """Track renames. ONLY uses local file-list"""

        self.renamed = []
        if not self.config.renames:
            log("Rename tracking disabled")
            return

        if self.config.cliconfig.dst_list:
            log("Rename tracking ignored for --dst-list")
            return

        attrib = self.config.renames

        # The algorithm for this is pretty simple. When a file is
        # renamed, it looks like the old file is deleted and the
        # new file is created. So the candidates are pretty simple.
        #
        # Since size must *always* match, we make a dictionary by sizes
        # to reduce the pool

        del_by_size = defaultdict(list)
        for path in self.deleted:
            size = self.loc_prev.get(path, {}).get("Size", -1)
            del_by_size[size].append(path)

        for path in self.new:
            nfile = self.curr[path]
            cpaths = del_by_size[nfile["Size"]]  # list of candidate paths
            cpaths = [
                cpath
                for cpath in cpaths
                if self.file_compare(nfile, self.prev.get(cpath, {}), attrib)
            ]

            if len(cpaths) == 1:
                self.renamed.append((cpaths[0], path))  # old,new
            elif not cpaths:
                continue
            else:
                log(f"Too many matches for {path}. Not moving")

        # Now we need to remove the moves from new and delete
        self.new = list(set(self.new) - set(n for _, n in self.renamed))
        self.deleted = list(set(self.deleted) - set(d for d, _ in self.renamed))

    def file_compare(self, file, pfile, attrib):
        """
        Return whether the file is the same based on attrib.
        
        May be used for compare or move tracking
        """
        if not attrib:
            return False

        # Always check size
        if "Size" not in file or "Size" not in pfile:
            return False

        if not file["Size"] == pfile["Size"]:
            return False

        if (
            attrib == "mtime"
            and abs(
                utils.RFC3339_to_unix(file["ModTime"])
                - utils.RFC3339_to_unix(pfile["ModTime"])
            )
            > self.config.dt
        ):
            return False

        if attrib == "hash":
            shared_hashes = set(file.get("Hashes", {})).intersection(
                pfile.get("Hashes", {})
            )
            if not shared_hashes:
                msg = "Non compatible (or non existent) hashes. Change attributes"
                debug(f"{msg}: {file} <--> {pfile}")
                raise NoCommonHashError(msg)

            for hashname in shared_hashes:
                if file["Hashes"][hashname] != pfile["Hashes"][hashname]:
                    return False

        return True  # At this point, all tests have passed!

    def run_shell(self, *, mode, stats=""):
        """Run the shell commands"""

        dry = self.config.cliconfig.dry_run

        if mode == "pre":
            cmds = self.config.pre_shell
        elif mode == "post":
            cmds = self.config.post_shell

        log("")
        log("Running shell commands")
        if not cmds:
            return

        returncode = shell_runner(cmds, dry=dry, env={"STATS": stats})

        if returncode and self.config.stop_on_shell_error:
            raise subprocess.CalledProcessError(returncode, cmds)


def shell_runner(cmds, dry=False, env=None):
    """
    Run the shell command (string or list) and return the returncode
    """
    prefix = "DRY RUN " if dry else ""
    if isinstance(cmds, str):
        for line in cmds.rstrip().split("\n"):
            log(f"{prefix}$ {line}")
        shell = True
    else:
        log(f"{prefix}{cmds}")
        shell = False

    if dry:
        return log("DRY-RUN: Not running")

    environ = os.environ.copy()
    if env:
        environ.update(env)

    proc = subprocess.Popen(
        cmds, shell=shell, env=environ, stderr=subprocess.PIPE, stdout=subprocess.PIPE
    )

    out, err = proc.communicate()
    out, err = out.decode(), err.decode()
    for line in out.split("\n"):
        log(f"STDOUT: {line}")

    if err.strip():
        for line in err.split("\n"):
            log(f"STDERR: {line}")
    if proc.returncode > 0:
        log(f"WARNING: Command return non-zero returncode: {proc.returncode}")
    return proc.returncode


class NoCommonHashError(ValueError):
    pass
