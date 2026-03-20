"""assign_channel tool — invites user to Slack channels."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agent.tools.base import AgentTool, ToolResult

if TYPE_CHECKING:
    from slack.client import SlackClient

logger = logging.getLogger(__name__)


class AssignChannelTool(AgentTool):
    """Invite the volunteer to a Slack channel. Idempotent."""

    def __init__(self, *, slack_client: SlackClient, user_id: str) -> None:
        self._slack_client = slack_client
        self._user_id = user_id

    @property
    def name(self) -> str:
        return "assign_channel"

    @property
    def description(self) -> str:
        return "Invite the volunteer to a Slack channel."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "Slack channel ID to invite user to",
                }
            },
            "required": ["channel_id"],
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        channel_id = kwargs.get("channel_id", "")
        try:
            self._slack_client.invite_to_channel(
                channel_id=channel_id, user_id=self._user_id
            )
            return ToolResult.success(data={"channel_id": channel_id, "invited": True})
        except Exception as e:
            error_msg = str(e)
            logger.exception("assign_channel failed for %s", channel_id)
            return ToolResult.failure(error=f"Channel assignment failed: {error_msg}")
