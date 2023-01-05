# Changelog

Newest on top

## 20230105.0.BETA

- Added an optimization to the move tracking execution. While not as optimized as full directory moving (which I contend has [too many edge cases](docs/Directory_Move_Optimization.md)), it batches moves within common directory paths when possible. This still requires rclone to make file moves (as opposed to directory moves) but it avoids duplicate checks and enables rclone's (superior) threading.
- Minor code changes around `rclone.call()`

## 20230103.0.BETA

(minor)

- Improved log inside the code
- Code cleanup
- documentation

## 20221229.0.BETA

- Added the ability to specify `subprocess.Popen` flags for the pre/post/fail`_shell` values. ("`shell`" is now really a misnomer but I'll keep it).
- Minor:
    - Modified some code and added some tests on directory moving. This was originally in preparation for a directory-moving optimization. However, I decided it was *NOT* worth it and [documented that decision](docs/Directory_Move_Optimization.md)

## 20221226.0.BETA

- When using `--dst-list`, the destination listing will happen concurrently with listing the source.

## 20221221.0.BETA

- Tries to upload logs (to `FAILED_log.log` and other modified names) if a failure occurs. Depending the cause of the failure, it may not work but it'll try! (e.g., misconfigured flags).
- Adds the new `fail_shell` configuration. This will (try to) run a shell command if the run fails. Useful to send a notification of failure.

## 20221220.0.BETA

- Initial Version!