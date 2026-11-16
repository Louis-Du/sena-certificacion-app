"""El aviso de actualización aparece con las notas del release."""


def test_update_modal_shows_release_notes_and_can_be_dismissed(page, app_url):
    release = {
        "current_version": "0.3.0",
        "latest_version": "0.4.0",
        "update_available": True,
        "notes": "- feat: autoupdate\n- fix: descarga con diálogo nativo",
        "notes_items": [
            "feat: autoupdate",
            "fix: descarga con diálogo nativo",
        ],
        "setup_url": (
            "https://github.com/Louis-Du/sena-certificacion-app/releases/download/"
            "v0.4.0/SENACertificacion-Setup-0.4.0.exe"
        ),
        "sha256": "a" * 64,
        "published_at": "2026-11-17T12:00:00Z",
        "release_url": (
            "https://github.com/Louis-Du/sena-certificacion-app/releases/tag/v0.4.0"
        ),
        "source": "version.json",
        "checked_at": "2026-11-17T12:00:00Z",
        "error": None,
        "cached": False,
        "dismissed_version": "",
        "can_self_update": True,
    }

    page.route(
        "**/api/updates/check*",
        lambda route: route.fulfill(status=200, json=release),
    )
    page.route(
        "**/api/updates/dismiss",
        lambda route: route.fulfill(status=200, json={"dismissed": True, "version": "0.4.0"}),
    )

    page.goto(app_url)
    page.wait_for_selector("#update-modal.is-open", timeout=8000)

    assert page.locator("#update-latest-version").text_content() == "v0.4.0"
    notes = page.locator("#update-notes").text_content()
    assert "feat: autoupdate" in notes
    assert "fix: descarga con diálogo nativo" in notes
    assert page.locator("#update-apply").text_content() == "Actualizar ahora"

    page.click("#update-modal-later")
    page.wait_for_function(
        "() => !document.getElementById('update-modal').classList.contains('is-open')"
    )
