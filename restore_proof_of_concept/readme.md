# Proof-of-Concept: Restore to point in time

These notebooks are documenting and validation the proof-of-concept that you can, using the information saved by rirb, restore to a single point in time.

**This type of recovery is not the intended use of rirb**. While this demonstrates that it can be done, if this is the type of recovery that will often be requested, there are much better tools out there.

The goal is to have a list of files to transfer in order to restore. 

The following is **outside the scope of this proof-of-concept** but is not particularly challenging:

- **Restoring a sub-directory** - You would simply need to filter the results
- **Performing the transfer** - It is easy enough to do it one-by-one but it could be optimized (especially when there aren't renames) so that the number of rclone calls could be reduced
- **Metadata** - The file lists have the metadata. The restore could be walked and permissions and times could be set. 
- **repair** - It is assumed that every (reverse) increment up to and including the desired state is still saved and there were never interuptions. The final backup should have been successful.
    - What can go wrong: If a backup was interupted while moving files, the needed files may be unaccounted for, though they will still exists in *somehwere* in the destination. You can use the `diffs.json.gz` (or `INCOMPLETE_BACKUP_diffs.json.gz`) and `backed_up_files.json.gz` (or `INCOMPLETE_BACKUP_backed_up_files.json.gz`) to identify and fix.
    - The codes currently do **NOT** account for that. It will manifest as a missing file when it gets restored. Again, _If full point-in-time backups are your primary use case, **this is the wrong tool**_
   

There are two stategies presented.

- **Hash Based**: If hashes are computed on the source files, they they can be used to restore. Note that the destination files *need not be reshashed* as that information resides in the `logs` directory. This method is more robust and theoretically faster
- **Diff Based**: By starting at the desired state and playing forward any diffs (`diffs.json.gz`) until the final state (`curr`), the appropriate source file can be found. This even includes if there were renames.

Again, this process is not polished or optimized. It is not part of the tool, but the methods are demonstrated

## What can go wrong

The biggest issue will be if there is an interrupted backup in the chain. This means that there will be a `diffs.json.gz` file that does not accurately represent all files in the corresponding backup directory. This will be apparent because there will be no corresponding `log.log` file in the `logs/` top-level directory *and*, at least by default, the `diffs.json.gz` will actually be `INCOMPLETE_BACKUP_diffs.json.gz`. It will have to be manually fixed.

Again, if full restores to a prior state is your desired use case, check out other tools.