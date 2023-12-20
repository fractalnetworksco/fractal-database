from django.db import models


class SingletonField(models.BooleanField):
    """
    A Django model field that can only be set to True. This is useful for creating singletons,
    ie models that should only have one instance in the database.
    """

    def pre_save(self, model_instance, add):
        value = super().pre_save(model_instance, add)
        if value is False:
            raise ValueError("SingletonField value must always be True.")
        return value
