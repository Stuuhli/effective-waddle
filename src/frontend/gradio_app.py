"""Gradio-powered frontend for interactive workflows."""
from __future__ import annotations

from textwrap import dedent
from typing import Any, Dict
import json

import gradio as gr
import httpx

from ..config import Settings

DEFAULT_BASE_URL = "http://localhost:8000"

STATUS_CSS = """
.status-box {
    padding: 0.75rem 1rem;
    border-radius: 0.75rem;
    margin-top: 0.75rem;
    font-weight: 500;
}
.status-box.info {
    background: rgba(59, 130, 246, 0.14);
    border: 1px solid rgba(59, 130, 246, 0.45);
    color: #dbeafe;
}
.status-box.success {
    background: rgba(21, 128, 61, 0.14);
    border: 1px solid rgba(21, 128, 61, 0.45);
    color: #bbf7d0;
}
.status-box.error {
    background: rgba(220, 38, 38, 0.14);
    border: 1px solid rgba(220, 38, 38, 0.45);
    color: #fecaca;
}
"""


def _normalise_base_url(base_url: str | None) -> str:
    base = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    return base or DEFAULT_BASE_URL


def _http_error_message(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        detail: str | None = None
        try:
            payload = exc.response.json()
            if isinstance(payload, dict):
                detail = payload.get("detail") or payload.get("message")
        except Exception:  # noqa: BLE001
            detail = None
        return f"HTTP {exc.response.status_code}: {detail or exc.response.reason_phrase}"
    return str(exc)


def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str] | None = None) -> Dict[str, Any]:
    with httpx.Client(timeout=10.0) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):  # Defensive, API should return an object
            raise ValueError("Unexpected response format")
        return data


def _auth_login(email: str, password: str, base_url: str) -> Dict[str, Any]:
    url = f"{base_url}/auth/login"
    return _post_json(url, {"email": email, "password": password})


def _create_ingestion_job(access_token: str, base_url: str, source: str, collection: str) -> Dict[str, Any]:
    url = f"{base_url}/ingestion/jobs"
    headers = {"Authorization": f"Bearer {access_token}"}
    return _post_json(url, {"source": source, "collection_name": collection}, headers=headers)


def _status_message(message: str, level: str = "info") -> str:
    return f"<div class='status-box {level}'>{message}</div>"

