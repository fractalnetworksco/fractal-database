import uuid

from django.db import models
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.models import AutoField, UUIDField


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


BaseDatabaseOperations.integer_field_ranges["UUIDField"] = (0, 0)


class UUIDAutoField(UUIDField, AutoField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("default", uuid.uuid4)
        kwargs.setdefault("editable", False)
        super().__init__(*args, **kwargs)

    # def get_internal_type(self):
    #     return "UUIDAutoField"

    # def rel_db_type(self, connection):
    #     return UUIDField().db_type(connection=connection)
