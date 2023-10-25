from uuid import uuid4

from asgiref.sync import sync_to_async
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models


class BaseModel(models.Model):
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid4)
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    deleted = models.BooleanField(default=False)

    class Meta:
        abstract = True

    def update(self, **kwargs) -> None:
        """Updates an instance of the model."""
        self.__class__.objects.filter(pk=self.pk).update(**kwargs)

    async def aupdate(self, **kwargs) -> None:
        """Updates an instance of the model asynchronously."""
        return await sync_to_async(self.update)(**kwargs)

    async def asave(self, *args, **kwargs) -> None:
        """Asynchronous version of save"""
        return await sync_to_async(self.save)(*args, **kwargs)


class Database(BaseModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    def __str__(self) -> str:
        return self.name


class ReplicatedModel(BaseModel):
    object_version = models.PositiveIntegerField(default=0)
    database = models.ForeignKey(Database, on_delete=models.CASCADE)

    class Meta:
        abstract = True


class ReplicationTarget(BaseModel):
    name = models.CharField(max_length=255)
    module = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    config = models.JSONField()
    database = models.ForeignKey(Database, on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f"{self.name} ({self.module})"


class ReplicationLog(BaseModel):
    payload = models.JSONField()
    object_version = models.PositiveIntegerField(default=0)
    target = models.ForeignKey(ReplicationTarget, on_delete=models.CASCADE)
