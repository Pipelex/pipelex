from pipelex.runtime_bridge.delivery_mode import DeliveryMode


class TestDeliveryMode:
    def test_string_values_are_stable(self) -> None:
        """The closed delivery enum's wire strings are stable (it is a StrEnum, used as its own string)."""
        assert DeliveryMode.BLOCKING == "blocking"
        assert DeliveryMode.FIRE_AND_FORGET == "fire_and_forget"

    def test_members_are_exhaustive(self) -> None:
        """The axis is closed at exactly two members — adding a third (e.g. STREAMING) is core's call, never a plugin's."""
        assert set(DeliveryMode) == {DeliveryMode.BLOCKING, DeliveryMode.FIRE_AND_FORGET}
