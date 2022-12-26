# Changelog

Newest on top

## 20221226.0.BETA

- When using `--dst-list`, the destination listing will happen concurrently with listing the source.

## 20221221.0.BETA

- Tries to upload logs (to `FAILED_log.log` and other modified names) if a failure occurs. Depending the cause of the failure, it may not work but it'll try! (e.g., misconfigured flags).
- Adds the new `fail_shell` configuration. This will (try to) run a shell command if the run fails. Useful to send a notification of failure.

## 20221220.0.BETA

- Initial Version!