"""Graphview API service."""

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    """Import the application factory lazily so model and migration imports stay side-effect free."""
    from graphview_api.main import create_app as factory

    return factory(*args, **kwargs)
