# Directory Move Optimization (and why I don't do it)

The way rclone and rirb handle moved directories is at a file-by-file level (I confirmed empirically with rclone and `-vv` logs). In fact, in general, both tools don't ever think about directories except to remove empty ones as requested.

The problem is, moving lots of small files can be very slow. And many remotes support moving an entire directory (the notable exceptions are bucket-based ones like B2 and S3). So if you move a directory on the source, it can be vastly sped up to call a similar directory move on the destination.

---

**BLUF**: While I considered this optimization, it had too many edge cases and I deemed it too risky. Backups do not need to be fast all of the time.

---

Here was my thought process

## Examine Parents

Given a file: `some/long/directory/chain/for/file.ext`, the parent is `some/long/directory/chain/for/`. 

In order to detect presumed-empty directories, I already compute all all of the parents. I devised a scheme where I would convert all moves into their parents. For example:

    sub/dir/file1.txt -->  sub/folder/file1.txt  ==> sub/dir/ -->  sub/folder/

I would require that no file exist in the new directory (`sub/folder`) *and* no file exist in the original (`sub/dir`). This way, if you didn't *actually* move everything, it wouldn't get moved too. (And if there's excluded files remaining, you're only moving the destination side so it doesn't matter).

The problem with this approach is subdirectories. If you have many subdirectories, they will also show as moved meaning if you move the deeper directory first, you can't later move the other. And if you move the highest level first, you need to exclude the move of the other.

## Examine Parents at the *moved* directory

To avoid the subdirectory issue, I also looked at only finding the *moved* parent

    sub/dir/file1.txt -->  new/dir/file1.txt  ==> sub/ -->  new/

(since `dir/file1.txt` remained). Again with the requirement that `new/` not currently exist and `sub/` be empty.

This seemingly solves the parent directory problem since unchanged sub directories will *also* move when I move the directory. However, there is a new edge case we need to consider: Multiple destinations

## Multiple Destinations Edge Case

If a directory has more than one file and/or subdirectory that moves to different places, then you can't move it.

    sub/file1.txt --> new/file1.txt             ==> sub/ --> new/
    sub/file2.txt --> other/file2.txt           ==> sub/ --> other/
    sub/dir/file3.txt --> sub/folder/file3.txt  ==> sub/dir --> sub/folder
    
These conflict and you need to be really careful. In fact, these would not qualify.

## Existing Destinations Edge Case

While we included the check that no files are in the dest, depending on exactly how you implement that check, it is easy to miss if two files are moved there. Or, rather, two directories.

Consider the following. Note that even a single file move, if it's the only file in the directory, will look like a directory move (more on that later)

    dir1/file1.txt --> new/file1.txt    ==> dir1/ --> new/
    dir2/file2.txt --> new/file2.txt    ==> dir2/ --> new/

Again, this is *probably* avoided but easy to implement incorrectly and you could end up breaking the transfer because you missed it and moved one sooner.

## A Path Forward -- Not used

My current thinking, should I choose to implement this idea, is to do the "Parent at the *moved* directory" approach *and* require that the files be *exactly* the same (same file names, no mods, etc). However, if you even change one file *while* moving it, this will break. It does fix the speed but becomes less useful since you need to have moved without also modifying any files. Again, a lot of conditions and edge cases

## Efficiency considerations

Another twist is efficiency of moving a few files vs a dir. For remotes that support it, it *may* be okay, though I am not sure what rclone does under the hood to validate the move (needs to make sure the dest isn't there?). For remotes that don't support it, rclone now has to do it itself. This is probably faster than how I can call it but may still be less efficient.

## Current Optimization

While directory moves remain too risky, the current approach is to batch common paths and use `rclone move` with  `--files-from`. Even if all files are listed to move, rclone still does it as a file-by-file move but it removes the overhead of checking destinations. In (limited) testing, this speeds up operations dramatically.

## Conclusion

The idea of doing a directory move is nice since you do not have to call so many individual moves. But in reality, there are just so many edge cases, including ones I may not have considered, that it isn't worth it. If that backup takes *MUCH* longer, then so be it!

One option, with its own tradeoff of course, is to manually do the dirmove on the destination but then **must run with `--dst-list` next time** to avoid a problem. Depending on the remote `--dst-list` may be worse than the moves.

I am not saying I will *never* add this optimization, but for now, I am far from convinced it is worth it.


