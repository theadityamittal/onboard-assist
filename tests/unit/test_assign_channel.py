"""Tests for assign_channel agent tool."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent.tools.assign_channel import AssignChannelTool


class TestAssignChannelTool:
    def test_name(self):
        tool = AssignChannelTool(slack_client=MagicMock(), user_id="U123")
        assert tool.name == "assign_channel"

    def test_invites_to_channel(self):
        mock_client = MagicMock()
        mock_client.invite_to_channel.return_value = True
        tool = AssignChannelTool(slack_client=mock_client, user_id="U123")

        result = tool.execute(channel_id="C456")

        assert result.ok is True
        mock_client.invite_to_channel.assert_called_once_with(
            channel_id="C456", user_id="U123"
        )

    def test_already_in_channel(self):
        """invite_to_channel returns True when already a member — tool reports success."""
        mock_client = MagicMock()
        mock_client.invite_to_channel.return_value = True
        tool = AssignChannelTool(slack_client=mock_client, user_id="U123")

        result = tool.execute(channel_id="C456")

        assert result.ok is True

    def test_channel_not_found(self):
        from slack_sdk.errors import SlackApiError

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = {"error": "channel_not_found"}
        mock_client.invite_to_channel.side_effect = SlackApiError(
            message="channel_not_found", response=mock_resp
        )
        tool = AssignChannelTool(slack_client=mock_client, user_id="U123")

        result = tool.execute(channel_id="C_BAD")

        assert result.ok is False
        assert "channel_not_found" in result.error
