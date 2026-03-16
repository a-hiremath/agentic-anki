"""Thin AnkiConnect client for direct note export."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, cast

from anki_pipeline.enums import NoteType
from anki_pipeline.models import ReviewedNote

_API_VERSION = 5

_STEM_BASIC_FIELDS = ["Front", "Back", "BackExtra", "Source", "Tags", "ExternalID"]
_STEM_CLOZE_FIELDS = ["Text", "BackExtra", "Source", "Tags", "ExternalID"]
_STEM_BASIC_TEMPLATE = {
    "Name": "Card 1",
    "Front": "{{Front}}",
    "Back": "{{FrontSide}}<hr id=answer>{{Back}}<br>{{BackExtra}}",
}
_STEM_CLOZE_TEMPLATE = {
    "Name": "Cloze",
    "Front": "{{cloze:Text}}",
    "Back": "{{cloze:Text}}<br>{{BackExtra}}",
}


class AnkiConnectError(RuntimeError):
    """Raised when AnkiConnect returns an error or is unreachable."""


class AnkiConnectClient:
    def __init__(self, url: str = "http://localhost:8765", timeout: int = 10) -> None:
        self._url = url
        self._timeout = timeout

    def _invoke(self, action: str, **params: object) -> object:
        """POST a single AnkiConnect action and return the result payload."""
        payload = json.dumps(
            {"action": action, "version": _API_VERSION, "params": params}
        ).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise AnkiConnectError(f"Cannot reach Anki at {self._url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise AnkiConnectError("AnkiConnect returned invalid JSON") from exc

        if not isinstance(body, dict):
            raise AnkiConnectError("AnkiConnect returned an invalid response")
        if body.get("error"):
            raise AnkiConnectError(f"AnkiConnect error: {body['error']}")
        if "result" not in body:
            raise AnkiConnectError("AnkiConnect response did not include a result")
        return body["result"]

    def health_check(self) -> int:
        """Return the API version reported by AnkiConnect."""
        return int(self._invoke("version"))

    def ensure_deck(self, deck_name: str) -> None:
        self._invoke("createDeck", deck=deck_name)

    def ensure_note_types(self) -> None:
        existing = cast(list[str], self._invoke("modelNames"))
        if "STEMBasic" not in existing:
            self._invoke(
                "createModel",
                modelName="STEMBasic",
                inOrderFields=_STEM_BASIC_FIELDS,
                css="",
                cardTemplates=[_STEM_BASIC_TEMPLATE],
                isCloze=False,
            )
        if "STEMCloze" not in existing:
            self._invoke(
                "createModel",
                modelName="STEMCloze",
                inOrderFields=_STEM_CLOZE_FIELDS,
                css="",
                cardTemplates=[_STEM_CLOZE_TEMPLATE],
                isCloze=True,
            )

    def add_note(self, deck_name: str, note: ReviewedNote) -> int:
        result = self._invoke("addNote", note=_build_anki_note(deck_name, note))
        return int(result)


def _note_fields(note: ReviewedNote) -> dict[str, str]:
    tags_str = " ".join(note.tags)
    if note.note_type == NoteType.stem_basic:
        return {
            "Front": note.front or "",
            "Back": note.back or "",
            "BackExtra": note.back_extra or "",
            "Source": note.source_field,
            "Tags": tags_str,
            "ExternalID": note.reviewed_note_id,
        }
    if note.note_type == NoteType.stem_cloze:
        return {
            "Text": note.text or "",
            "BackExtra": note.back_extra or "",
            "Source": note.source_field,
            "Tags": tags_str,
            "ExternalID": note.reviewed_note_id,
        }
    raise ValueError(f"Unknown note type: {note.note_type!r}")


def _build_anki_note(deck_name: str, note: ReviewedNote) -> dict[str, Any]:
    return {
        "deckName": deck_name,
        "modelName": note.note_type.value,
        "fields": _note_fields(note),
        "tags": note.tags,
    }
