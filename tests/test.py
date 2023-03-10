#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os, sys
from pathlib import Path
import gzip as gz
import json
import shutil
import textwrap
import re


p = os.path.abspath("../")
if p not in sys.path:
    sys.path.insert(0, p)

# Local
import testutils

# tool itself
import rirb.main
from rirb.config_example import dst as _  # This is just to test it for coverage


# 3rd Party
import pytest


def test_main():
    """
    Many tests under one roof...

    Tested things (Not exhaustive)

    - copy, move, delete, update, backup
    - Filters
    - backup lists (including the right hash)
    - hash_type
    - use_local_cache = False
    - unicode and space
    """

    test = testutils.Tester(name="main")

    test.config["filter_flags"] = ["--filter", "- *.exc"]
    test.config["renames"] = "hash"
    test.config["hash_type"] = "sha1"
    test.config["use_local_cache"] = False  # Tests the logic too
    test.write_config()

    test.write_pre(
        "src/unįçôde, spaces, symb°ls (!@#$%^&*) in €‹›ﬁﬂ‡°·—±", "did it work?"
    )
    test.write_pre("src/untouched.txt", "Do not modify")
    test.write_pre("src/mod_same-size.txt", "modify but not change size")
    test.write_pre("src/mod_diff_size.txt", "modify and change size")
    test.write_pre(
        "src/mod_same-size-mtime.txt", "modify but not change size OR modTime"
    )
    test.write_pre("src/touch.txt", "touch me")
    test.write_pre("src/sub/move.txt", "move me")
    test.write_pre("src/skip.exc", "skip me")
    test.write_pre("src/delete.txt", "delete me")

    # sync it
    test.cli("--init", "config.py")

    assert {("missing_in_dst", "skip.exc")} == test.compare_tree()

    # Modify
    test.write_post("src/new.txt", "new file")

    test.write_post("src/mod_same-size.txt", "ModifY BuT NoT ChangE SizE")
    test.write_post("src/mod_diff_size.txt", "modify and change size --DONE")

    stat0 = os.stat("src/mod_same-size-mtime.txt")
    test.write_post(
        "src/mod_same-size-mtime.txt", "Modify but Not change size OR modTime"
    )
    os.utime("src/mod_same-size-mtime.txt", (stat0.st_atime, stat0.st_mtime))

    Path("src/touch.txt").touch()
    test.move("src/sub/move.txt", "src/sub2/moved.txt")
    os.unlink("src/delete.txt")

    # Backup
    test.cli("config.py")

    ## Check it
    # Compare
    assert {
        ("disagree", "mod_same-size-mtime.txt"),  # expected since we fooled it
        ("missing_in_dst", "skip.exc"),
    } == test.compare_tree()

    # Backups

    backup_dir = test.backup_dirs()[-1]
    backed_up = set(os.listdir(backup_dir))
    gold = {
        "mod_same-size.txt": "modify but not change size",
        "mod_diff_size.txt": "modify and change size",
        "delete.txt": "delete me",
    }
    assert {p: test.read(os.path.join(backup_dir, p)) for p in backed_up} == gold

    # Test the information
    flistpath = Path(test.log_dirs()[-1]) / "backed_up_files.json.gz"
    with gz.open(flistpath) as fobj:
        flist = json.load(fobj)

    # Test that ONLY crc32 is used as per hash_type
    assert set(flist["delete.txt"]["Hashes"]) == {"sha1"}
    for path in gold:
        assert (
            test.sha1(os.path.join(backup_dir, path)) == flist[path]["Hashes"]["sha1"]
        ), f"hash wrong {path}"

    # Verify the diffs
    diffspath = Path(test.log_dirs()[-1]) / "diffs.json.gz"
    with gz.open(diffspath) as fobj:
        diffs = json.load(fobj)
    diffs = {k: v for k, v in diffs.items() if not k.startswith("_")}
    assert diffs == {
        "deleted": ["delete.txt"],
        "modified": ["mod_diff_size.txt", "mod_same-size.txt"],
        "new": ["new.txt"],
        "renamed": [["sub/move.txt", "sub2/moved.txt"]],
    }

    ## Aside: Just test writing new. Do not use test.cli() since it expects a
    #         a log
    import rirb.cli

    rirb.cli.cli(["new.py", "--new"])


