import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.laptop import LaptopConfiguration
from app.repositories.laptop_repository import LaptopRepository


@pytest.mark.asyncio
async def test_laptop_repository_get_by_identity_hash():
    mock_session = AsyncMock()
    mock_result = MagicMock()

    dummy_config = LaptopConfiguration(
        id=uuid.uuid4(),
        laptop_model_id=uuid.uuid4(),
        identity_hash="test_identity_hash",
        title="Test Laptop",
    )

    mock_result.scalar_one_or_none.return_value = dummy_config
    mock_session.execute.return_value = mock_result

    repo = LaptopRepository(mock_session)
    result = await repo.get_by_identity_hash("test_identity_hash")

    assert result is not None
    assert result.identity_hash == "test_identity_hash"
    assert result.title == "Test Laptop"
    mock_session.execute.assert_called_once()

