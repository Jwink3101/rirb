"""
rirb config File

This configuration file is read as Python so things can be customized as
desired. With few exceptions, any missing items will go to the defaults
already specified.

Rclone flags should always be a list. 
Example: `--exclude myfile` will be ['--exclude','myfile']

This is *ALWAYS* evaluated from the PARENT DIRECTORY OF THIS FILE. This is useful,
for example, if specifying filter files.

Defaults are sensible for a local source. Change as needed for others.

A few modules, including `os` and `Path = pathlib.Path` are already loaded along
with `log()` and `debug()`
"""
# Specify the source and destination. if local, no need to specify in
# reclone remote format
src = "<<MUST SPECIFY>>"
dst = "<<MUST SPECIFY>>"

# Specify FILTERING flags only. Note that if filtering flags are used later,
# it *will* cause issues. Examples of rclone filters:
#     --include --exclude --include-from --exclude-from --filter --filter-from
#     --exclude-if-present
#
# Must be specified as a list, e.g., ['--exclude','*.exc']
filter_flags = []

# General rclone flags are called every time rclone is called. This is how
# you can specify things like the conifg file.
# Remember that this config is evaluated from its parent directory.
#
# Example: ['--config','path/to/config']
#
# Note: Not all flags are compatible and may break the behavior, e.g. --progress
# Flags related to links such as `--links` or `--copy-links` should go HERE
rclone_flags = []

# The following are added to the existing environment.
# These should NOT include any filtering!
# Example: Getting config password
#   > from getpass import getpass
#   > rclone_env = {'RCLONE_CONFIG_PASS':getpass('Password: ')}
rclone_env = {}

# Specify the attributes to decide if a source file is modified.
#   'size'  : Did the size change. Acceptable but easy to have false negative
#   'mtime' : Did the size and modification time change. Requires that source has
#             ModTime. Can even use --use-server-modtime flags on the source
#   'hash'  : Use the hash. Note that using 'hash' with `reuse_hashes = 'mtime'`
#           : is *effectivly* still mtime
compare = "mtime"  # 'size', 'mtime', 'hash'

# Generally, comparisons are done from source-to-source but if run with --dst-list
# mode, the destination is relisted and used for comparison. If the destination
# does not support the same attributes of the source (e.g. use mtime on a local
# source but destination is WebDAV which doesn't support it), you can specify
# an alternative compare attribute. Options are the same as for `compare` plus
# `None` which means to use the same.
dst_compare = None  # None means use `compare`

# When listing the destination directly from --dst-list, you can specify additional
# flags that you may otherwise not need. For example, if the destination is S3, you
# may with to include --fast-list
dst_list_rclone_flags = []

# When there is any kind of backup interruption, the *right* thing to do is run it
# again with --dst-list. This will do it automatically. Note that if this is set, it
# write an empty lock file in `<rclone cache dir>/rirb/stat/<_uuid>`.
# Note: Turning this off will raise a warning on the next run but then clear it! It is
# NOT RECOMENDED to change this!
automatic_dst_list = True

# In order to make tracking an interrupted backup easier, the `backed_up_files.json.gz`
# and `diffs.json.gz` files get uploaded *BEFORE* the main backup. The `curr.json.gz`
# and `log.log` get uploaded afterwards. However, to ensure there are no mistakes, the
# `backed_up_files.json.gz` and `diffs.json.gz` can be prefixed until the backup
# completes. If this is False, it is still possible to identify incomplete backups by
# the missing log.log file
prefix_incomplete_backups = True

# Renames can be tracked if the file is unmodified other than the name.
#
# Tracking is done via the following. Note that the pool of considered
# files are *only* those that have been identified as new.
#
#   'size'    : Size of the file only. Not very safe. Use with extreme caution
#   'mtime'   : mtime and size. Slightly safer than size but still risky
#   'hash'    : Hash of the files.
#    False    : Disable rename tracking
#
# Because moving files has to be done with individual rclone calls, it is often more
# efficient to disable rename tracking as a delete and copy can be more efficient for
# lots of files. It also doesn't make sense to use renames if the remote doesn't support
# server-side copy or move.
#
# Note that when using --dst-list, renames are NOT tracked.
renames = False