def test_missing_local_list():
    test = testutils.Tester(name="missingloc")

    test.config["use_local_cache"] = True
    test.config["_uuid"] = "UUID"
    test.write_config()

    test.write_pre("src/file1.txt", "file1.")
    test.cli("--init", "config.py")
    assert len(test.compare_tree()) == 0

    # See that it gets used
    test.write_pre("src/file1.txt", "file1..")
    test.cli("config.py")
    debuglog = test.logs[-1][1]
    assert "DEBUG: Looking for local list: cache/rirb/UUID.json.gz ..." in debuglog
    assert "DEBUG: ...found" in debuglog
    assert "DEBUG: ...NOT found. Pulling" not in debuglog
    assert len(test.compare_tree()) == 0

    # See that it gets used
    test.write_pre("src/file1.txt", "file1...")
    os.unlink("cache/rirb/UUID.json.gz")
    test.cli("config.py")
    debuglog = test.logs[-1][1]
    assert "DEBUG: Looking for local list: cache/rirb/UUID.json.gz ..." in debuglog
    assert "DEBUG: ...found" not in debuglog
    assert "DEBUG: ...NOT found. Pulling" in debuglog
    assert len(test.compare_tree()) == 0


@pytest.mark.parametrize("attrib", ("size", "mtime", "hash", "fail-hash", None))
def test_dst_list(attrib):
    """
    Test using the dst_list.

    attrib = 'fail-hash' will do 'hash' but withOUT computing them locally. This
    should fail!
    """
    test = testutils.Tester(name="dst-list")

    attrib0 = attrib
    if attrib == "fail-hash":
        compare = "size"
        attrib = "hash"
    else:
        compare = "hash"

    test.config["compare"] = compare
    test.config["reuse_hashes"] = False
    test.config["dst_compare"] = attrib
    test.config["hash_type"] = "crc32"
    test.config["dst_list_rclone_flags"] = ["--fast-list"]
    test.write_config()

    test.write_pre("src/file1.txt", "file1.")
    test.write_pre("src/file2.txt", "file2..")
    test.write_pre("src/file3.txt", "file3...")

    test.cli("--init", "config.py")
    assert test.compare_tree() == set()

    # Now write stuff at dst
    test.write_post("dst/curr/file2.txt", "file2..MOD")
    test.move("dst/curr/file3.txt", "dst/curr/file-3.txt")
    test.write_post("dst/curr/file4.txt", "file4....")

    miss = {
        ("missing_in_src", "file-3.txt"),
        ("disagree", "file2.txt"),
        ("missing_in_dst", "file3.txt"),
        ("missing_in_src", "file4.txt"),
    }
    assert test.compare_tree() == miss

    # Sync
    test.cli("config.py")
    assert test.compare_tree() == miss  # Should have missed them!
    assert test.logs[-1][1].count("--fast-list") == 1  # Just in the config

    # Try again with --dst-list. This should now clean it up.
    if attrib0 == "fail-hash":
        try:
            test.cli("config.py", "--dst-list", "--debug")
            assert False, "Expected failure!"
        except rirb.main.NoCommonHashError:
            print("Failed as expected")
            return

    test.cli("config.py", "--dst-list")
    assert test.compare_tree() == set()
    assert test.logs[-1][1].count("--fast-list") == 2  # config and call


