"""Never let tests modify the developer's persistent database or use Gemini."""
import pytest
from carbon_coach.api import app
from carbon_coach.storage import MemoryRepository

@pytest.fixture(autouse=True)
def isolated_application_store():
    previous = app.state.repository
    app.state.repository = MemoryRepository()
    try:
        yield
    finally:
        app.state.repository = previous
