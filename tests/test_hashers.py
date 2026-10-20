import hashlib
import importlib.metadata

from feluda.factory import VideoFactory

from dau_worker.hashers import FeludaMediaHasher


class FakeFactory:
    def __init__(self, path):
        self.path = path
        self.requested = []

    def make_from_url(self, url):
        self.requested.append(url)
        return {"path": self.path}


def test_hashes_the_downloaded_file_with_blake2b_and_deletes_it(tmp_path):
    media_file = tmp_path / "0b6c2f2e"
    media_file.write_bytes(b"hello")
    factory = FakeFactory(str(media_file))

    hash_value = FeludaMediaHasher(factory).hash("temp/0b6c2f2e")

    assert hash_value == hashlib.blake2b(b"hello").hexdigest()
    assert factory.requested == ["temp/0b6c2f2e"]
    assert not media_file.exists()


def test_algorithm_names_the_installed_operator_version():
    version = importlib.metadata.version("feluda-media-hash")

    assert FeludaMediaHasher(VideoFactory).algorithm == f"feluda-media-hash@{version}"
