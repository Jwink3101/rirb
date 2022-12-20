# B2 Key that is safe from deletes

Making a key that can not delete files; only hide them (i.e. in rclone, cannot do `--b2-hard-delete`)

## Note

You should set the lifecycle rules so that files are *eventually* deleted if that is what you want. If you do not have a lifecycle rule of any kind, this isn't very useful!

## Create safe key

This comments out the keys but lists them all to make it easier. The full list of keys (last checked, 2022-11-30) is [in the B2 Docs](https://www.backblaze.com/b2/docs/application_keys.html)

I do this in Python since it is easier to comment and read but can be done in Bash as well.

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generate a safe key. This could be done in bash but 
I think the Python is easier to use and understand
"""
import os,subprocess

KEYNAME = 'safe'

env = os.environ.copy()
env['B2_APPLICATION_KEY_ID'] = '<account or keyID>'
env['B2_APPLICATION_KEY'] = '<key>'

capabilities = [
    "listKeys",
    # "writeKeys",
    # "deleteKeys",
    "listAllBucketNames",
    "listBuckets",
    "readBuckets",
    "writeBuckets", # rclone seems to need this. I don't understand why?!?!
    # "deleteBuckets",
    "readBucketRetentions",
    # "writeBucketRetentions",
    "readBucketEncryption",
    # "writeBucketEncryption",
    "listFiles",
    "readFiles",
    "shareFiles",
    "writeFiles", # Include hide
    # "deleteFiles",
    "readFileLegalHolds",
    # "writeFileLegalHolds",
    "readFileRetentions",
    # "writeFileRetentions",
    # "bypassGovernance",
    "readBucketReplications",
    # "writeBucketReplications
]

cmd = ['b2','create-key',KEYNAME,','.join(capabilities)]
subprocess.call(cmd,env=env)
```











