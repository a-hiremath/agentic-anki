"""Tests for source ingestion (Spec Section 13.1)."""

import pytest
from pathlib import Path

from anki_pipeline.distillation.ingestion import ingest_source
from anki_pipeline.enums import EntryMode
from anki_pipeline.identity import source_fingerprint


class TestIngestSource:
    def test_ingest_markdown(self, tmp_path: Path):
        md_file = tmp_path / "sample.md"
        md_file.write_text("# Heading\n\nSome content here.\n", encoding="utf-8")
        record = ingest_source(md_file, run_id="run1")
        assert record.entry_mode == EntryMode.document
        assert record.media_type == "text/markdown"
        assert "Heading" in record.canonical_text
        assert record.char_count > 0
        assert len(record.source_fingerprint) == 64

    def test_ingest_txt(self, tmp_path: Path):
        txt_file = tmp_path / "sample.txt"
        txt_file.write_text("Plain text content.", encoding="utf-8")
        record = ingest_source(txt_file, run_id="run1")
        assert record.media_type == "text/plain"

    def test_source_fingerprint_deterministic(self, tmp_path: Path):
        content = "Deterministic content.\n"
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"
        f1.write_text(content, encoding="utf-8")
        f2.write_text(content, encoding="utf-8")
        r1 = ingest_source(f1, run_id="run1")
        r2 = ingest_source(f2, run_id="run2")
        assert r1.source_fingerprint == r2.source_fingerprint

    def test_different_content_different_fingerprint(self, tmp_path: Path):
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"
        f1.write_text("Content A", encoding="utf-8")
        f2.write_text("Content B", encoding="utf-8")
        r1 = ingest_source(f1, run_id="run1")
        r2 = ingest_source(f2, run_id="run1")
        assert r1.source_fingerprint != r2.source_fingerprint

    def test_bom_stripped(self, tmp_path: Path):
        f = tmp_path / "bom.txt"
        f.write_bytes(b"\xef\xbb\xbfHello world.")
        record = ingest_source(f, run_id="run1")
        assert not record.canonical_text.startswith("\ufeff")

    def test_file_not_found_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            ingest_source(tmp_path / "nonexistent.md", run_id="run1")

    def test_raw_file_hash_set(self, tmp_path: Path):
        f = tmp_path / "file.md"
        f.write_text("# Title\n\nContent.", encoding="utf-8")
        record = ingest_source(f, run_id="run1")
        assert record.raw_file_hash is not None
        assert len(record.raw_file_hash) == 64
