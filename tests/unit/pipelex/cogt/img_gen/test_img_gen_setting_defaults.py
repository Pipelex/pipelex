from pipelex.cogt.img_gen.img_gen_setting import ImgGenSetting


class TestImgGenSettingDefaults:
    def test_is_moderated_defaults_to_none(self):
        """is_moderated must default to None ("no explicit choice"), so workers omit the moderation/safety-checker
        param and the provider's own default applies (OpenAI gpt-image: "auto", i.e. standard filtering).

        A concrete False default would explicitly request reduced moderation for every deck alias/handle
        resolution that constructs a setting without the field — a silent safety downgrade.
        """
        setting = ImgGenSetting(model="some-img-gen-model")
        assert setting.is_moderated is None

    def test_explicit_is_moderated_round_trips(self):
        """An explicit choice is preserved as-is for both values."""
        assert ImgGenSetting(model="some-img-gen-model", is_moderated=True).is_moderated is True
        assert ImgGenSetting(model="some-img-gen-model", is_moderated=False).is_moderated is False
