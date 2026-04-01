from pipelex.pipe_run.delivery_assignment import (
    DeliveryAssignment,
    DeliveryStatus,
    StorageTarget,
    WebhookTarget,
)


class TestDeliveryAssignment:
    def test_default_delivery_assignment(self) -> None:
        assignment = DeliveryAssignment()
        assert assignment.storage is None
        assert assignment.webhooks == []

    def test_storage_only(self) -> None:
        assignment = DeliveryAssignment(storage=StorageTarget())
        assert assignment.storage is not None
        assert assignment.storage.key_prefix is None

    def test_storage_with_prefix(self) -> None:
        assignment = DeliveryAssignment(storage=StorageTarget(key_prefix="results/"))
        assert assignment.storage is not None
        assert assignment.storage.key_prefix == "results/"

    def test_webhooks_only(self) -> None:
        assignment = DeliveryAssignment(
            webhooks=[WebhookTarget(url="https://example.com/callback")],
        )
        assert len(assignment.webhooks) == 1
        assert assignment.webhooks[0].url == "https://example.com/callback"

    def test_webhook_with_headers_and_payload(self) -> None:
        webhook = WebhookTarget(
            url="https://example.com/callback",
            headers={"X-Custom": "value"},
            payload={"extra_field": "extra_value"},
        )
        assert webhook.headers == {"X-Custom": "value"}
        assert webhook.payload == {"extra_field": "extra_value"}

    def test_storage_and_webhooks(self) -> None:
        assignment = DeliveryAssignment(
            storage=StorageTarget(key_prefix="output/"),
            webhooks=[
                WebhookTarget(url="https://a.com"),
                WebhookTarget(url="https://b.com"),
            ],
        )
        assert assignment.storage is not None
        assert len(assignment.webhooks) == 2

    def test_serialization_roundtrip(self) -> None:
        assignment = DeliveryAssignment(
            storage=StorageTarget(key_prefix="test/"),
            webhooks=[WebhookTarget(url="https://example.com", payload={"key": "val"})],
        )
        dumped = assignment.model_dump()
        restored = DeliveryAssignment(**dumped)
        assert restored.storage is not None
        assert restored.storage.key_prefix == "test/"
        assert restored.webhooks[0].url == "https://example.com"
        assert restored.webhooks[0].payload == {"key": "val"}

    def test_delivery_status_values(self) -> None:
        assert DeliveryStatus.COMPLETED == "COMPLETED"
        assert DeliveryStatus.FAILED == "FAILED"
