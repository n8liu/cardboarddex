import importlib.util
from pathlib import Path
from unittest.mock import Mock
import pytest

spec = importlib.util.spec_from_file_location('backup', Path(__file__).with_name('backup.py'))
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def test_upload_requires_matching_remote_checksum(tmp_path):
    path = tmp_path / 'archive'
    path.write_bytes(b'backup-data')
    s3 = Mock()
    s3.put_object.return_value = {'ChecksumSHA256': 'incorrect'}
    with pytest.raises(RuntimeError, match='checksum'):
        backup.upload(s3, 'bucket', 'key', path)


def test_backup_failure_does_not_publish_manifest(tmp_path, monkeypatch):
    config = tmp_path / 'backup.env'
    config.write_text(f'BACKUP_BUCKET=test\nBACKUP_DIRECTORY={tmp_path}/backups\n')
    monkeypatch.setattr(backup, 'run', Mock(side_effect=RuntimeError('pg_dump failed')))
    s3_factory = Mock()
    monkeypatch.setattr(backup.boto3, 'client', s3_factory)
    with pytest.raises(RuntimeError, match='pg_dump failed'):
        backup.backup(str(config), str(tmp_path))
    assert not list((tmp_path / 'backups').glob('*/manifest.json'))
    s3_factory.assert_not_called()
