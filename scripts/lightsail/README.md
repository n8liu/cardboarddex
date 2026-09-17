These scripts operate on production only when explicitly invoked with production configuration.

- `provision.py`: preview AWS resources; `--apply` provisions the $7 instance and private backup bucket. Secrets are written under ignored `.system_generated/lightsail/`, mode 0600, never printed.
- `bootstrap.sh`: root-only setup on a clean Ubuntu 24.04 AMD64 instance.
- `release.sh`: server-side deployment, used by `../deploy_to_lightsail.sh`; never migrates schemas.
- `backup.py`: root systemd backup, `/etc/cardboarddex/backup.env` and `/etc/cardboarddex/app.env`.
- `restore.sh`: refuses existing tables; `RESTORE_CONTAINER` must explicitly name an empty destination.
- `verify_backup.py`: freshness validation; `--restore` verifies downloaded archives on a disposable Docker container.
- `ecr_cleanup.py`: preview unless `--apply`; supply both running and rollback digests using repeated `--protect`.

Never use `docker compose down -v`. The database volume is external and explicitly named. SSH host keys must be verified independently; do not replace verification with `ssh-keyscan` alone.
