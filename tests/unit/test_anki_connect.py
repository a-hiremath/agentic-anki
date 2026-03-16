"""Tests for the AnkiConnect client."""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from anki_pipeline.retrieval_design.anki_connect import (
    AnkiConnectClient,
    AnkiConnectError,
    _build_anki_note,
    _note_fields,
)
from tests.unit.test_export import make_basic_note, make_cloze_note


def _mock_urlopen(response_body: dict[str, object]) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(response_body).encode("utf-8")
    context = MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = False
    return context


class TestHealthCheck:
    @patch("urllib.request.urlopen")
    def test_returns_version(self, mock_urlopen: MagicMock):
        mock_urlopen.return_value = _mock_urlopen({"result": 5, "error": None})
        client = AnkiConnectClient()

        assert client.health_check() == 5

    @patch("urllib.request.urlopen")
    def test_raises_on_url_error(self, mock_urlopen: MagicMock):
        mock_urlopen.side_effect = urllib.error.URLError("refused")
        client = AnkiConnectClient()

        with pytest.raises(AnkiConnectError):
            client.health_check()


class TestEnsureDeck:
    @patch("urllib.request.urlopen")
    def test_calls_create_deck(self, mock_urlopen: MagicMock):
        mock_urlopen.return_value = _mock_urlopen({"result": None, "error": None})
        client = AnkiConnectClient()
        client.ensure_deck("Math::Calc")

        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["action"] == "createDeck"
        assert payload["params"]["deck"] == "Math::Calc"


class TestEnsureNoteTypes:
    @patch("urllib.request.urlopen")
    def test_skips_existing_models(self, mock_urlopen: MagicMock):
        mock_urlopen.return_value = _mock_urlopen(
            {"result": ["STEMBasic", "STEMCloze"], "error": None}
        )
        client = AnkiConnectClient()
        client.ensure_note_types()

        assert mock_urlopen.call_count == 1

    @patch("urllib.request.urlopen")
    def test_creates_missing_models(self, mock_urlopen: MagicMock):
        mock_urlopen.side_effect = [
            _mock_urlopen({"result": [], "error": None}),
            _mock_urlopen({"result": None, "error": None}),
            _mock_urlopen({"result": None, "error": None}),
        ]
        client = AnkiConnectClient()
        client.ensure_note_types()

        assert mock_urlopen.call_count == 3
        payloads = [
            json.loads(call.args[0].data.decode("utf-8")) for call in mock_urlopen.call_args_list
        ]
        assert payloads[1]["params"]["modelName"] == "STEMBasic"
        assert payloads[2]["params"]["modelName"] == "STEMCloze"
        assert payloads[2]["params"]["isCloze"] is True


class TestAddNote:
    @patch("urllib.request.urlopen")
    def test_basic_payload(self, mock_urlopen: MagicMock):
        mock_urlopen.return_value = _mock_urlopen({"result": 1234, "error": None})
        note = make_basic_note()
        client = AnkiConnectClient()

        assert client.add_note("Math", note) == 1234

        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["action"] == "addNote"
        assert payload["params"]["note"]["modelName"] == "STEMBasic"

    @patch("urllib.request.urlopen")
    def test_cloze_payload(self, mock_urlopen: MagicMock):
        mock_urlopen.return_value = _mock_urlopen({"result": 5678, "error": None})
        note = make_cloze_note()
        client = AnkiConnectClient()

        assert client.add_note("Math", note) == 5678

        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["params"]["note"]["modelName"] == "STEMCloze"


class TestAnkiConnectError:
    @patch("urllib.request.urlopen")
    def test_non_null_error_field_raises(self, mock_urlopen: MagicMock):
        mock_urlopen.return_value = _mock_urlopen({"result": None, "error": "bad request"})
        client = AnkiConnectClient()

        with pytest.raises(AnkiConnectError):
            client.health_check()


class TestHelpers:
    def test_note_fields_basic(self):
        note = make_basic_note()
        fields = _note_fields(note)

        assert fields["Front"] == note.front
        assert fields["ExternalID"] == note.reviewed_note_id

    def test_build_anki_note_includes_tags(self):
        note = make_cloze_note()
        payload = _build_anki_note("Math", note)

        assert payload["deckName"] == "Math"
        assert payload["modelName"] == "STEMCloze"
        assert payload["tags"] == note.tags
