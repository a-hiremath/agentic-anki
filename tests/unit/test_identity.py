"""Tests for content-based identity functions (Spec Section 9.2)."""

import pytest
from pathlib import Path

from anki_pipeline.enums import NoteType
from anki_pipeline.identity import (
    content_hash,
    file_hash,
    generate_id,
    note_identity_hash,
    source_fingerprint,
)


class TestSourceFingerprint:
    def test_deterministic(self):
        text = "Some source text with content."
        assert source_fingerprint(text) == source_fingerprint(text)

    def test_different_text_different_hash(self):
        assert source_fingerprint("text A") != source_fingerprint("text B")

    def test_hex_sha256(self):
        fp = source_fingerprint("hello")
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_whitespace_normalization_considered(self):
        # trailing whitespace should not affect fingerprint
        a = source_fingerprint("hello   \n")
        b = source_fingerprint("hello\n")
        assert a == b


class TestContentHash:
    def test_deterministic(self):
        h = content_hash("definition", "A set is a collection of distinct elements.")
        assert h == content_hash("definition", "A set is a collection of distinct elements.")

    def test_type_affects_hash(self):
        claim = "The derivative is the rate of change."
        assert content_hash("definition", claim) != content_hash("formula", claim)

    def test_case_insensitive_claim(self):
        assert content_hash("definition", "HELLO WORLD") == content_hash("definition", "hello world")

    def test_whitespace_collapsed(self):
        assert content_hash("definition", "hello   world") == content_hash("definition", "hello world")


class TestNoteIdentityHash:
    def test_basic_deterministic(self):
        h1 = note_identity_hash(NoteType.stem_basic, front="What is X?", back="X is Y.")
        h2 = note_identity_hash(NoteType.stem_basic, front="What is X?", back="X is Y.")
        assert h1 == h2

    def test_basic_changes_on_front_change(self):
        h1 = note_identity_hash(NoteType.stem_basic, front="What is X?", back="X is Y.")
        h2 = note_identity_hash(NoteType.stem_basic, front="What is Z?", back="X is Y.")
        assert h1 != h2

    def test_cloze_deterministic(self):
        h1 = note_identity_hash(NoteType.stem_cloze, text="The {{c1::cat}} sat on the mat.")
        h2 = note_identity_hash(NoteType.stem_cloze, text="The {{c1::cat}} sat on the mat.")
        assert h1 == h2

    def test_cloze_changes_on_text_change(self):
        h1 = note_identity_hash(NoteType.stem_cloze, text="The {{c1::cat}} sat.")
        h2 = note_identity_hash(NoteType.stem_cloze, text="The {{c1::dog}} sat.")
        assert h1 != h2

    def test_basic_and_cloze_different_for_same_content(self):
        h1 = note_identity_hash(NoteType.stem_basic, front="hello", back="world")
        h2 = note_identity_hash(NoteType.stem_cloze, text="hello world")
        assert h1 != h2

    def test_invalid_note_type_raises(self):
        with pytest.raises(ValueError):
            note_identity_hash("invalid_type", front="x", back="y")  # type: ignore

    def test_none_back_extra_vs_empty(self):
        h1 = note_identity_hash(NoteType.stem_basic, front="Q?", back="A.", back_extra=None)
        h2 = note_identity_hash(NoteType.stem_basic, front="Q?", back="A.", back_extra="")
        # None and empty string should normalize to same hash
        assert h1 == h2

    def test_semantic_edit_changes_hash(self):
        h1 = note_identity_hash(NoteType.stem_basic, front="What is X?", back="X is Y.")
        h2 = note_identity_hash(NoteType.stem_basic, front="What is X?", back="X is Z, not Y.")
        assert h1 != h2


class TestFileHash:
    def test_deterministic(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        assert file_hash(f) == file_hash(f)

    def test_different_content_different_hash(self, tmp_path: Path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"hello")
        f2.write_bytes(b"world")
        assert file_hash(f1) != file_hash(f2)

    def test_hex_sha256(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"test")
        h = file_hash(f)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestGenerateId:
    def test_returns_string(self):
        assert isinstance(generate_id(), str)

    def test_unique(self):
        ids = {generate_id() for _ in range(100)}
        assert len(ids) == 100

    def test_uuid4_format(self):
        import uuid
        uid = generate_id()
        parsed = uuid.UUID(uid)
        assert parsed.version == 4
