import pytest
from jobs.repair_legacy_images import main


def test_retired_image_repair_fails_without_network(caplog):
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert 'retired' in caplog.text
