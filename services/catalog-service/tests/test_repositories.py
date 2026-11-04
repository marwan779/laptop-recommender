import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.laptop import LaptopConfiguration
from app.repositories.laptop_repository import LaptopRepository


@pytest.mark.asyncio
async def test_laptop_repository_get_by_canonical_id():
    mock_session = AsyncMock()
    mock_result = MagicMock()

    dummy_config = LaptopConfiguration(
        id=uuid.uuid4(),
        canonical_id="test_canonical_id",
        mpn="TEST-MPN-123",
        title="Test Laptop",
    )

    mock_result.scalar_one_or_none.return_value = dummy_config
    mock_session.execute.return_value = mock_result

    repo = LaptopRepository(mock_session)
    result = await repo.get_by_canonical_id("test_canonical_id")

    assert result is not None
    assert result.canonical_id == "test_canonical_id"
    assert result.title == "Test Laptop"
    mock_session.execute.assert_called_once()
