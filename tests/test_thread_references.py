import pytest

from app.tools.thread_references import ThreadReferenceError, reference_ids


def test_explicit_identifiers_only_and_deduplication():
    assert reference_ids("V-42, v-007 und V-42: vergleichen.") == [42, 7]
    assert reference_ids("42, #42, AV-42, V-42x, https://example.org/V-42") == []


@pytest.mark.parametrize("text", ["V-0", "V-9223372036854775808", "V-" + "9" * 100,
                                  " ".join(f"V-{i}" for i in range(1, 12))])
def test_invalid_reference_rejected(text):
    with pytest.raises(ThreadReferenceError):
        reference_ids(text)
