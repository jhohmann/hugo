"""Validierung von Quellenlinks für Speicherung und Darstellung."""

import re
from urllib.parse import quote, urlsplit

SOURCE_LINK_PATTERN = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s<>]+?)\)")


def source_url(value: str) -> str | None:
    """Nur absolute HTTP(S)-Links ohne Zugangsdaten oder Steuerzeichen."""
    if not isinstance(value, str) or any(
        char.isspace() or ord(char) < 32 or char in '\\<>"' for char in value
    ):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            return None
        parsed.port
    except ValueError:
        return None
    return quote(value, safe=":/?#[]@!$&'*+,;=%~_-")
