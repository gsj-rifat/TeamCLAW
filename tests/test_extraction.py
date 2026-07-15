import pytest
from unittest.mock import AsyncMock

from src.core.logic.extraction import InsightExtractor


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    return llm


@pytest.fixture
def extractor(mock_llm):
    return InsightExtractor(mock_llm)


@pytest.mark.asyncio
async def test_extract_maps_decisions_todos_and_facts(extractor, mock_llm):
    mock_llm.generate_json.return_value = {
        "decisions": [{"text": "Use PostgreSQL over MongoDB"}],
        "todos": [
            {
                "text": "Set up database schema",
                "assignee": "@rifat",
                "due_date": "2026-07-18",
            }
        ],
        "facts": [{"text": "Team prefers relational storage for reporting"}],
    }

    result = await extractor.extract(
        "We decided to use PostgreSQL. @rifat please set up the schema by Friday."
    )

    assert len(result.decisions) == 1
    assert result.decisions[0].text == "Use PostgreSQL over MongoDB"
    assert len(result.todos) == 1
    assert result.todos[0].assignee == "@rifat"
    assert result.todos[0].due_date == "2026-07-18"
    assert len(result.facts) == 1


@pytest.mark.asyncio
async def test_extract_returns_empty_on_llm_error(extractor, mock_llm):
    mock_llm.generate_json.side_effect = RuntimeError("rate limited")

    result = await extractor.extract("Some message with enough characters.")

    assert result.decisions == []
    assert result.todos == []
    assert result.facts == []
