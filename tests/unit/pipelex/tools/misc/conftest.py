import pytest
from pydantic import BaseModel, Field


class Address(BaseModel):
    street: str
    city: str
    country: str
    postal_code: str | None = None


class UserPreferences(BaseModel):
    theme: str = "dark"
    notifications: bool = True
    tags: list[str] = Field(default_factory=list)


class ComplexUser(BaseModel):
    name: str
    age: int
    email: str | None
    addresses: list[Address]
    preferences: UserPreferences
    metadata: dict[str, str | int | bool] = Field(default_factory=dict)


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
