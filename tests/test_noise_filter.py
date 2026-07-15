import pytest
from unittest.mock import AsyncMock, patch

from src.core.logic.extraction import InsightExtractor


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def extractor(mock_llm):
    return InsightExtractor(mock_llm)


@pytest.mark.asyncio
async def test_short_message_rejected_without_llm_call(extractor, mock_llm):
    meaningful, reason = await extractor.is_meaningful("hello")

    assert meaningful is False
    assert reason == "Too short"
    mock_llm.generate_json.assert_not_called()


@pytest.mark.asyncio
async def test_meaningful_message_passes_threshold(extractor, mock_llm):
    mock_llm.generate_json.return_value = {
        "is_meaningful": True,
        "confidence": 0.9,
        "reason": "Contains a decision and action item",
    }

    text = "We decided to launch on Friday. @mike will fix the login bug."
    meaningful, reason = await extractor.is_meaningful(text)

    assert meaningful is True
    assert "decision" in reason.lower() or reason
    mock_llm.generate_json.assert_called_once()


@pytest.mark.asyncio
async def test_low_confidence_message_rejected(extractor, mock_llm):
    mock_llm.generate_json.return_value = {
        "is_meaningful": True,
        "confidence": 0.2,
        "reason": "Casual acknowledgement",
    }

    text = "Sounds good, thanks for the update team."
    meaningful, reason = await extractor.is_meaningful(text)

    assert meaningful is False
    assert reason == "Casual acknowledgement"


@pytest.mark.asyncio
async def test_filter_disabled_skips_llm(extractor, mock_llm):
    with patch("src.core.logic.extraction.settings.noise_filter_enabled", False):
        meaningful, reason = await extractor.is_meaningful("ok")

    assert meaningful is True
    assert reason == "Filter disabled"
    mock_llm.generate_json.assert_not_called()
