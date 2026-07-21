"""The transitio feed editor: a local map GUI over the transitio library."""

from transitio_editor._app import create_app

__all__ = ["create_app", "__version__"]


def __getattr__(name):
    if name == "__version__":
        from importlib.metadata import version

        return version("transitio-editor")
    raise AttributeError(f"module 'transitio_editor' has no attribute {name!r}")
