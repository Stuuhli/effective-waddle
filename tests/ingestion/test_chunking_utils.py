from __future__ import annotations

from src.ingestion.pipeline import _sanitize_page_text, _split_long_tokens


def test_sanitize_page_text_removes_data_uri() -> None:
    text = (
        "Intro ![caption](data:image/png;base64,AAAA) middle "
        '<img src="data:image/png;base64,BBBB" alt="" /> '
        "data:image/png;base64,CCCC <!-- image --> end"
    )

    cleaned = _sanitize_page_text(text)

    assert cleaned == "Intro middle end"


def test_split_long_tokens_breaks_large_segments() -> None:
    long_word = "a" * 9000
    words = ["start", long_word, "end"]

    result = _split_long_tokens(words, max_length=2048)

    assert result[0] == "start"
    assert result[-1] == "end"
    # The long token should have been split into multiple pieces within bounds.
    assert all(len(piece) <= 2048 for piece in result[1:-1])
    reconstructed = "".join(result[1:-1])
    assert reconstructed == long_word