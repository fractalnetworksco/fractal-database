from django.db import models


class SingletonField(models.BooleanField):
    enabled = False

    def __init__(self, *args, **kwargs):
        # Always set default to True
        if kwargs["enabled"]:
            kwargs["default"] = True
            kwargs["unique"] = True
            self.enabled = True

        super().__init__(*args, **kwargs)

    def pre_save(self, model_instance, add):
        value = super().pre_save(model_instance, add)
        if self.enabled:
            if value is False:
                raise ValueError("SingletonField value must always be True.")
        return value
