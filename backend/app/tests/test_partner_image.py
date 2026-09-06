"""Contact profile image upload — SPEC.md §5 UPLOAD_DIR, §17 P1.

Every test points UPLOAD_DIR at a tmp_path first, so a run never writes into
the real backend/uploads and never leaves a file behind.
"""

from __future__ import annotations

import io

import pytest
from sqlalchemy.orm import Session

from app.core.enums import PartnerType
from app.core.uploads import MAX_IMAGE_BYTES, upload_root
from app.models.partner import Partner

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"


@pytest.fixture(autouse=True)
def isolated_upload_dir(tmp_path, monkeypatch):
    """Redirect UPLOAD_DIR at the settings object every test reads."""
    from app.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    return tmp_path / "uploads"


@pytest.fixture()
def partner(db: Session) -> Partner:
    row = Partner(name="Open Wood", partner_type=PartnerType.both)
    db.add(row)
    db.flush()
    return row


def _png(size: int = 64) -> bytes:
    """A byte string that starts like a real PNG and is `size` bytes long."""
    return PNG_SIGNATURE + b"\x00" * max(0, size - len(PNG_SIGNATURE))


def _stored(upload_dir) -> list:
    """What is on disk. A rejected upload never creates the directory at all,
    which counts as nothing stored rather than as an error.
    """
    return sorted(upload_dir.iterdir()) if upload_dir.exists() else []


def _post(client, partner_id: int, content: bytes, name: str, content_type: str):
    return client.post(
        f"/api/partners/{partner_id}/image",
        files={"file": (name, io.BytesIO(content), content_type)},
    )


# --- the happy path ---------------------------------------------------------


def test_a_valid_png_is_accepted_and_stored(client, partner, isolated_upload_dir):
    response = _post(client, partner.id, _png(), "avatar.png", "image/png")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["image_url"].startswith("/uploads/")
    assert body["image_url"].endswith(".png")

    stored = _stored(isolated_upload_dir)
    assert len(stored) == 1
    assert stored[0].read_bytes() == _png()


def test_a_valid_jpeg_is_accepted(client, partner):
    content = JPEG_SIGNATURE + b"\x00" * 100
    response = _post(client, partner.id, content, "photo.jpeg", "image/jpeg")

    assert response.status_code == 200, response.text
    assert response.json()["image_url"].endswith(".jpg")


def test_the_clients_filename_is_discarded(client, partner, isolated_upload_dir):
    """★ A traversal attempt must not escape the upload directory, and must not
    even survive as a name — core/uploads.py generates its own.
    """
    response = _post(client, partner.id, _png(), "../../../../.env", "image/png")

    assert response.status_code == 200, response.text
    stored = _stored(isolated_upload_dir)
    assert len(stored) == 1
    assert stored[0].parent == isolated_upload_dir
    assert ".env" not in stored[0].name
    # 32 hex characters from secrets.token_hex(16), plus the extension.
    assert len(stored[0].stem) == 32
    assert not (isolated_upload_dir.parent.parent / ".env").exists()


def test_uploading_again_replaces_the_previous_file(
    client, partner, isolated_upload_dir
):
    first = _post(client, partner.id, _png(), "one.png", "image/png").json()
    second = _post(
        client, partner.id, JPEG_SIGNATURE + b"\x01" * 50, "two.jpg", "image/jpeg"
    ).json()

    assert first["image_url"] != second["image_url"]
    # The old file is unlinked, not orphaned on disk.
    assert [p.name for p in _stored(isolated_upload_dir)] == [
        second["image_url"].removeprefix("/uploads/")
    ]


# --- rejections -------------------------------------------------------------


def test_an_oversized_image_is_rejected(client, partner, isolated_upload_dir):
    too_big = PNG_SIGNATURE + b"\x00" * MAX_IMAGE_BYTES

    response = _post(client, partner.id, too_big, "huge.png", "image/png")

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "IMAGE_TOO_LARGE"
    assert _stored(isolated_upload_dir) == []


def test_a_file_at_exactly_the_limit_is_accepted(client, partner):
    """The boundary is >, not >=."""
    response = _post(
        client, partner.id, _png(MAX_IMAGE_BYTES), "limit.png", "image/png"
    )

    assert response.status_code == 200, response.text


def test_a_wrong_content_type_is_rejected(client, partner, isolated_upload_dir):
    response = _post(client, partner.id, b"#!/bin/sh\necho hi\n", "x.sh", "text/plain")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_IMAGE_TYPE"
    assert _stored(isolated_upload_dir) == []


