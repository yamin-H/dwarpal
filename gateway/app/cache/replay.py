import re


def replay_pieces(text: str) -> list[str]:
    """Split a cached answer into word-sized pieces so it can be replayed as a stream."""
    return re.findall(r"\s*\S+|\s+$", text)