def test_automatic_dst_list_and_prefix():
    """Test that automatic dst_list works in various ways"""
    test = testutils.Tester(name="auto-dst-list")

    test.config["compare"] = "mtime"
    test.config["_uuid"] = "myuuid"
    # test.config["automatic_dst_list"] = True # default
    # test.config["prefix_incomplete_backups"] = True # default
    test.write_config()

    test.write_pre("src/file1.txt", "file1.")

    # Initial run
    test.cli("config.py", "--init")
    assert test.compare_tree() == set()

    # Make it fail with a catch...
    test.write_pre("src/file1.txt", "file1...")
    test.write_pre("dst/curr/newtxt", "should not be here")
    try:
        rirb.rclone._TEST_FAIL_LOC = "transfer"
        test.cli("config.py", "--debug")  # use --debug so we can catch it
    except ValueError:
        pass
    finally:
        rirb.rclone._TEST_FAIL_LOC = None
    assert test.compare_tree() == {
        ("disagree", "file1.txt"),
        ("missing_in_src", "newtxt"),
    }
    # test filelist prefixes
    assert set(os.listdir(test.log_dirs()[-1])) == {
        "INCOMPLETE_BACKUP_backed_up_files.json.gz",
        "INCOMPLETE_BACKUP_diffs.json.gz",
        "FAILED_log.log",
    }

    # ... then run it again. It *should* now use --dst-list AUTOMATICALLY
    test.cli("config.py")
    assert test.compare_tree() == set()
    assert (
        "Previous run did not complete. Moving to --dst-list mode" in test.logs[-1][0]
    )

    # Do it again with the mode off
    test.config["automatic_dst_list"] = False
    test.config["prefix_incomplete_backups"] = False
    test.write_config()
    test.write_pre("src/file1.txt", "file1....")
    test.write_pre("dst/curr/newtxt", "should not be here")
    try:
        rirb.rclone._TEST_FAIL_LOC = "transfer"
        test.cli("config.py", "--debug")  # use --debug so we can catch it
    except ValueError:
        pass
    finally:
        rirb.rclone._TEST_FAIL_LOC = None

    assert test.compare_tree() == {
        ("disagree", "file1.txt"),
        ("missing_in_src", "newtxt"),
    }
    # test filelist prefixes. Should be missing
    assert set(os.listdir(test.log_dirs()[-1])) == {
        "diffs.json.gz",
        "backed_up_files.json.gz",
        "FAILED_log.log",
    }

    # Now this should (a) raise a warning and (b) not delete the errant file
    test.cli("config.py")
    assert "!!!! This one may fail without --dst-list! !!!!" in test.logs[-1][0]
    assert test.compare_tree() == {("missing_in_src", "newtxt")}

    # Running again should have the same issues but NOT raise a warning since the
    # last run was successful. This is an issue of sorts...
    test.cli("config.py")
    assert "!!!! This one may fail without --dst-list! !!!!" not in test.logs[-1][0]
    assert test.compare_tree() == {("missing_in_src", "newtxt")}

    # Now write the file myself but also allow it to rerun and make sure it works
    test.config["automatic_dst_list"] = True
    test.write_config()
    Path("cache/rirb/stat/myuuid").touch()
    test.cli("config.py")
    assert (
        "Previous run did not complete. Moving to --dst-list mode" in test.logs[-1][0]
    )
    assert test.compare_tree() == set()


def test_move_attribs():
    """Test unclear moves and make sure they don't happen"""
    test = testutils.Tester(name="unique_moves")

    # Size is a horrible rename attribute but it's easy to fake here so we will use it.
    test.config["renames"] = "size"
    test.write_config()

    test.write_pre("src/file1.txt", "file1")  # 1,2,3 have the same size
    test.write_pre("src/file2.txt", "file2")
    test.write_pre("src/file3.txt", "file3")
    test.write_pre("src/file4.txt", "file4....")
    test.write_pre("src/file5.txt", "file5.....")

    test.cli("--init", "config.py")
    assert test.compare_tree() == set()

    # Move just one
    test.move("src/file1.txt", "src/file1MOVED.txt")
    test.cli("config.py")
    assert test.compare_tree() == set()
    assert "Move 'file1.txt' --> 'file1MOVED.txt'" in test.logs[-1][0]

    # Move the others.
    test.move("src/file2.txt", "src/file2MOVED.txt")
    test.move("src/file3.txt", "src/file3MOVED.txt")
    test.move("src/file4.txt", "src/file4MOVED.txt")
    test.cli("config.py")
    assert test.compare_tree() == set()
    assert "Move 'file2.txt' --> 'file2MOVED.txt'" not in test.logs[-1][0]
    assert "Move 'file3.txt' --> 'file3MOVED.txt'" not in test.logs[-1][0]
    assert "Move 'file4.txt' --> 'file4MOVED.txt'" in test.logs[-1][0]
    assert "Too many matches for file2MOVED.txt. Not moving" in test.logs[-1][0]
    assert "Too many matches for file3MOVED.txt. Not moving" in test.logs[-1][0]

    test.move("src/file5.txt", "src/file5MOVED.txt")
    test.cli("config.py", "--dst-list")
    assert "Move 'file5.txt' --> 'file5MOVED.txt'" not in test.logs[-1][0]
    assert "Rename tracking ignored for --dst-list" in test.logs[-1][0]


