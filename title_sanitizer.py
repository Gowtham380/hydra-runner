"""
Root shim for ingester.title_sanitizer
"""
from ingester.title_sanitizer import (
    KNOWN_PIRATE_SITES,
    KNOWN_VALID_ACRONYMS_AND_SHORT_WORDS,
    strip_pirate_and_channel_prefixes,
    extract_tech_specs,
    clean_movie_title,
    clean_series_title,
    parse_video_line,
    sanitize_movie_title
)

__all__ = [
    "KNOWN_PIRATE_SITES",
    "KNOWN_VALID_ACRONYMS_AND_SHORT_WORDS",
    "strip_pirate_and_channel_prefixes",
    "extract_tech_specs",
    "clean_movie_title",
    "clean_series_title",
    "parse_video_line",
    "sanitize_movie_title"
]
