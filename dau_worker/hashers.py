import importlib.metadata
from typing import Protocol

from feluda.factory import AudioFactory, VideoFactory
from feluda.operators import MediaHash


class Hasher(Protocol):
    algorithm: str

    def hash(self, file_key: str) -> str: ...


class FeludaMediaHasher:
    algorithm = f"feluda-media-hash@{importlib.metadata.version('feluda-media-hash')}"

    def __init__(self, factory) -> None:
        self.factory = factory

    def hash(self, file_key: str) -> str:
        media = self.factory.make_from_url(file_key)
        # A new operator per call: MediaHash keeps its result on the instance, so a shared one
        # could return another concurrent job's hash.
        return MediaHash().run(media, remove_after_processing=True)


HASHERS: dict[str, Hasher] = {
    "video": FeludaMediaHasher(VideoFactory),
    "audio": FeludaMediaHasher(AudioFactory),
}