def test_log_dests():
    """Tests saving the logs to multiple locations"""
    test = testutils.Tester(name="log_dests")

    test.write_config()

    test.write_pre("src/file.txt", "file")
    test.cli("--init", "config.py")

    # Test the main dest
    gold = test.logs[-1][0].strip()
    assert gold == (Path(test.log_dirs()[-1]) / "log.log").read_text().strip()

    # Do it again with additional dests
    test.config["log_dest"] = "newlog/"
    test.write_config()
    test.write_pre("src/file.txt", "file.")
    test.cli("config.py")

    gold = test.logs[-1][0].strip()
    assert gold == (Path(test.log_dirs()[-1]) / "log.log").read_text().strip()
    assert gold == next(Path("newlog/").glob("*.log")).read_text().strip()

    # Do it again with two additional dests
    test.config["log_dest"] = "newlog2/", "alt:logs"
    test.write_config()
    test.write_pre("src/file.txt", "file..")
    test.cli("config.py")

    gold = test.logs[-1][0].strip()
    assert gold == (Path(test.log_dirs()[-1]) / "log.log").read_text().strip()
    assert gold == next(Path("newlog2/").glob("*.log")).read_text().strip()
    assert gold == next(Path("alt/logs").glob("*.log")).read_text().strip()


def test_shell():
    import subprocess

    test = testutils.Tester(name="shell")
    test.config["pre_shell"] = """echo "PRE"\necho "PRE" > shell\n exit 4"""
    test.config["post_shell"] = """echo "POST"\necho "POST" >> shell\necho "$STATS" """
    test.config["fail_shell"] = textwrap.dedent(
        """
        echo "FAIL"
        echo "FAIL" >> shell
        echo LOGS "$LOGPATH"
        echo DEBUG "$DEBUGPATH" """
    )
    test.config["stop_on_shell_error"] = False
    test.write_config()

    test.write_pre("src/file.txt", "file")
    test.cli("--init", "config.py")

    log = test.logs[-1][0]
    for txt in [
        "pre.shell.out: PRE",
        '$ echo "PRE"',
        '$ echo "POST"',
        "post.shell.out: POST",
        "post.shell.out: Deleted: 0 files",  # stats
        "WARNING: Command return non-zero returncode: 4",
        "post.shell.out: Elapsed Time:",
    ]:
        assert txt in log, f"Missing {txt}"
    assert Path("shell").read_text().strip() == "PRE\nPOST"

    # Do it again but do not allow errors
    test.config["stop_on_shell_error"] = True
    test.write_config()

    test.write_pre("src/file.txt", "file.")
    try:
        test.cli("config.py", "--debug")  # --debug will make it throw the error
        assert False  # Should not have gotten here
    except subprocess.CalledProcessError:
        pass

    assert Path("shell").read_text().strip() == "PRE\nFAIL", "did not call fail_shell"
    logdir = Path(test.log_dirs()[-1])
    failed_log = logdir / "FAILED_log.log"
    assert failed_log.exists()  # implied below but nice to see
    assert "Attempting to upload logs. May fail" in failed_log.read_text()

    # With a dict (pre) and a list post
    os.environ["TEST0"] = "env test"
    test.config["pre_shell"] = {
        "cmd": [
            sys.executable,
            "-c",
            textwrap.dedent(
                """
                    import os, json
                    res = {"TEST0":os.environ.get("TEST0","FAIL"),
                           "TEST1":os.environ.get("TEST1","FAIL"),
                           "cwd":os.getcwd(),}
                    print(f"CAPTURE>>>{json.dumps(res)}<<<CAPTURE")
                     """
            ),
        ],
        "env": {"TEST1": "pre dict env"},
        "cwd": os.path.expanduser("~"),
    }

    test.config["post_shell"] = ["echo", "%(STATS)s" + "\n%(TEST0)s" + "\n%%(TEST1)s"]
    test.write_config()

    test.write_pre("src/file.txt", "file..")
    test.cli("config.py")

    log = test.logs[-1][0]

    # Post list cmd
    for txt in [
        r"""post.shell: ['echo', '%(STATS)s\n%(TEST0)s\n%%(TEST1)s']""",  # command
        "post.shell.out: Total",  # %(STATS)s
        "post.shell.out: env test",  # %(TEST0)s
        "post.shell.out: %(TEST1)s",  # %%(TEST1)s
    ]:
        assert txt in log, f"missing {txt}"

    # Pre dict cmd
    matches = re.findall("CAPTURE>>>(.*?)<<<CAPTURE", log)
    assert len(matches) == 2  # listing and then actual results
    pre_dict = json.loads(matches[1])
    assert pre_dict.pop("TEST0") == "env test"
    assert pre_dict.pop("TEST1") == "pre dict env"
    assert pre_dict.pop("cwd") == os.path.expanduser("~")
    assert len(pre_dict) == 0  # Should be nothing left


