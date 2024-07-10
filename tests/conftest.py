import pytest


@pytest.fixture(autouse=True)
def media_root(settings, tmpdir):
    settings.MEDIA_ROOT = str(tmpdir)
