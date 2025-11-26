import pytest

from tests.unit.pipelex.tools.misc.test_data import Address, ComplexUser, UserPreferences


@pytest.fixture
def complex_user() -> ComplexUser:
    """Create a complex nested object for testing."""
    return ComplexUser(
        name="John Doe",
        age=30,
        email="john@example.com",
        addresses=[
            Address(street="123 Main St", city="Springfield", country="USA", postal_code="12345"),
            Address(street="456 Side St", city="Brooklyn", country="USA"),
        ],
        preferences=UserPreferences(theme="light", notifications=False, tags=["python", "coding"]),
        metadata={"last_login": "2024-03-20", "login_count": 42, "is_active": True},
    )