def test_dry_run():
    test = testutils.Tester(name="dry")

    test.config["renames"] = "mtime"
    test.config["pre_shell"] = """echo "PRE"\necho "PRE" > shell"""
    test.config["post_shell"] = """echo "POST"\necho "POST" >> shell"""
    test.write_config()

    test.write_pre("src/move.txt", "move abcde")
    test.write_pre("src/del1.txt", "del1")
    test.write_pre("src/del2.txt", "del1")
    test.write_pre("src/mod.txt", "mod")
    test.cli("--init", "config.py")

    test.write_pre("src/mod.txt", "mod.")
    test.write_pre("src/new1.txt", "new1", dt=-10)
    test.move("src/move.txt", "src/move1.txt")
    os.unlink("src/del1.txt")
    test.cli("config.py")
    assert len(test.compare_tree()) == 0
    assert len(test.backup_dirs()) == 1

    test.write_pre("src/mod.txt", "mod..")
    test.write_pre("src/new1.txt", "new1", dt=-20)
    test.move("src/move1.txt", "src/move2.txt")
    os.unlink("src/del2.txt")
    os.unlink("shell")

    comp0 = test.compare_tree()
    test.cli("config.py", "--dry-run")
    assert test.compare_tree() == comp0
    log = test.logs[-1][0]

    for txt in [
        "Planned Actions",
        "modified: 'mod.txt'",
        "modified: 'new1.txt'",
        "deleted: 'del2.txt'",
        "rename: 'move1.txt' --> 'move2.txt'",
        'pre.shell.DRY-RUN: $ echo "PRE"',
        'post.shell.DRY-RUN: $ echo "POST"',
    ]:
        assert txt in log, f"missing {txt}"

    assert not Path("shell").exists()  # should not have been run


@pytest.mark.parametrize("mode", [True, False, "auto"])
def test_dir_cleanup(mode):
    """Test cleaning up newly empty dirs"""

    test = testutils.Tester(name="dir-clean")

    test.config["cleanup_empty_dirs"] = mode
    test.write_config()

    test.write_pre("src/dir1/file1.txt", "file1")
    test.write_pre("src/dir2/file2.txt", "file2")

    test.cli("--init", "config.py")

    test.move("src/dir1/file1.txt", "src/dirONE/file1.txt")
    test.move("src/dir2/file2.txt", "src/dirTWO/file2.txt")
    test.write_post("dst/curr/dir2/errant file.txt", "aa")

    test.cli("config.py")

    assert Path("dst/curr/dir1").exists() == (not mode in {"auto", True})
    assert Path("dst/curr/dir2").exists()  # Added an extra file so it will be there


