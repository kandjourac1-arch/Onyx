"""Package Onyx V2 avec chargement différé du serveur Flask."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .server import app

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    """Expose l'application Flask sans initialiser l'audio à chaque import."""
    if name == "app":
        from .server import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