def _format_json(data: Dict[str, Any] | None) -> str:
    if not data:
        return "{}"
    try:
        return json.dumps(data, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(data)


def create_frontend(settings: Settings) -> gr.Blocks:
    """Return a configured Gradio Blocks interface."""

    title = settings.fastapi.title or "RAG Platform"

    tokens_state: gr.State = gr.State({"access": "", "refresh": "", "base_url": DEFAULT_BASE_URL})

    def login_action(
        email: str,
        password: str,
        base_url: str,
        state: Dict[str, str],
    ) -> tuple[str, Dict[str, str], Any, Any, Any, Any]:
        """Authenticate the user and persist the resulting tokens in the shared state.

        Gradio passes the current value of :class:`gr.State` as ``state``; the handler
        returns an updated tuple whose second element becomes the new state.  On
        success we enable the ingestion controls and show the API response.  On
        failure the previous state is kept and the form stays disabled.
        """
        empty_json = gr.update(value="{}", interactive=False)
        if not email or not password:
            return (
                _status_message("⚠️ Bitte E-Mail und Passwort ausfüllen.", "error"),
                state,
                gr.update(),
                gr.update(),
                gr.update(),
                empty_json,
            )
        base = _normalise_base_url(base_url or state.get("base_url"))
        try:
            result = _auth_login(email=email, password=password, base_url=base)
        except httpx.HTTPError as exc:
            message = _http_error_message(exc)
            return (
                _status_message(f"❌ Login fehlgeschlagen: {message}", "error"),
                state,
                gr.update(),
                gr.update(),
                gr.update(),
                empty_json,
            )
        except Exception as exc:  # noqa: BLE001
            return (
                _status_message(f"❌ Unerwarteter Fehler: {exc}", "error"),
                state,
                gr.update(),
                gr.update(),
                gr.update(),
                empty_json,
            )
        new_state = {
            "access": result.get("access_token", ""),
            "refresh": result.get("refresh_token", ""),
            "base_url": base,
        }
        if not new_state["access"]:
            return (
                _status_message("❌ Antwort ohne Access-Token erhalten.", "error"),
                state,
                gr.update(interactive=False),
                gr.update(interactive=False),
                gr.update(interactive=False),
                gr.update(value=_format_json(result), interactive=False),
            )
        return (
            _status_message("✅ Login erfolgreich. Du kannst nun Ingestion-Jobs erstellen.", "success"),
            new_state,
            gr.update(interactive=True),
            gr.update(interactive=True),
            gr.update(interactive=True),
            gr.update(value=_format_json(result), interactive=False),
        )

    def logout_action(state: Dict[str, str]) -> tuple[str, Dict[str, str], Any, Any, Any, Any]:
        """Reset the stored tokens and disable ingestion controls."""
        empty = {"access": "", "refresh": "", "base_url": state.get("base_url", DEFAULT_BASE_URL)}
        return (
            _status_message("ℹ️ Abgemeldet.", "info"),
            empty,
            gr.update(interactive=False, value=""),
            gr.update(interactive=False, value="default"),
            gr.update(interactive=False),
            gr.update(value="{}", interactive=False),
        )

    def ingestion_action(source: str, collection: str, state: Dict[str, str]) -> tuple[str, str]:
        """Trigger a new ingestion job for the authenticated user."""
        access = state.get("access")
        base = _normalise_base_url(state.get("base_url"))
        if not access:
            return _status_message("⚠️ Bitte zuerst einloggen.", "error"), "{}"
        if not source or not collection:
            return _status_message("⚠️ Quelle und Collection werden benötigt.", "error"), "{}"
        try:
            result = _create_ingestion_job(access, base, source, collection)
        except httpx.HTTPError as exc:
            return _status_message(f"❌ Ingestion fehlgeschlagen: {_http_error_message(exc)}", "error"), "{}"
        except Exception as exc:  # noqa: BLE001
            return _status_message(f"❌ Unerwarteter Fehler: {exc}", "error"), "{}"
        job_id = result.get("id", "unbekannt")
        status = result.get("status", "unbekannt")
        return _status_message(f"✅ Ingestion-Job {job_id} gestartet (Status: {status}).", "success"), _format_json(result)

    with gr.Blocks(title=f"{title} Console", theme="glass", css=STATUS_CSS) as demo:
        gr.Markdown(
            dedent(
                f"""
                # {title}

                Melde dich mit deinen API-Zugangsdaten an, um Ingestion-Jobs auszulösen.
                Die Eingaben werden ausschließlich über die offiziellen FastAPI-Endpunkte verarbeitet.
                """
            ).strip()
        )

        with gr.Box():
            gr.Markdown("## Login")
            base_url_input = gr.Textbox(label="API Base URL", value=DEFAULT_BASE_URL)
            email_input = gr.Textbox(label="E-Mail", placeholder="du@example.com")
            password_input = gr.Textbox(label="Passwort", type="password")
            login_button = gr.Button("Anmelden", variant="primary")
            logout_button = gr.Button("Logout")
            login_feedback = gr.HTML(_status_message("Bitte melde dich mit deinen Zugangsdaten an.", "info"))
            auth_response = gr.Textbox(
                label="Auth Response (JSON)",
                value="{}",
                lines=8,
                interactive=False,
            )

        with gr.Box():
            gr.Markdown("## Ingestion")
            source_input = gr.Textbox(
                label="Quelle",
                placeholder="s3://bucket/doc.pdf",
                interactive=False,
            )
            collection_input = gr.Textbox(
                label="Collection",
                value="default",
                interactive=False,
            )
            create_job_button = gr.Button("Ingestion-Job anlegen", variant="primary", interactive=False)
            ingestion_feedback = gr.HTML("")
            ingestion_response = gr.Textbox(
                label="Ingestion Response (JSON)",
                value="{}",
                lines=8,
                interactive=False,
            )

        login_button.click(
            login_action,
            inputs=[email_input, password_input, base_url_input, tokens_state],
            outputs=[login_feedback, tokens_state, source_input, collection_input, create_job_button, auth_response],
        )

        logout_button.click(
            logout_action,
            inputs=[tokens_state],
            outputs=[login_feedback, tokens_state, source_input, collection_input, create_job_button, auth_response],
        )

        create_job_button.click(
            ingestion_action,
            inputs=[source_input, collection_input, tokens_state],
            outputs=[ingestion_feedback, ingestion_response],
        )

    return demo


__all__ = ["create_frontend"]