def test_no_modtime():
    """
    Make sure ModTimes are turned off when they are supposed to be
    """
    test = testutils.Tester(name="no_modtime")

    test.config["compare"] = "size"
    test.config["dst_compare"] = "size"
    test.config["renames"] = False
    test.config["get_modtime"] = False
    test.config["metadata"] = False
    test.write_config()

    test.write_pre("src/file1.txt", "file")

    test.cli("--init", "config.py", "--debug")

    with gz.open(Path(test.log_dirs()[-1]) / "curr.json.gz", "rb") as fobj:
        files = json.load(fobj)
    assert not files["file1.txt"].get("ModTime", "")

    # Just quickly show that any of these can trigger it
    test.config["compare"] = "mtime"
    test.write_config()

    test.cli("--init", "config.py", "--debug")  # make sure to run with --init again
    with gz.open(Path(test.log_dirs()[-1]) / "curr.json.gz", "rb") as fobj:
        files = json.load(fobj)
    assert files["file1.txt"].get("ModTime", "")


def test_redacted_pass():
    """
    Make sure RCLONE_CONFIG_PASS is redacted
    """
    test = testutils.Tester(name="RCLONE_CONFIG_PASS")
    test.config["rclone_env"]["RCLONE_CONFIG_PASS"] = "donotshow"
    test.write_config()

    test.write_pre("src/file1.txt", "file")

    # With debug mode
    obj = test.cli("--init", "config.py", "--debug")
    assert "donotshow" not in test.logs[-1][0]
    assert "donotshow" not in test.logs[-1][1]

    # Without debug mode
    obj = test.cli("--init", "config.py")
    assert "donotshow" not in test.logs[-1][0]
    assert "donotshow" not in test.logs[-1][1]

    # Check the config object -- Not really needed since the user won't see it
    assert "donotshow" not in str(obj.config)
    assert "donotshow" not in repr(obj.config)


def test_override():
    """Test the --override setting"""
    test = testutils.Tester(name="override")

    test.config["compare"] = "size"
    test.write_config()

    test.write_pre("src/dir1/file.txt", "file")
    test.cli("--init", "config.py")

    # Modify it and show that it doesn't work
    test.write_post("src/dir1/file.txt", "diff", add_dt=10)
    test.cli("config.py")
    assert test.compare_tree() == {("disagree", "dir1/file.txt")}

    # Now override it to use mtime and this should work
    test.write_post("src/dir1/file.txt", "difF", add_dt=20)
    test.cli("config.py", "--override", "compare = 'mtime'")
    assert test.compare_tree() == set()


@pytest.mark.parametrize("webdav", (True, False))
def test_links(webdav):
    """
    Test handling symlinks. Use the webdav server to test a remote that isn't
    symlink aware
    """

    if webdav:
        dport = 56789
        dst = f":webdav,url='http://localhost:{int(dport)}':"
    else:
        dst = None

    test = testutils.Tester(name="symlinks", dst=dst)

    test.config["rclone_flags"] = ["--links"]
    test.write_config()

    test.write_pre("src/file1.txt", "file1")
    os.symlink("file1.txt", "src/link1.txt")
    os.symlink("link1.txt", "src/link2link1.txt")
    os.symlink("file1.txt", "src/linkDEL.txt")

    test.write_pre("src/dir/file2.txt", "file2.0")
    os.symlink("dir/", "src/linkdir")

    if webdav:
        dwebdav = testutils.WebDAV("dst", port=dport)

    test.cli("--init", "config.py")

    if webdav:  # This is a bit nasty because of the .rclonelink
        res = {
            ("missing_in_dst", "linkDEL.txt"),
            ("missing_in_src", "linkDEL.txt.rclonelink"),
            ("missing_in_dst", "link1.txt"),
            ("missing_in_src", "link1.txt.rclonelink"),
            ("missing_in_dst", "link2link1.txt"),
            ("missing_in_src", "link2link1.txt.rclonelink"),
            ("missing_in_dst", "linkdir/file2.txt"),
            ("missing_in_src", "linkdir.rclonelink"),
        }
    else:
        res = set()
    assert test.compare_tree() == res

    test.write_post("src/file1.txt", "file1 mod")
    os.unlink("src/linkDEL.txt")
    test.cli("config.py")

    if webdav:
        res.difference_update(
            {
                ("missing_in_src", "linkDEL.txt.rclonelink"),
                ("missing_in_dst", "linkDEL.txt"),
            }
        )

    assert test.compare_tree() == res

    if webdav:
        dwebdav.close()


