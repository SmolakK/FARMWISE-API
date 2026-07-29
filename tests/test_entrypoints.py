from core.main_call import read_data as core_read_data
from main import app
from main_call import read_data
from server.main import app as server_app


def test_local_library_entrypoint():
    assert read_data is core_read_data


def test_server_entrypoint():
    assert app is server_app
