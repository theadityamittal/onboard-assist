"""Tests for Bedrock LLM provider."""

from unittest.mock import MagicMock, patch

import pytest
from llm.bedrock import BedrockProvider
from llm.provider import LLMResponse


class TestBedrockProvider:
    def _mock_bedrock_response(self, text="Hello", input_tokens=10, output_tokens=5):
        """Create a mock Bedrock converse response."""
        return {
            "output": {"message": {"content": [{"text": text}]}},
            "usage": {
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
            },
        }

    @patch("llm.bedrock.boto3")
    def test_invoke_returns_llm_response(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.return_value = self._mock_bedrock_response(
            text="The refund policy is...", input_tokens=50, output_tokens=20
        )

        provider = BedrockProvider(region="us-east-1")
        result = provider.invoke(
            messages=[{"role": "user", "content": "What is the refund policy?"}],
            model_id="us.amazon.nova-micro-v1:0",
        )

        assert isinstance(result, LLMResponse)
        assert result.text == "The refund policy is..."
        assert result.input_tokens == 50
        assert result.output_tokens == 20
        assert result.model_id == "us.amazon.nova-micro-v1:0"

    @patch("llm.bedrock.boto3")
    def test_invoke_passes_max_tokens(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.return_value = self._mock_bedrock_response()

        provider = BedrockProvider(region="us-east-1")
        provider.invoke(
            messages=[{"role": "user", "content": "hi"}],
            model_id="us.amazon.nova-micro-v1:0",
            max_tokens=2000,
        )

        call_kwargs = mock_client.converse.call_args[1]
        assert call_kwargs["inferenceConfig"]["maxTokens"] == 2000

    @patch("llm.bedrock.boto3")
    def test_invoke_formats_messages_correctly(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.return_value = self._mock_bedrock_response()

        provider = BedrockProvider(region="us-east-1")
        provider.invoke(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
                {"role": "user", "content": "How are you?"},
            ],
            model_id="us.amazon.nova-micro-v1:0",
        )

        call_kwargs = mock_client.converse.call_args[1]
        assert len(call_kwargs["messages"]) == 3
        assert call_kwargs["messages"][0]["role"] == "user"

    @patch("llm.bedrock.boto3")
    def test_invoke_with_system_prompt(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.return_value = self._mock_bedrock_response()

        provider = BedrockProvider(region="us-east-1")
        provider.invoke(
            messages=[
                {"role": "system", "content": "You are an onboarding assistant."},
                {"role": "user", "content": "Hello"},
            ],
            model_id="us.amazon.nova-micro-v1:0",
        )

        call_kwargs = mock_client.converse.call_args[1]
        assert "system" in call_kwargs
        # System messages extracted, only user/assistant in messages
        assert all(m["role"] != "system" for m in call_kwargs["messages"])

    @patch("llm.bedrock.boto3")
    def test_invoke_raises_on_api_error(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.side_effect = Exception("Bedrock unavailable")

        provider = BedrockProvider(region="us-east-1")
        with pytest.raises(Exception, match="Bedrock unavailable"):
            provider.invoke(
                messages=[{"role": "user", "content": "hi"}],
                model_id="us.amazon.nova-micro-v1:0",
            )

    @patch("llm.bedrock.boto3")
    def test_client_created_once(self, mock_boto3):
        """Client is reused across invocations (not recreated)."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.return_value = self._mock_bedrock_response()

        provider = BedrockProvider(region="us-east-1")
        provider.invoke(
            messages=[{"role": "user", "content": "a"}],
            model_id="m",
        )
        provider.invoke(
            messages=[{"role": "user", "content": "b"}],
            model_id="m",
        )
        mock_boto3.client.assert_called_once()
