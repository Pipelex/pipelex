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