def test_dir_moves():
    test = testutils.Tester(name="dirmove")

    test.config["filter_flags"] = ["--exclude", "*.exc", "--exclude", "no/**"]
    test.config["reuse_hashes"] = False
    test.config["renames"] = "hash"
    test.write_config()

    test.write_pre("src/dir-move-all/file1.txt", "file.")
    test.write_pre("src/dir-move-all/file2.txt", "file..")

    test.write_pre("src/dir-move-all-replace/file3.txt", "file...")
    test.write_pre("src/file4.txt", "file....")

    test.write_pre("src/dir-move-some/file5.txt", "file.....")
    test.write_pre("src/dir-move-some/file6-keep.txt", "file......")

    test.write_pre("src/dir-move-exc/file7.txt", "file.......")
    test.write_pre("src/dir-move-exc/file8.exc", "file........")

    test.write_pre("src/dir-move-excdir/file9.txt", "file.........")
    test.write_pre("src/dir-move-excdir/no/file10.txt", "file..........")
    test.write_pre("src/dir-move-excdir/yes/file11.txt", "file...........")

    test.write_pre("src/dir-move-withsub/file12.txt", "file............")
    test.write_pre("src/dir-move-withsub/sub/file13.txt", "file.............")

    test.write_pre("src/sub1/sub2/sub3/sub4/sub5/file14.txt", f"file{'.'*14}")
    test.write_pre("src/sub1/sub2/sub3/sub4/sub5/file15.txt", f"file{'.'*15}")

    test.write_pre("src/s1/s2/s3/s4/s5/file16.txt", f"file{'.'*16}")
    test.write_pre("src/s1/s2/s3/s4/s5/file17.txt", f"file{'.'*17}")

    test.write_pre("src/D1/D2/file18.txt", f"file{'.'*18}")

    test.cli("--init", "config.py")

    assert test.compare_tree() == {
        ("missing_in_dst", "dir-move-exc/file8.exc"),
        ("missing_in_dst", "dir-move-excdir/no/file10.txt"),
    }

    shutil.move("src/dir-move-all", "src/dir-MOVED-all")

    shutil.move("src/dir-move-all-replace/", "src/dir-MOVED-all-replace/")
    test.move("src/file4.txt", "src/dir-move-all-replace/file4.txt")

    test.move("src/dir-move-some/file5.txt", "src/dir-MOVED-some/file5.txt")

    shutil.move("src/dir-move-exc/", "src/dir-MOVED-exc/")

    shutil.move("src/dir-move-excdir/", "src/dir-MOVED-excdir/")

    shutil.move("src/dir-move-withsub/", "src/dir-MOVED-withsub/")

    shutil.move("src/sub1/sub2/sub3/sub4/sub5/", "src/sub1/subTwo/subThree/sub4/sub5/")
    shutil.move("src/s1/s2/s3/s4/s5/", "src/new/sub/")

    Path("src/dd1/D2/").mkdir(parents=True, exist_ok=True)
    shutil.move("src/D1/D2/file18.txt", "src/dd1/D2/file-18.txt")

    test.cli("config.py")
    assert test.compare_tree() == {
        ("missing_in_dst", "dir-MOVED-exc/file8.exc"),
        ("missing_in_dst", "dir-MOVED-excdir/no/file10.txt"),
    }


if __name__ == "__main__":
    # test_main()
    # test_missing_local_list()
    # for attrib in ("size", "mtime", "hash", "fail-hash", None):
    #     test_dst_list(attrib)
    # test_automatic_dst_list_and_prefix()
    # test_move_attribs()
    # test_log_dests()
    # test_shell()
    test_dry_run()
    # for mode in [True, False, "auto"]:
    #     test_dir_cleanup(mode)
    # test_no_modtime()
    # test_redacted_pass()
    # test_override()
    # test_links(False)
    # test_links(True)
    # test_dir_moves()
    print("--- PASSED ---")
