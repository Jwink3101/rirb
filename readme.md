# rirb -- Reverse Incremental Rclone Backup

Helper tool using rclone under-the-hood to make reverse-incremental backups.

## TL/DR

This mimics 

    $ rclone sync source: dest:curr --backup-dir dest:back/<date>` 
    
but is faster since it stores the previous backup listing. It also keeps some additional data, automates saving logs, and uses a (more traceable and repeatable) configuration file.

Because it stores diffs and other state information, full point-in-time recovery is possible, though that is *not* the indended use and can break. See [Restore Proof of Concept](restore_proof_of_concept/readme.md).

Backups with rclone and/or rirb are not the most efficient, advanced, fast, featurefull, complete, sexy, or sophisticated. However, they are **simple, easy to use, easy to understand, easy to verify, easy to restore, and robust**. For backups, that is a great tradeoff.

## Overall philosophy:

The end result should be *very* similar to

    $ rclone sync source: dest:curr --backup-dir dest:back/<date>

This is a **HELPER** tool. It is not designed to do *everything* needed for backups. It is aimed at the *intermediate* user (i.e. me) and may still need some modifications and/or manual scritping. Notably, situations *not* covered are:

- **Restores**: Restores should be done directly through rclone (with `--metadata` if supported). If that is not possible, you may have to change permissions.
- **Verification / Repairs**: If the `curr` gets modified outside of this tool, you can run with `--dst-list`. Can also use `rclone check` (and/or `cryptcheck` to verify).
- **Seeding Files**: Files can be seeded to the remote but then they must either be incorporated with `--dst-list` or be **manually** added to the `curr.json.xz`, preferably *with* hashes.
- **Advanced recovery from interrupted state** - Interruptions can be recovered by running again with `--dst-list` mode. But if you need to recover from an interrupted state *before* it can be run again, it may need to be done manually with reading the backup file lists. Nothing is *EVER* deleted so all of the files are there, but may take a bit of work.

## Why use this over rclone

Rclone can be used directly without a problem but rirb offers some additional features

- No need to list destination files (vast speedup since that can be very slow and use a lot of API calls)
- A list of hashes can be kept including what what backed up/modified.
- Store and compare (except with `--dst-list`), ModTime on nominally unsupported remotes (e.g. WebDAV)
- Alternative hash database tracking vs hasher remote. (I think it’s easier to understand but that is up for debate)
- Better move tracking including disallowing moved that cannot be *uniquely* identified.

The nice thing is, this is **just a helper**. Without it, you still have your backup and you can change strategy at any time. You do not need rirb for restores and you can easily migrate your backup strategy.

## Setup

Install directly from github:

    $ python -m pip install git+https://github.com/Jwink3101/rirb
    
Then make a config file with `--new`. Set all of your configurations and then run with `--init`.

## Usage

One major flag to consider is `--dst-list`. This means the destination *is* actually listed and used for comparison. It is helpful when the destination may be out of sync with the local (e.g., interrupted backup). Note that moves are not tracked and an optionally different compare attribute is used.

### Configuration

To get a new config file, do:

    $ rirb --new <config-file.py>

The configuration file is read as a Python file (and note, has no security. Do not load untrusted inputs). It is **heavily documented**. Most options are based around attributes.

Whereas an rclone call does this automatically, you need to set them for rirb. Look at the [matrix of remotes](https://rclone.org/overview/) to decide what to do.

Suggestions:

- If the source supports ModTimes, use at *least* `mtime`. (Except S3. See below)
    - Even if the remote doesn't support ModTime, you can use `mtime` for normal backups and `dst_compare = 'size'` for when using `--dst-list`.
- If the source suports hashes *and* they are fast (e.g. most cloud remotes such as S3, B2, Dropbox, OneDrive, GoogleDrive, etc), use hashes. Be weary of hashes on local and SFTP as they are slow.
- Remember that `dst_compare` must be compatible between remotes but also only an issue when using `--dst-list` flag. For example, while `size` is not great, if you use it to *cleanup* the backup (from interruptions, etc), it is acceptable.
- If using S3:
    - As the **source**: set `get_modtime = False` since ModTime on S3 is expensive.
    - As the **dest**: Set `dst_compare = 'size'` or `'hash'`
        - Only use `hash` if also hashing source and the hashes are compatible.

If the source supports metadata, use it even if the dest does not. Or *always* use it since it's harmless.

## Remote Layout

The structure on the destination will look something like the following

```text
dst  
├── back  
│   └── <dated entries>  
│       └── <file tree>  
│           └── <files...>  
├── curr  
│   └── <current full directory tree>  
└── logs  
    └── <dated entries>  
        ├── backed_up_files.json.gz
        ├── curr.json.gz
        ├── diffs.json.gz
        └── log.log
```

At the top:

- `curr` is the full backup as it stands when last run. If you are restoring everything, this is what you'd want to copy
- `logs/<dated entries>` - This hold the main information about the backup. This includes
    - `backed_up_files.json.gz` - gzip-compressed json of the files that are in the corresponding `back/<dated entries>` directory. These are also accessible from the *previous* `curr` file if needed
    - `curr.json.gz` - gzip-compressed json file of the `curr` as it existed when the backup was made.
    - `diffs.json.gz` - gzip-compressed json file of all files that were new, modified, deleted, or renamed. Just the file-names. The file properties can be created from the `curr.json.gz` or `backed_up_files.json.gz`
    - `log.log` - Log file of the backup. Note that it terminates before the log itself is copied.
- `back/<dated entries>` - Deleted or modified files from the backup.

Note that, *by design*, the `backed_up_files.json.gz` and `diffs.json.gz` will get written *before* backup and the `curr.json.gz` and `log.log` after. To help identify if the backup failed, they will get prefixed "`INCOMPLETE_BACKUP_`" (but this can be disabled). Regardless, incomplete backups can be identified by the presence of `backed_up_files.json.gz` and `diffs.json.gz` (with or without their prefix) and the lack of `log.log`

## Interrupted Backups

If a backup is interrupted during upload but *before* the file list is uploaded, it could leave the backup in a hybrid state where some files updated, deleted, or moved. 

Running again with `--dst-list` should fix everything (even though less efficiently). If recovery is needed without that option, then it can be done from the file-lists and some manual scripting.

By default, an interrupted backup is run with `dst-list`

As noted above, the `backed_up_files.json.gz` and `diffs.json.gz` will be present to help with any tracking but with a prefix.

## Initial large backups

During the initial backups, it should be run with `--dst-list` until it is fully backed up. This is, for all intents and purposes, like just running with `rclone sync`, but will allow for incomplete backups.

## Known Issues and Deficiencies

- rirb will **intentionally** not allow a move when it cannot be uniquely identified based on the attribute. This includes when using hashes as the attributes. Theoretically, it should be allowed since the content is the same but we do not. Even when hashes are the attribute, moves still require *unique* identification