def test_a_non_image_disguised_as_a_png_is_rejected(
    client, partner, isolated_upload_dir
):
    """★ Content-Type is client-supplied (R6), so the bytes decide."""
    response = _post(
        client, partner.id, b"<?php system($_GET['c']); ?>", "shell.png", "image/png"
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_IMAGE_TYPE"
    assert _stored(isolated_upload_dir) == []


def test_an_empty_file_is_rejected(client, partner):
    response = _post(client, partner.id, b"", "empty.png", "image/png")

    assert response.status_code == 415


def test_a_missing_contact_id_is_404(client, isolated_upload_dir):
    response = _post(client, 999999, _png(), "avatar.png", "image/png")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert _stored(isolated_upload_dir) == []


def test_an_archived_contact_cannot_be_given_an_image(client, partner, db: Session):
    partner.is_active = False
    db.flush()

    response = _post(client, partner.id, _png(), "avatar.png", "image/png")

    assert response.status_code == 404


def test_a_contact_role_cannot_upload(contact_client, partner):
    """Same gate as PUT /partners/{id} — admin and accountant only (§12.2)."""
    response = contact_client.post(
        f"/api/partners/{partner.id}/image",
        files={"file": ("avatar.png", io.BytesIO(_png()), "image/png")},
    )

    assert response.status_code == 403


# --- the column stays optional ----------------------------------------------


def test_a_contact_without_an_image_serialises_with_a_null_url(client, partner):
    """No upload ever done is the normal case, not a broken one."""
    response = client.get(f"/api/partners/{partner.id}")

    assert response.status_code == 200
    assert response.json()["image_url"] is None


def test_image_url_cannot_be_set_through_the_json_body(client, partner):
    """It is read-only on PartnerOut and absent from PartnerUpdate (R6)."""
    response = client.put(
        f"/api/partners/{partner.id}",
        json={"name": "Open Wood", "image_url": "/uploads/../../etc/passwd"},
    )

    assert response.status_code == 200
    assert response.json()["image_url"] is None


def test_creating_a_contact_still_needs_no_image(client):
    response = client.post(
        "/api/partners", json={"name": "No Picture Co", "partner_type": "customer"}
    )

    assert response.status_code == 201, response.text
    assert response.json()["image_url"] is None


# --- the upload directory ---------------------------------------------------


def test_upload_root_is_created_on_demand(isolated_upload_dir):
    assert not isolated_upload_dir.exists()
    assert upload_root() == isolated_upload_dir
    assert isolated_upload_dir.is_dir()


# --- removing an image ------------------------------------------------------


def test_deleting_an_image_clears_the_url_and_the_file(
    client, partner, isolated_upload_dir
):
    _post(client, partner.id, _png(), "avatar.png", "image/png")
    assert len(_stored(isolated_upload_dir)) == 1

    response = client.delete(f"/api/partners/{partner.id}/image")

    assert response.status_code == 200, response.text
    assert response.json()["image_url"] is None
    assert _stored(isolated_upload_dir) == []


def test_deleting_when_there_is_no_image_is_a_success(client, partner):
    """Idempotent: the endpoint's job is to leave the contact without a
    picture, and it already is.
    """
    response = client.delete(f"/api/partners/{partner.id}/image")

    assert response.status_code == 200
    assert response.json()["image_url"] is None


def test_deleting_an_image_twice_is_a_success(client, partner, isolated_upload_dir):
    _post(client, partner.id, _png(), "avatar.png", "image/png")

    assert client.delete(f"/api/partners/{partner.id}/image").status_code == 200
    assert client.delete(f"/api/partners/{partner.id}/image").status_code == 200
    assert _stored(isolated_upload_dir) == []


def test_an_image_can_be_uploaded_again_after_being_removed(client, partner):
    _post(client, partner.id, _png(), "one.png", "image/png")
    client.delete(f"/api/partners/{partner.id}/image")

    response = _post(client, partner.id, _png(), "two.png", "image/png")

    assert response.status_code == 200, response.text
    assert response.json()["image_url"] is not None


def test_deleting_the_image_of_a_missing_contact_is_404(client):
    response = client.delete("/api/partners/999999/image")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_contact_role_cannot_delete_an_image(contact_client, partner):
    """Same gate as the upload, and as PUT /partners/{id} (§12.2)."""
    response = contact_client.delete(f"/api/partners/{partner.id}/image")

    assert response.status_code == 403


def test_deleting_an_image_leaves_the_rest_of_the_contact_alone(
    client, partner, db: Session
):
    partner.email = "hello@openwood.example"
    partner.phone = "9876543210"
    db.flush()
    _post(client, partner.id, _png(), "avatar.png", "image/png")

    body = client.delete(f"/api/partners/{partner.id}/image").json()

    assert body["name"] == "Open Wood"
    assert body["email"] == "hello@openwood.example"
    assert body["phone"] == "9876543210"
    assert body["is_active"] is True
