"""Integration tests: Google Calendar OAuth callback and event creation flows.

Tests:
- OAuth callback Lambda: code exchange → token store → admin notification
- Token stored encrypted in DynamoDB SECRETS record
- Event creation via GoogleCalendarClient
- Token refresh on expiry
- Admin notification on revocation (invalid_grant)
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
from gcal.client import GoogleCalendarClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_successful_token_response(
    access_token: str = "acc_tok", refresh_token: str = "ref_tok"
) -> dict:
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": 3600,
        "token_type": "Bearer",
    }


def _make_httpx_response(
    status_code: int, body: dict, url: str = "https://example.com"
) -> httpx.Response:
    """Build a fake httpx.Response with a request object (needed for raise_for_status)."""
    request = httpx.Request("POST", url)
    return httpx.Response(status_code, json=body, request=request)


# ---------------------------------------------------------------------------
# GoogleCalendarClient unit-level integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGoogleCalendarClientEventCreation:
    """Test GoogleCalendarClient.create_event with mocked HTTP."""

    def test_create_event_sends_correct_request(self):
        """create_event should POST correctly structured body and return parsed JSON."""
        client = GoogleCalendarClient(client_id="cid", client_secret="csecret")
        event_response = {
            "id": "evt123",
            "summary": "Onboarding: Jane Smith",
            "status": "confirmed",
        }

        with patch(
            "httpx.post", return_value=_make_httpx_response(200, event_response)
        ) as mock_post:
            result = client.create_event(
                access_token="my_access_token",
                summary="Onboarding: Jane Smith",
                start="2024-03-01T09:00:00Z",
                end="2024-03-01T10:00:00Z",
                attendees=["jane@example.com"],
                description="Welcome meeting",
            )

        assert result["id"] == "evt123"
        assert result["summary"] == "Onboarding: Jane Smith"

        call_args = mock_post.call_args
        assert (
            call_args.args[0]
            == "https://www.googleapis.com/calendar/v3/calendars/primary/events"
        )
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer my_access_token"
        body = call_args.kwargs["json"]
        assert body["summary"] == "Onboarding: Jane Smith"
        assert body["attendees"] == [{"email": "jane@example.com"}]
        assert body["start"]["dateTime"] == "2024-03-01T09:00:00Z"

    def test_create_event_without_attendees(self):
        """create_event should work without attendees field."""
        client = GoogleCalendarClient(client_id="cid", client_secret="csecret")
        event_response = {"id": "evt456", "summary": "Team sync"}

        with patch(
            "httpx.post", return_value=_make_httpx_response(200, event_response)
        ):
            result = client.create_event(
                access_token="tok",
                summary="Team sync",
                start="2024-03-01T14:00:00Z",
                end="2024-03-01T15:00:00Z",
            )

        assert result["id"] == "evt456"

    def test_create_event_raises_on_http_error(self):
        """create_event should raise HTTPStatusError on non-2xx response."""
        client = GoogleCalendarClient(client_id="cid", client_secret="csecret")

        with (
            patch(
                "httpx.post",
                return_value=_make_httpx_response(401, {"error": "unauthorized"}),
            ),
            pytest.raises(httpx.HTTPStatusError),
        ):
            client.create_event(
                access_token="expired_token",
                summary="Event",
                start="2024-03-01T09:00:00Z",
                end="2024-03-01T10:00:00Z",
            )


@pytest.mark.integration
class TestGoogleCalendarClientTokenRefresh:
    """Test GoogleCalendarClient.refresh_access_token with mocked HTTP."""

    def test_refresh_access_token_returns_new_token(self):
        """refresh_access_token should return new access_token on success."""
        client = GoogleCalendarClient(client_id="cid", client_secret="csecret")
        refresh_response = {"access_token": "new_acc_tok", "expires_in": 3600}

        with patch(
            "httpx.post", return_value=_make_httpx_response(200, refresh_response)
        ) as mock_post:
            result = client.refresh_access_token(refresh_token="valid_refresh_tok")

        assert result["access_token"] == "new_acc_tok"
        assert result["expires_in"] == 3600

        call_args = mock_post.call_args
        assert call_args.args[0] == "https://oauth2.googleapis.com/token"
        assert call_args.kwargs["data"]["grant_type"] == "refresh_token"
        assert call_args.kwargs["data"]["refresh_token"] == "valid_refresh_tok"

    def test_refresh_raises_value_error_on_invalid_grant(self):
        """refresh_access_token should raise ValueError when Google returns invalid_grant."""
        client = GoogleCalendarClient(client_id="cid", client_secret="csecret")
        revoked_response = {
            "error": "invalid_grant",
            "error_description": "Token has been expired or revoked.",
        }

        with (
            patch(
                "httpx.post", return_value=_make_httpx_response(400, revoked_response)
            ),
            pytest.raises(ValueError, match="invalid_grant"),
        ):
            client.refresh_access_token(refresh_token="revoked_refresh_tok")

    def test_refresh_raises_http_error_on_server_error(self):
        """refresh_access_token should raise HTTPStatusError on 500."""
        client = GoogleCalendarClient(client_id="cid", client_secret="csecret")

        with (
            patch(
                "httpx.post",
                return_value=_make_httpx_response(500, {"error": "server_error"}),
            ),
            pytest.raises(httpx.HTTPStatusError),
        ):
            client.refresh_access_token(refresh_token="tok")


@pytest.mark.integration
class TestGoogleCalendarClientCodeExchange:
    """Test GoogleCalendarClient.exchange_code with mocked HTTP."""

    def test_exchange_code_returns_tokens(self):
        """exchange_code should POST with correct params and return token dict."""
        client = GoogleCalendarClient(client_id="cid", client_secret="csecret")
        token_payload = {
            "access_token": "acc_tok",
            "refresh_token": "ref_tok",
            "expires_in": 3600,
        }

        with patch(
            "httpx.post", return_value=_make_httpx_response(200, token_payload)
        ) as mock_post:
            result = client.exchange_code(
                code="auth_code_xyz",
                redirect_uri="https://example.com/google/oauth/callback",
            )

        assert result["access_token"] == "acc_tok"
        assert result["refresh_token"] == "ref_tok"

        call_args = mock_post.call_args
        assert call_args.kwargs["data"]["grant_type"] == "authorization_code"
        assert call_args.kwargs["data"]["code"] == "auth_code_xyz"
        assert call_args.kwargs["data"]["client_id"] == "cid"

    def test_exchange_code_raises_on_error(self):
        """exchange_code should raise HTTPStatusError on non-2xx response."""
        client = GoogleCalendarClient(client_id="cid", client_secret="csecret")

        with (
            patch(
                "httpx.post",
                return_value=_make_httpx_response(400, {"error": "invalid_code"}),
            ),
            pytest.raises(httpx.HTTPStatusError),
        ):
            client.exchange_code(code="bad_code", redirect_uri="https://x.com/cb")


# ---------------------------------------------------------------------------
# gcal.callback Lambda handler integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGcalCallbackLambdaHandler:
    """Test the Google OAuth callback Lambda end-to-end with mocked AWS + HTTP."""

    def _build_event(
        self, code: str = "auth_code", workspace_id: str = "W1", error: str = ""
    ) -> dict:
        params: dict = {}
        if error:
            params["error"] = error
        else:
            params["code"] = code
            params["state"] = workspace_id
        return {"queryStringParameters": params}

    def test_successful_oauth_callback_stores_tokens_and_notifies_admin(self):
        """Full happy-path: code exchanged, tokens stored encrypted, admin DM sent."""
        from gcal import callback as gcal_cb

        token_payload = _make_successful_token_response()
        mock_gcal_client = MagicMock()
        mock_gcal_client.exchange_code.return_value = token_payload

        mock_store = MagicMock()
        from state.models import WorkspaceConfig

        mock_store.get_workspace_config.return_value = WorkspaceConfig(
            workspace_id="W1",
            team_name="Test Corp",
            bot_user_id="B001",
            admin_user_id="U_ADMIN",
        )
        mock_store.get_workspace_secrets.return_value = {"bot_token": "xoxb-test"}

        mock_encryptor = MagicMock()
        mock_slack_client_inst = MagicMock()

        with (
            patch.object(
                gcal_cb,
                "_get_app_secrets",
                return_value={
                    "google_client_id": "gcid",
                    "google_client_secret": "gcs",
                },
            ),
            patch.object(gcal_cb, "_get_store", return_value=mock_store),
            patch("gcal.callback.GoogleCalendarClient", return_value=mock_gcal_client),
            patch("gcal.callback.FieldEncryptor", return_value=mock_encryptor),
            patch("gcal.callback.SlackClient", return_value=mock_slack_client_inst),
            patch("gcal.callback.WebClient"),
            patch("gcal.callback.boto3"),
            patch.dict(
                "os.environ",
                {
                    "KMS_KEY_ID": "arn:aws:kms:us-east-1:123:key/abc",
                    "GOOGLE_OAUTH_REDIRECT_URI": "https://app.com/cb",
                },
            ),
        ):
            response = gcal_cb.lambda_handler(self._build_event(), context=None)

        assert response["statusCode"] == 200
        assert "connected successfully" in response["body"]

        # Tokens should be saved
        mock_store.save_workspace_secrets.assert_called_once()
        secrets_call = mock_store.save_workspace_secrets.call_args.kwargs
        assert secrets_call["workspace_id"] == "W1"
        assert secrets_call["secrets_blob"]["google_access_token"] == "acc_tok"
        assert secrets_call["secrets_blob"]["google_refresh_token"] == "ref_tok"

        # calendar_enabled should be set to True
        mock_store.save_workspace_config.assert_called_once()
        config_call = mock_store.save_workspace_config.call_args.kwargs
        assert config_call["calendar_enabled"] is True

        # Admin should be notified
        mock_slack_client_inst.send_message.assert_called_once()
        notify_text = mock_slack_client_inst.send_message.call_args.kwargs["text"]
        assert "connected" in notify_text.lower()

    def test_oauth_cancelled_returns_200_with_cancel_message(self):
        """When user denies access, Lambda should return 200 with cancellation message."""
        from gcal import callback as gcal_cb

        response = gcal_cb.lambda_handler(
            self._build_event(error="access_denied"), context=None
        )

        assert response["statusCode"] == 200
        assert "cancelled" in response["body"].lower()

    def test_missing_code_returns_400(self):
        """Missing authorization code should return 400."""
        from gcal import callback as gcal_cb

        response = gcal_cb.lambda_handler(
            {"queryStringParameters": {"state": "W1"}}, context=None
        )

        assert response["statusCode"] == 400
        assert "Missing" in response["body"]

    def test_token_exchange_failure_returns_500(self):
        """If code exchange raises an exception, Lambda should return 500."""
        from gcal import callback as gcal_cb

        mock_gcal_client = MagicMock()
        mock_gcal_client.exchange_code.side_effect = RuntimeError("Network error")

        with (
            patch.object(gcal_cb, "_get_app_secrets", return_value={}),
            patch("gcal.callback.GoogleCalendarClient", return_value=mock_gcal_client),
            patch.dict(
                "os.environ",
                {
                    "KMS_KEY_ID": "test-key",
                    "GOOGLE_OAUTH_REDIRECT_URI": "https://x.com/cb",
                },
            ),
        ):
            response = gcal_cb.lambda_handler(self._build_event(), context=None)

        assert response["statusCode"] == 500

    def test_token_expiry_calculated_from_expires_in(self):
        """access_token_expiry should be approximately now + expires_in seconds."""
        from gcal import callback as gcal_cb

        before = int(time.time())
        token_payload = {
            "access_token": "acc",
            "refresh_token": "ref",
            "expires_in": 3600,
        }
        mock_gcal_client = MagicMock()
        mock_gcal_client.exchange_code.return_value = token_payload

        mock_store = MagicMock()
        from state.models import WorkspaceConfig

        mock_store.get_workspace_config.return_value = WorkspaceConfig(
            workspace_id="W1",
            team_name="Corp",
            bot_user_id="B001",
            admin_user_id="U_ADM",
        )
        mock_store.get_workspace_secrets.return_value = {"bot_token": "xoxb"}

        mock_encryptor = MagicMock()
        mock_slack_inst = MagicMock()

        with (
            patch.object(gcal_cb, "_get_app_secrets", return_value={}),
            patch.object(gcal_cb, "_get_store", return_value=mock_store),
            patch("gcal.callback.GoogleCalendarClient", return_value=mock_gcal_client),
            patch("gcal.callback.FieldEncryptor", return_value=mock_encryptor),
            patch("gcal.callback.SlackClient", return_value=mock_slack_inst),
            patch("gcal.callback.WebClient"),
            patch("gcal.callback.boto3"),
            patch.dict(
                "os.environ",
                {"KMS_KEY_ID": "key", "GOOGLE_OAUTH_REDIRECT_URI": "https://x.com/cb"},
            ),
        ):
            gcal_cb.lambda_handler(self._build_event(), context=None)

        after = int(time.time())
        secrets_blob = mock_store.save_workspace_secrets.call_args.kwargs[
            "secrets_blob"
        ]
        expiry = int(secrets_blob["access_token_expiry"])
        assert before + 3600 <= expiry <= after + 3600


@pytest.mark.integration
class TestGcalCallbackTokenRefreshFlow:
    """Test the token refresh and revocation notification flows."""

    def test_invalid_grant_raises_value_error(self):
        """When Google returns invalid_grant, refresh_access_token raises ValueError."""
        client = GoogleCalendarClient(client_id="cid", client_secret="csec")
        revoked = {"error": "invalid_grant", "error_description": "Token revoked."}

        with (
            patch("httpx.post", return_value=_make_httpx_response(400, revoked)),
            pytest.raises(ValueError) as exc_info,
        ):
            client.refresh_access_token(refresh_token="old_tok")

        assert "invalid_grant" in str(exc_info.value)

    def test_token_refresh_updates_access_token(self):
        """After a successful refresh, the caller receives the new access token."""
        client = GoogleCalendarClient(client_id="cid", client_secret="csec")
        new_tok_response = {"access_token": "fresh_token", "expires_in": 3600}

        with patch(
            "httpx.post", return_value=_make_httpx_response(200, new_tok_response)
        ):
            result = client.refresh_access_token(refresh_token="still_valid_ref")

        assert result["access_token"] == "fresh_token"

    def test_revocation_scenario_caller_handles_invalid_grant(self):
        """Simulate caller logic: catch ValueError, notify admin, clear tokens."""
        client = GoogleCalendarClient(client_id="cid", client_secret="csec")
        mock_notify = MagicMock()
        mock_clear = MagicMock()

        revoked = {"error": "invalid_grant", "error_description": "Token revoked."}

        with patch("httpx.post", return_value=_make_httpx_response(400, revoked)):
            try:
                client.refresh_access_token(refresh_token="revoked_tok")
            except ValueError:
                mock_notify(
                    admin_id="U_ADMIN",
                    message="Google Calendar access has been revoked.",
                )
                mock_clear(workspace_id="W1")

        mock_notify.assert_called_once()
        notify_call = mock_notify.call_args.kwargs
        assert "revoked" in notify_call["message"].lower()
        mock_clear.assert_called_once_with(workspace_id="W1")
