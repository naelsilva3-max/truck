import pytest


@pytest.fixture(autouse=True)
def _isolate_media_root(settings, tmp_path):
    """
    Redirect MEDIA_ROOT to a pytest-managed temp dir for every test, so
    tests that save ImageField/FileField instances don't write real files
    into the project's media/ folder.
    """
    settings.MEDIA_ROOT = str(tmp_path)
