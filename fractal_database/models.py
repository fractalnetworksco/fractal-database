import logging
from importlib import import_module
from typing import Iterable
from uuid import uuid4

from asgiref.sync import sync_to_async
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.serializers import serialize
from django.db import models

logger = logging.getLogger("django")


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


class ReplicatedModel(BaseModel):
    object_version = models.PositiveIntegerField(default=0)
    # {"<target_type": { repr_metadata }}
    # Stores a map of representation data associated with each of the model's replication targets
    # for example, a model that replicated to a MatrixReplicationTarget will store its associated
    # Matrix room_id in this property
    repr_metadata = models.JSONField()
    # database = models.ForeignKey(
    #    "Database", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_database"
    # )

    class Meta:
        abstract = True

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        from fractal_database.signals import object_post_save

        models.signals.post_save.connect(object_post_save, sender=cls)

    def schedule_replication(self):
        targets = Database.objects.get().replicationtarget_set.all()  # type: ignore
        for target in targets:
            ReplicationLog.objects.create(payload=serialize("json", [self]), target=target)


class Database(ReplicatedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    # database = models.ForeignKey(
    #    "Database",
    #    on_delete=models.CASCADE,
    #    related_name="%(app_label)s_%(class)s_database",
    #    null=True,
    #    blank=True,
    # )

    def __str__(self) -> str:
        return self.name


class ReplicationTarget(BaseModel):
    name = models.CharField(max_length=255)
    # python module path that implements the ReplicationTarget
    module = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    database = models.ForeignKey(Database, on_delete=models.CASCADE)
    primary = models.BooleanField(default=False)

    class Meta:
        # enforce that only one primary=True ReplicationTarget can exist per Database
        constraints = [
            models.UniqueConstraint(
                fields=["database"],
                condition=models.Q(primary=True),
                name="unique_primary_per_database",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.module})"


class ReplicationLog(BaseModel):
    payload = models.JSONField()
    object_version = models.PositiveIntegerField(default=0)
    target = models.ForeignKey(ReplicationTarget, on_delete=models.CASCADE)

    async def replicate(self):
        """
        Applies the ReplicationLog for all of the enabled Replication Targets.
        """
        print(f"Replicating {self.payload} to homeserver")
        targets: Iterable[ReplicationTarget] = ReplicationTarget.objects.filter(enabled=True)

        # FIXME: Each replicationtarget should have its own instance of the ReplicationLog object.
        # this is so we can have per target replication tracking. Right now, if any target fails,
        # if we call replicate on the same ReplicationLog object, it will replicate to ALL targets again,
        # even if some of them succeeded previously (causes duplicates).
        async for target in targets:
            try:
                mod = import_module(target.module)
            except (ModuleNotFoundError, TypeError) as err:
                logger.error(f"Could not import module {target.module}: {err}")
                return None

            try:
                await mod.replicate(self)
            except Exception as err:
                logger.error(f"Error replicating object to homeserver using module {mod}: {err}")
                return None

        return await self.aupdate(deleted=True)
