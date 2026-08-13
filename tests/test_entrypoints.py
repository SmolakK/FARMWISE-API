from farmwise_api.core.main_call import read_data as core_read_data
from farmwise_api import read_data
from farmwise_api.cli import app
from farmwise_api.server.main import STATIC_DIR, app as server_app


def test_local_library_entrypoint():
    assert read_data is core_read_data


def test_server_entrypoint():
    assert app is server_app


def test_server_static_assets_are_packaged_with_server():
    assert STATIC_DIR == STATIC_DIR.parent / "static"
    assert (STATIC_DIR / "style.css").is_file()
