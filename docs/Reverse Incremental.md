# Reverse Incremental Backups (and naming)

Many people, myself included, have referred to the following style backups as "forever forward incremental"

    $ rclone sync source: dest:curr --backup-dir dest:back/<date>

However, I believe **this is an incorrect classification**. I believe this should be classified as "reverse incremental".

Let me explain.

Let's ignore the "forever" part. It just muddies the waters.

Incremental backup looks like:

```
Run 0:  Full-Backup0
Run 1:  Full-Backup0 + diffs1
Run 2:  Full-Backup0 + diffs1 + diffs2
...
Run N:  Full-Backup0 + diffs1 + diffs2 + ... + diffsN
```

You need to take the initial Full-backup0 and play forward the chain of diffs to get to any arbitrary state

Reverse incremental is as follows:

```
Run 0: Full-Backup0
Run 1:              Full-Backup1
                    Mods0
Run 2:                            Full-Backup2
                    Mods0         Mods1
...
Run N:                            Full-Backup2  ... Full-BackupN
                    Mods0         Mods1         ... ModsN-1
```

This is also what the aforementioned rclone command returns. At any given point in time, the full backups (`dest:curr`) is the most up to date with the mods to get there (`dest:back/<date>`) being `ModsN-1`. To get to an arbitrary state, you start at `Full-BackupN` and replay in reverse until you get to the desired state. Or start at the desired state and run forward. Either way, you do **not need anything about the backup state prior to the desired one**.

Note that rirb does not provide the tools to recover to an arbitrary state but *can do it* in ideal conditions. See [Proof of Concept](../restore_proof_of_concept/readme.md). However, it is not the intended use of this tool.