# When doing mtime comparisons, what is the error to allow. Ideally, this
# should be small since it is always on the same machine but some filesystems
# have some slack.
dt = 1.1  # seconds

# Some remotes (e.g. S3) require an additional API call to get modtimes. If you
# are comparing with 'size' of 'hash', you can forgo this API call by setting
# this to False. Note that this may be ignored if modtimes are needed
get_modtime = True  # True means you DO save ModTime.

# Hashes can be expensive to compute on "SlowHash" remotes such as local or sftp.
# As such, rather than recompute them all, the hashes of the previous state
# can be used if they match based on this setting. If this is set, unmatched files
# are hased in a second call.
#
#   "size"  : Reuse hashes if filename and size match the previous
#   "mtime" : Reuse hashes if the filename, size, and mtime (within dt) match
#   False   : Do NOT reuse hashes. Note: Setting this to False on a "SlowHash"
#             remote *and* requiring hashes through other settings will be very slow.
reuse_hashes = "mtime"

# Some remotes (notably local) allow for multiple hash types. If this is specified
# AND hashes need to be computed, you can set the types. Specify as a single item
# (e.g. hash_type = 'sha1') or as a tuple (e.g. hash_type = 'sha1','md5'). If None
# (default), will do all possible
hash_type = None

# Even if the hashes are not needed for compare or move-tracking, it can be helpful
# to have the file hashes. It is NOT recommended for "SlowHash" remotes (e.g. local,
# sftp) unless you ALSO have `reuse_hashes` set. Note thatthis may be ignored if
# hashes are needed anyway.
get_hashes = False

# Clean up newly empty directories on the destination. Set to True, False, or 'auto'. If
# 'auto', will only do it for remotes that support empty directories
cleanup_empty_dirs = "auto"

# The `curr.json.gz` file on the destination is always current, but to save time,
# a local copy of the current file listing can also be stored. This saves a bit
# of time (and bandwidth). It will be named from the _uuid. Will use
# `<rclone cache dir>/rirb`.
use_local_cache = True

# Specify the path to the rclone executable.
rclone_exe = "rclone"

# Also store and transfer metadata. Uses rclone's metadata capabilities
# as outlined at https://rclone.org/docs/#metadata.
# Not all remotes (either source or dest) can read/write this but, if it can
# be read on the source, it will be preserved in the filelist
metadata = True

# Specify additional log directories. These should be full rclone remote directories
# to save the log in addition to the remote. Can specify as a single string or a
# list/tuple/etc if you wish to use multiple.
log_dest = None
# log_dest = "/full/path/to/local"
# log_dest = "/full/path/to/local", "remote:path/to/log"

## Pre- and Post-run
# Specify shell code to be evaluated before and/or after running syncrclone. Note
# these are all run from the directory of this config (as with everything else).
# STDOUT and STDERR will be captured. Note that there is no validation or
# security of the inputs. These are not actually called if using dry-run.
#
# If specified as a list, will run directly with subprocess. Otherwise uses shell=True
# The _post_ shell call also has "$STATS" defined which prints the run statistics
# including timing (which will be different than the final since the logs will not
# yet have been dumped)
pre_shell = ""
post_shell = ""

# Specify whether or not to allow an error in the shell commands above to continue
stop_on_shell_error = False

#######
# This should only be changed by the user when migrating from an older config
# to a newer one. Just because the current version of rirb and the version
# below do not match, it does not mean the run won't work.
_version = "__VERSION__"

# This is a random string that should be different in every config.
# Changing it could have unintended consequences if a run did not finish.
_uuid = "__UUID4__"
