import logging
from importlib import import_module
from typing import Iterable
from uuid import uuid4

from asgiref.sync import sync_to_async
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.serializers import serialize
from django.db import models

from .fields import SingletonField

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
    repr_metadata = models.JSONField(default=dict)
    # all replicated models belong to a database
    # this property determines where the model is replicated to
    database = models.ForeignKey(
        "fractal_database.Database",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_database",
    )
    models = []

    class Meta:
        abstract = True

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        ReplicatedModel.models.append(cls)

    @classmethod
    def connect_signals(cls, **kwargs):
        from fractal_database.signals import object_post_save, set_object_database

        for model_class in cls.models:
            print('Registering replication signals for model "{}"'.format(model_class.__name__))
            # pre save signal to automatically set the database property on all ReplicatedModels
            models.signals.pre_save.connect(set_object_database, sender=model_class)
            # post save that schedules replication
            models.signals.post_save.connect(object_post_save, sender=model_class)

    def schedule_replication(self):
        print("Inside ReplicatedModel.schedule_replication()")
        # this is an "instance" database so there should only be one
        if isinstance(self, Database) or isinstance(self, RootDatabase):
            database = self
        else:
            database = self.database
        # TODO replication targets can implement their own serialization strategy
        targets = database.replicationtarget_set.all()  # type: ignore
        for target in targets:
            ReplicationLog.objects.create(payload=serialize("json", [self]), target=target)


class Database(ReplicatedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    database = models.ForeignKey(
        "fractal_database.RootDatabase",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_root_database",
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return self.name


class RootDatabase(Database):
    root = SingletonField()

    class Meta:
        # enforce that only one root=True RootDatabase can exist per RootDatabase
        constraints = [
            models.UniqueConstraint(
                fields=["root"],
                condition=models.Q(root=True),
                name="unique_root_database_singleton",
            )
        ]


class ReplicationTarget(BaseModel):
    name = models.CharField(max_length=255)
    # python module path that implements the ReplicationTarget
    module = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    database = models.ForeignKey(Database, on_delete=models.CASCADE)
    # replication events are only consumed from the primary target for a database
    primary = models.BooleanField(default=False)

    class Meta:
        # enforce that only one primary=True ReplicationTarget can exist per Database
        # a primary replication target represents the canonical source of truth for a database
        # secondary replication targets serve as a fallback in case the primary target is unavailable
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
        try:
            mod = import_module(self.target.module)  # type: ignore
        except (ModuleNotFoundError, TypeError) as err:
            logger.error(f"Could not import module {self.target.module}: {err}")
            return None

        try:
            await mod.replicate(self)
        except Exception as err:
            logger.error(f"Error replicating object to homeserver using module {mod}: {err}")
            return None

        return await self.aupdate(deleted=True)
