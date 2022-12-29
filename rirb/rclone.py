"""
Rclone interfacing. Largely borrowed from syncrclone's 20221024.0.BETA
"""
import os, sys
import shutil
import shlex
import subprocess
from pathlib import Path
import time
import json
import gzip as gz

from . import log, debug
from . import utils

_TESTMODE = False
_TEST_FAIL_LOC = None  # This will be used in testing to make it fail

FILTER_FLAGS = frozenset(
    {
        "--include",
        "--exclude",
        "--include-from",
        "--exclude-from",
        "--filter",
        "--filter-from",
        "--files-from",
        "--one-file-system",
        "--exclude-if-present",
    }
)

NO_TRAVERSE_LIMIT = 50  # Something of a WAG
IGNORED_FILE_DATA = (
    "IsDir",
    "Name",
    "ID",
    "Tier",
)


class NoPreviousFileListError(ValueError):
    pass


class Rclone:
    """
    Main rclone interfacing object
    
    config: config object for this run
    """

    def __init__(self, config):
        self.rclonetime = 0.0

        self.add_args = []
        if config.metadata:
            self.add_args.append("--metadata")

        self.config = config
        self.tmpdir = config.tmpdir

        # Buidld dest paths
        self.destpath = utils.Bunch()
        self.destpath.back = utils.pathjoin(self.config.dst, "back", self.config.now)
        self.destpath.curr = utils.pathjoin(self.config.dst, "curr")
        self.destpath.log_base = utils.pathjoin(self.config.dst, "logs")
        self.destpath.logs = utils.pathjoin(self.config.dst, "logs", self.config.now)
        for path, val in self.destpath.items():
            debug(f"Set path {path} = {val}")
        # self.destpath.backup =
        self.call(["--version"], stream=True)

    def pull_prev_list(self):
        config = self.config

        if config.cliconfig.init:
            log("New setup. No previous list")
            return {}

        prevfile = None
        if locprev := self._local_name():
            debug(f"Looking for local list: {locprev} ...")
            if locprev.exists():
                debug("...found")
                prevfile = locprev
            else:
                debug("...NOT found. Pulling")

        if not prevfile:
            try:
                # First list all dirs
                cmd = [
                    "lsf",
                    self.destpath.log_base,
                    "--dirs-only",
                    "--include",
                    r"{{ \d{4}-\d{2}-\d{2}T\d{6} }}",  # regex. Not sure it's working but the end result works...
                ]
                rprevdirs = self.call(cmd)
                rprevdir = sorted(
                    ds for d in rprevdirs.split("\n") if (ds := d.strip())
                )[-1]
                rprevfile = utils.pathjoin(
                    self.destpath.log_base, rprevdir, "curr.json.gz"
                )

                prevfile = utils.pathjoin(self.tmpdir, "prev.json.gz")

                cmd = ["copyto", rprevfile, prevfile]
                cmd += ["--retries", "1"]
                self.call(cmd, display_error=False, logstderr=False)

            except subprocess.CalledProcessError as err:
                raise NoPreviousFileListError(
                    f"No previous file found at {self.destpath.log_base}. "
                    "Should you run with `--init`"
                )
        with gz.open(prevfile) as fobj:
            return json.load(fobj)

    def _local_name(self):
        config = self.config
        if not config.use_local_cache:
            return

        locname = getattr(self, "locname", None)
        if not locname:
            if not config.use_local_cache:
                return

            cdir = self.local_cache_dir()
            if not cdir:
                return
            self.locname = locname = Path(cdir) / "rirb" / f"{config._uuid}.json.gz"

        return locname

    def local_cache_dir(self):
        if _TESTMODE:  ## Just used in testing
            return Path("cache")

        if cdir := getattr(self, "_local_cache_dir", None):
            return cdir

        for line in self.call(["config", "paths"]).split("\n"):
            if line.startswith("Cache dir:"):
                cdir = line.split(":", 1)[-1].strip()
                debug(f"rclone cache: '{cdir}'")
                break
        else:
            debug("Could not get rclone cache dir!")
            return

        self._local_cache_dir = Path(cdir)
        return self._local_cache_dir

    def list_dest(self):
        """
        List the destination
        """
        config = self.config

        cmd = [
            "lsjson",
            self.destpath.curr,
            "--recursive",
            "--files-only",
            "--no-mimetype",
        ]

        # Unlike list_source(), we always disable mod-times unless that is the
        # attribute.
        compare = config.dst_compare if config.dst_compare else config.compare

        if compare == "size":
            cmd += ["--no-modtime"]
        elif compare == "hash":
            hash_flags = ["--hash"]
            if config.hash_type:
                if isinstance(config.hash_type, str):
                    config.hash_type = [config.hash_type]
                for htype in config.hash_type:
                    hash_flags.extend(["--hash-type", htype])
            cmd += hash_flags
        else:  # compare == 'mtime':
            pass

        # Listing flags only for --dst-list
        cmd.extend(config.dst_list_rclone_flags)

        # Note we do NOT filter or anything like that! It should be the full listing.
        # We allow for an error if and only if this is also an --init run since there
        # may not be a destination to list
        try:
            raw_files = self.call(cmd)
        except subprocess.CalledProcessError:
            if self.config.cliconfig.init:
                log(
                    "rclone remote listing error. Assuming it does not exist since --init is set"
                )
                raw_files = "[]"
            else:
                log(
                    "rclone remote listing error. Does the remote exists? Try with --init"
                )
                raise
        files = json.loads(raw_files)
        dst_prev = self.file_list2dict(files)
        debug(f"Read {len(files)} destination files")
        return dst_prev

    def list_source(self, prev=None):
        """
        List SOURCE, optionally use previous for hashes, add metatada as needed
        """
        config = self.config

        compute_hashes = any(
            [config.get_hashes, config.compare == "hash", config.renames == "hash",]
        )

        skip_modtime = not any(
            [  # Notice this is negated
                config.get_modtime,
                config.compare == "mtime",
                (config.cliconfig.dst_list and config.dst_compare == "mtime"),
                config.renames == "mtime",
                (compute_hashes and config.reuse_hashes == "mtime"),
                #                 config.hash_fail_fallback == "mtime",
            ]
        )

        debug(f"{compute_hashes = }, {skip_modtime = }")

        cmd = ["lsjson", config.src, "--recursive", "--files-only", "--no-mimetype"]

        if skip_modtime:
            cmd.append("--no-modtime")

        hash_flags = ["--hash"]
        if config.hash_type:
            if isinstance(config.hash_type, str):
                config.hash_type = [config.hash_type]
            for htype in config.hash_type:
                hash_flags.extend(["--hash-type", htype])

        if compute_hashes and not config.reuse_hashes:
            cmd.extend(hash_flags)

        # add_args (including --metadata) and rclone_flags will be added by call()

        files = json.loads(self.call(cmd + config.filter_flags))
        curr = self.file_list2dict(files)
        debug(f"Read {len(files)} files")

        if not compute_hashes or (compute_hashes and not config.reuse_hashes):
            return curr

        # Add back the hashes
        if prev is None:
            prev = {}

        update_list = []
        for path, file in curr.items():
            try:
                pfile = prev[path]
            except KeyError:
                update_list.append(path)
                continue

            if "Hashes" not in pfile:
                update_list.append(path)
                continue

            if file["Size"] != pfile["Size"]:
                update_list.append(path)
                continue

            if (
                self.config.reuse_hashes == "mtime"
                and abs(
                    utils.RFC3339_to_unix(file["ModTime"])
                    - utils.RFC3339_to_unix(pfile["ModTime"])
                )
                > config.dt
            ):
                update_list.append(path)
                continue

            # Use the prior hashes
            file["Hashes"] = pfile["Hashes"]

        if not update_list:
            log(f"No need to compute more hashes")
            return curr

        flistpath = config.tmpdir / "relist.txt"
        flistpath.write_text("\n".join(update_list))

        cmd.extend(("--files-from", str(flistpath)))
        cmd.extend(hash_flags)

        log(f"Computing hashes for {len(update_list)} files")
        files = json.loads(self.call(cmd))
        curr.update(self.file_list2dict(files))

        return curr

    def file_list2dict(self, files):
        out = {}
        for file in files:
            path = file.pop("Path")
            for key in IGNORED_FILE_DATA:
                file.pop(key, None)
            out[path] = file
        return out

    def transfer(self, *, curr, new, modified, prev):
        """
        Transfer new and modified files.
        """
        if _TEST_FAIL_LOC == "transfer":  # Just used in testing
            raise ValueError("Failure created for testing!")

        if not (new or modified or prev):
            debug("Nothing to transfer")
            return

        # We will use `--files-from` to tell rclone what we want to transfer and we
        # KNOW we want them all to transfer. However, we do not want to blanket use
        # --ignore-times which will always transfer the files since a retry will then
        # retry it all.
        #
        # The solution is split `modified` into same-size and diff-size lists from
        # what is already there (from `prev`). The `new` and `diff-size` files
        # are transfered with `--size-only` (fast!) and the same-size are transfered
        # with `--ignore-times`.
        same_size = {
            path for path in modified if curr[path]["Size"] == prev[path]["Size"]
        }
        diff_size = set(modified) - same_size

        cmd0 = ["copy", self.config.src, self.destpath.curr]
        cmd0 += ["-v", "--stats-one-line", "--log-format", ""]  # What to show
        cmd0 += ["--backup-dir", self.destpath.back]  # Let rclone do the backups

        log("Transfering Files")

        flag_lists = (
            ("--ignore-times", same_size),  # Always Transfer
            ("--size-only", diff_size.union(new)),  # We KNOW they do not match size
        )
        for ii, (flag, flist) in enumerate(flag_lists):
            debug(f"Transfer {len(flist)} with '{flag}'")
            if not flist:
                continue

            flistpath = self.config.tmpdir / f"transfer_{ii}.txt"
            flistpath.write_text("\n".join(flist))

            cmd = cmd0 + ["--files-from", str(flistpath), flag]
            if len(flist) <= NO_TRAVERSE_LIMIT:
                cmd += ["--no-traverse"]
            self.call(cmd, stream=True)

    def delete(self, files):
        """
        Delete (i.e. move) files
        """
        if not files:
            return
        cmd = ["move", self.destpath.curr, self.destpath.back]
        cmd += ["-v", "--stats-one-line", "--log-format", ""]  # What to show

        # We know in all cases, the dest doesn't exists. So never check dest,
        # always transfer, and do not traverse
        cmd += ["--no-check-dest", "--ignore-times", "--no-traverse"]

        flistpath = self.config.tmpdir / "move.txt"
        flistpath.write_text("\n".join(files))

        cmd += ["--files-from", str(flistpath)]

        log("Deleting Files")
        self.call(cmd, stream=True)

    def rename(self, renames):
        if not renames:
            return
        log(f"Renaming {len(renames)} files")
        for sourcefile, destfile in renames:
            cmd = [
                "moveto",
                utils.pathjoin(self.destpath.curr, sourcefile),
                utils.pathjoin(self.destpath.curr, destfile),
            ]
            cmd += ["-v", "--stats-one-line", "--log-format", ""]  # What to show

            # We know in all cases, the dest doesn't exists. So never check dest,
            # always transfer, and do not traverse
            cmd += ["--no-check-dest", "--ignore-times", "--no-traverse"]

            log(f"Move {repr(sourcefile)} --> {repr(destfile)}")
            self.call(
                cmd, stream=True,
            )

    def rmdirs(self, *, curr_dirs, prev_dirs):
        if not self.config.cleanup_empty_dirs or (
            self.config.cleanup_empty_dirs == "auto" and not self.empty_dir_support()
        ):
            return

        rmdirs0 = prev_dirs - curr_dirs

        # Originally, I sorted by length to get the deepest first but I can
        # actually get the root of them so that I can call rmdirs (with the `s`)
        # and let that go deep

        cmd0 = ["rmdirs"]
        cmd0 += ["-v", "--stats-one-line", "--log-format", ""]  # What to show
        cmd0 += ["--retries", "1"]

        rmdirs = []
        for diritem in sorted(rmdirs0):
            # See if it's parent is already there. This can 100% be improved
            # since the list is sorted. See https://stackoverflow.com/q/7380629/3633154
            # for example. But it's not worth it here
            if any(diritem.startswith(f"{rmdir}/") for rmdir in rmdirs):
                continue  # ^^^ Add the / so it gets child dirs only

            rmdirs.append(diritem)

            try:
                log(f"Removing Directory '{diritem}' (if empty)")
                cmd = cmd0 + [utils.pathjoin(self.destpath.curr, diritem)]
                self.call(cmd, stream=True)
            except subprocess.CalledProcessError:
                # This is likely due to the file not existing. It is acceptable
                # for this error since even if it was something else, not
                # properly removing empty dirs is acceptable
                #
                # Recent tests do not seem to trigger this with rmdirs. Just rmdir.
                # Consider removing
                log(f"Could not delete '{diritem}'. Must not be empty")

    def upload_curr(self, curr):
        """Upload 'curr.json.gz'"""
        # new list of all files
        new_curr_list = self.tmpdir / "newcurr.json.gz"
        with gz.open(new_curr_list, "wt") as fobj:
            json.dump(curr, fobj, indent=1, ensure_ascii=False)
        debug(f'Dumped updated "current" list to {new_curr_list}')

        if locprev := self._local_name():
            Path(locprev).parent.mkdir(exist_ok=True, parents=True)
            shutil.copy2(new_curr_list, locprev)
            debug(f"Copied to local: {locprev}")

        cmd = [
            "copyto",
            str(new_curr_list),
            utils.pathjoin(self.destpath.logs, "curr.json.gz"),
        ]
        self.call(cmd)
        debug("Uploaded 'curr.json.gz'")

    def upload_diffs_backups(self, diffs, backup, prefix=True):
        debug(f"Uploading Diffs {prefix = }")
        p = "INCOMPLETE_BACKUP_" if prefix else ""
        # Diffs file
        diffs_file = self.tmpdir / "diffs.json.gz"
        with gz.open(diffs_file, "wt") as fobj:
            json.dump(diffs, fobj, indent=1, ensure_ascii=False)
        cmd = [
            "copyto",
            str(diffs_file),
            utils.pathjoin(self.destpath.logs, f"{p}diffs.json.gz"),
        ]
        self.call(cmd)

        # backups. May be an empty dict
        if not backup:
            return

        backup_list = self.tmpdir / "backed_up_files.json.gz"
        with gz.open(backup_list, "wt") as fobj:
            json.dump(backup, fobj, indent=1, ensure_ascii=False)
        cmd = [
            "copyto",
            str(backup_list),
            utils.pathjoin(self.destpath.logs, f"{p}backed_up_files.json.gz"),
        ]
        self.call(cmd)

    def remove_prefix_diffs_backups(self, *, backup):
        """Remove the 'INCOMPLETE_BACKUP_' prefix"""
        p = "INCOMPLETE_BACKUP_"

        cmd = [
            "moveto",
            utils.pathjoin(self.destpath.logs, f"{p}diffs.json.gz"),
            utils.pathjoin(self.destpath.logs, "diffs.json.gz"),
        ]
        self.call(cmd)

        if not backup:
            return

        cmd = [
            "moveto",
            utils.pathjoin(self.destpath.logs, f"{p}backed_up_files.json.gz"),
            utils.pathjoin(self.destpath.logs, "backed_up_files.json.gz"),
        ]
        self.call(cmd)

    def copylog(self, logfile, logdest):
        cmd = [
            "copyto",
            str(logfile),
            str(logdest),
        ]
        self.call(cmd)

    def empty_dir_support(self, remote=None):
        """
        Return whether or not the remote supports 
        
        Defaults to True since if it doesn't support them, calling rmdirs
        will just do nothing
        """
        config = self.config
        if not remote:
            remote = self.config.dst
        features = json.loads(self.call(["backend", "features", remote], stream=False))

        return features.get("Features", {}).get("CanHaveEmptyDirectories", True)

    def init_check_interupt(self):
        """create the file and return whether or not it already exists"""
        statfile = self.local_cache_dir() / f"rirb/stat/{self.config._uuid}"
        statfile.parent.mkdir(exist_ok=True, parents=True)
        debug(f"writing interupt test file: {statfile}")
        try:
            statfile.touch(exist_ok=False)
            return False
        except OSError:
            debug("interupt test file EXISTS!")
            return True

    def end_check_interupt(self):
        statfile = self.local_cache_dir() / f"rirb/stat/{self.config._uuid}"
        statfile.unlink(missing_ok=True)
        debug(f"unlinking interupt test file: {statfile}")

    def call(self, cmd, stream=False, logstderr=True, display_error=True):
        """
        Call rclone. If streaming, will write stdout & stderr to
        log. If logstderr, will always send stderr to log (default)
        """
        config = self.config
        cmd = [self.config.rclone_exe] + cmd + self.config.rclone_flags + self.add_args
        debug("rclone:call", cmd)

        env = os.environ.copy()
        k0 = set(env)

        env.update(self.config.rclone_env)
        env["RCLONE_ASK_PASSWORD"] = "false"  # so that it never prompts

        if stream:
            stdout = subprocess.PIPE
            stderr = subprocess.STDOUT
        else:  # Stream to files to prevent a deadlock in the buffer
            # Random names for concurrent calls. Use random integers
            rnd = int.from_bytes(os.urandom(6), "little")
            stdout = open(f"{config.tmpdir}/std.{rnd}.out", mode="wb")
            stderr = open(f"{config.tmpdir}/std.{rnd}.err", mode="wb")

        t0 = time.time()
        proc = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, env=env)

        if stream:
            out = []
            with proc.stdout:
                for line in iter(proc.stdout.readline, b""):
                    line = line.decode(
                        errors="backslashreplace"
                    )  # Allow for bad encoding
                    line = line.rstrip()
                    log("rclone:", line)
                    out.append(line)
            out = "\n".join(out)
            err = ""  # Piped to stderr

        proc.wait()
        self.rclonetime += time.time() - t0

        if not stream:
            stdout.close()
            stderr.close()
            with open(stdout.name, "rt") as F:
                out = F.read()
            with open(stderr.name, "rt") as F:
                err = F.read()
            if err and logstderr:
                log(" rclone stderr:", err)

        if proc.returncode:
            if display_error:
                log("RCLONE ERROR")
                log("CMD", cmd)
                if stream:
                    log("STDOUT and STDERR", out)
                else:
                    log("STDOUT", out.strip())
                    log("STDERR", err.strip())
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, output=out, stderr=err
            )
        if not logstderr:
            out = out + "\n" + err
        return out
