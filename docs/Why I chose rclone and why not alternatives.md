# Why I chose rclone/rirb and why not alternatives

## Why not block based

The biggest alternative I considered are block-based backup tools such as [restic][restic], [Borg][borg], [duplicacy][duplicacy], [kopia][kopia], [Arq][arq] (I think), and others. They work by splitting the files into block (based on a really cool content-defined chunking algorithm) and backing up the files by blocks. For each backup, they have a database of all of the files and all of the blocks that go into that file. It is "synthetic full backups". You can view every run as a full snapshot. Restoring any snapshot, whether the first or last, is the same.

[restic]:https://restic.net/
[borg]: https://www.borgbackup.org/
[duplicacy]: https://duplicacy.com/
[kopia]:https://kopia.io/
[arq]:https://www.arqbackup.com/

What is so great about them is that they deduplicate between all files and across all versions. And they do this *implicitly* too! If you modify a small bit of a large file, only that block gets backup. If you move a file, it will get rechunked and then not have to upload or store it again. Same if you move it *and* modify it. It is all implicit and automatic. And as it is full snapshots, it is also easy to decide how to prune it long term! 

They also present (generally speaking) the filesystem as a *full snapshot*. So when you go to restore, it is the full system as it stood when it was backed up.

The dissadvantages? The biggest is that they require their software to recover and you cannot really do any introspection on the backup without it. Since all that is stored is blobs of data and the final database, it can be hard to do anything with it. Also, if you were to, say, order a recovery drive, you can't easily select which files you want. And if the database gets correupted, you are out of luck.

They also often have issues around pruning and cleaning old data blobs. Enough so that I worry about the recovery. And very few offer ways to "rewrite" a backup and remove something you didn't intent to backup (this is a feature as well as a bug!)

## Why not hardlink-based

Hard-link based backups such as Time Machine, rsync (not rclone) with `--link-dest`, and [rsnapshot](https://rsnapshot.org/) are really creative. They are incremenetal in that they only back up new files but they have full snapshots by making cheap "hard links" to the past files (or directories for Time Machine). This means they are very storage efficient but still incremental and full-snapshot. The biggest advantage is that they are 100% native. No software or anything; just a Unix-like (POSIX?) file system! And as it is full snapshots, it is also easy to decide how to prune it long term!

However, they need to reside on a file system so object storage or even *most* cloud storages are off limits. And they do not support encryption other than at the filesystem level. They also do not usually track moves or do any kind of deduplication.

## Why rclone-based including rirb

*For rclone* - To be clear, as discussed before, this is rclone with `--backup-dir`. So you backup the files and anything that is modified or deleted gets moved to a backup dir.

*For rirb* - Backups by default.

This is great because it is easy. 1:1 file on source to file on destination. This makes recovery easy and not dependant on rclone (except for decryption if used). It is also simple which is a major benefit for backups. You can use any rclone support storage as the destination (or even the source).

Moves can be tracked (though there are caveats and issues depending on setup) but there is no other deduplication. This approach also does *not* present full snapshots. If you accidentally delete files, they can be found. And it is easy to restore the *latest* but it is hard to restore to a point-in-time. I keep the hashes and filelists so it can be scripted but it is not easy! Also, you can prune by deleted backups you don't need but you cannot do something like say "keep 1 backup per week".

Another advantage is that you can mount the backup from cloud storage and use it for serving! You can mount block-based too but they are not designed for serving files. It is not clear how they will perform.

To be clear, there are also disadvantages to this approach such as the lack of full-snapshots and the inefficiency. But those are worth it for the other advantages

## Why NOT [forward] incremental (and why reverse is okay!)

Some tools, such as [duplicity](https://duplicity.gitlab.io/) are \[forward\] incremental. That means it does a full backup and then adds to the "chain" with only differences. On it's face, this is fine since, to restore, you restore the full and "replay" the differences. The problem is that as the chain of diffs get long, it becomes (a) inefficient and/or (b) not robust to errors. Even the [duplicity FAQs](https://duplicity.gitlab.io/FAQ.html) say "Keep the number of incrementals for a maximum of one month, then do a full backup" No thanks!

There are advantages to forward incremental if you are writing to immutable media (or immutable cloud storage) but since restore is just so much more complicated, it isn't worth it.

Reverse Incremental, which is what rirb/rclone does, is different in that at the end of the backup run you have the current full state and then a copy of all modified/deleted files (a "reverse" chain if you will). The advantage of this is that to restore, you are always *directly* restoring the latest backup. The disadvantage is that you cannot easily do a *full* restore of a previous point in time. It's not impossible; just hard. See [proof of concept](../restore_proof_of_concept). However, *most* uses of a backup are either a full restore or to cherry-pick a modified file.

## Conclusion

rclone/rirb as a backup tool is far from perfect. But the simplicity and ease of use makes it a good tradeoff!