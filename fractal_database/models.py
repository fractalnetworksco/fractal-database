import logging
from importlib import import_module
from typing import Any, Callable, List
from uuid import uuid4

from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers import serialize
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.db.models.manager import BaseManager
from fractal_database.exceptions import StaleObjectException
from fractal_database_matrix.representations import MatrixSpace

from .fields import SingletonField
from .signals import defer_replication

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
    reprlog_set = GenericRelation("fractal_database.RepresentationLog")
    # all replicated models belong to a database
    # this property determines where the model is replicated to
    database = models.ForeignKey(
        "fractal_database.Database",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_database",
    )
    repr = GenericRelation("fractal_database.ReplicatedModelRepresentation")

    # track subclasses
    models = []
    repr_models = []

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        Gaurds on the object version to ensure that the object version is incremented monotonically
        """
        with transaction.atomic():
            try:
                current = type(self).objects.select_for_update().get(pk=self.pk)
                if self.object_version + 1 <= current.object_version:
                    raise StaleObjectException()
            except ObjectDoesNotExist:
                pass
            super().save(*args, **kwargs)  # Call the "real" save() method.

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # keep track of subclasses so we can register signals for them in App.ready
        ReplicatedModel.models.append(cls)

    @classmethod
    def connect_signals(cls, **kwargs):
        from fractal_database.signals import object_post_save, set_object_database

        for model_class in cls.models:
            logger.info(
                'Registering replication signals for model "{}"'.format(model_class.__name__)
            )
            # pre save signal to automatically set the database property on all ReplicatedModels
            models.signals.pre_save.connect(set_object_database, sender=model_class)
            # post save that schedules replication
            models.signals.post_save.connect(object_post_save, sender=model_class)

    def schedule_replication(self, created: bool = False):
        # must be in a txn for defer_replication to work properly
        if not transaction.get_connection().in_atomic_block:
            with transaction.atomic():
                return self.schedule_replication(created=created)

        print("Inside ReplicatedModel.schedule_replication()")
        if isinstance(self, Database) or isinstance(self, RootDatabase):
            database = self
        else:
            database = self.database

        # TODO replication targets to implement their own serialization strategy
        targets = database.replicationtarget_set.all()  # type: ignore
        repr_logs = None
        for parent_target in targets:
            target = parent_target.target
            # pass this replicated model instance to the target's replication method
            if created:
                # FIXME: this method name is really confusing
                repr_logs = target.create_representation_logs(self)
            else:
                # reper_log = target.create_update_representation_logs(self)
                print("Not creating repr for object: ", self)

            print(f"Creating replication log for target {target}")
            repl_log = ReplicationLog.objects.create(
                payload=serialize("python", [self]),
                target=target,
                instance=self,
                txn_id=transaction.savepoint().split("_")[0],
            )

            # dummy targets return none
            if repr_logs:
                print("Adding repr logs to repl log")
                repl_log.repr_logs.add(*repr_logs)

            defer_replication(target)


class ReplicatedModelRepresentation(BaseModel):
    metadata = models.JSONField(default=dict)
    target = models.ForeignKey("fractal_database.ReplicationTarget", on_delete=models.CASCADE)
    instance = GenericForeignKey()
    object_id = models.CharField(max_length=255)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="%(app_label)s_%(class)s_content_type",
    )

    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]


class Database(ReplicatedModel, MatrixSpace):
    # TODO shouldn't be importing fractal_database_matrix stuff here
    # figure out a way to register representations on remote models from
    # fractal_database_matrix
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


class RootDatabase(Database, MatrixSpace):
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


class ReplicationLog(BaseModel):
    payload = models.JSONField(encoder=DjangoJSONEncoder)
    object_version = models.PositiveIntegerField(default=0)
    target = models.ForeignKey("fractal_database.ReplicationTarget", on_delete=models.CASCADE)
    instance = GenericForeignKey()
    object_id = models.CharField(max_length=255)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="%(app_label)s_%(class)s_content_type",
    )
    repr_logs = models.ManyToManyField("fractal_database.RepresentationLog")
    txn_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]


class ReplicationTarget(BaseModel):
    name = models.CharField(max_length=255, unique=True)
    enabled = models.BooleanField(default=True)
    database = models.ForeignKey(Database, on_delete=models.CASCADE)
    # replication events are only consumed from the primary target for a database
    primary = models.BooleanField(default=False)
    # This field will store the content type of the subclass
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    # This is the generic foreign key to the subclass
    content_object = GenericForeignKey("content_type", "uuid")

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

    def create_representation_logs(self, instance):
        """
        Create the representation logs (tasks) for creating a Matrix space
        """
        if not hasattr(instance, "get_repr_types"):
            return []

        repr_logs = []
        repr_types = instance.get_repr_types()
        for repr_type in repr_types:
            print(f"Creating repr {repr_types} logs for instance {instance} on target {self}")
            metadata_props = repr_type.get_repr_metadata_properties()
            repr_logs.append(
                *repr_type.create_representation_logs(instance, self, metadata_props)
            )

        return repr_logs

    def save(self, *args, **kwargs):
        if not self.pk:  # If this is a new object (no primary key yet)
            # Set the content_type to the current model
            self.content_type = ContentType.objects.get_for_model(self.__class__)
        super().save(*args, **kwargs)

    async def get_repl_logs_by_txn(self) -> List[BaseManager[ReplicationLog]]:
        txn_ids = (
            ReplicationLog.objects.filter(target=self, deleted=False)
            .values_list("txn_id", flat=True)
            .distinct()
        )
        return [
            ReplicationLog.objects.filter(txn_id=txn_id, deleted=False, target=self).order_by(
                "date_created"
            )
            async for txn_id in txn_ids
        ]

    @property
    def target(self):
        if self.content_type and hasattr(self, self.content_type.model):
            # We can now safely get the child object by using the content_type field
            return getattr(self, self.content_type.model)
        return None

    async def replicate(self):
        raise NotImplementedError()

    def __str__(self) -> str:
        return f"{self.name}"


class RepresentationLog(BaseModel):
    target = models.ForeignKey(ReplicationTarget, on_delete=models.CASCADE)
    method = models.CharField(max_length=255)
    instance = GenericForeignKey()
    object_id = models.CharField(max_length=255)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="%(app_label)s_%(class)s_content_type",
    )
    metadata = models.JSONField(default=dict, encoder=DjangoJSONEncoder)

    def _import_method(self, method: str) -> Callable:
        """
        Imports and returns the provided method.
        """
        repr_class, repr_method = method.split(":")
        repr_module, repr_class = repr_class.rsplit(".", 1)
        repr_module = import_module(repr_module)
        repr_class = getattr(repr_module, repr_class)
        return getattr(repr_class, repr_method)

    async def apply(self, target):
        repr_method = self._import_method(self.method)
        print("Calling ReplicationLog's repr_log method: ", repr_method)
        await repr_method(self, target)
        await self.aupdate(deleted=True)


class DummyReplicationTarget(ReplicationTarget):
    async def replicate(*args, **kwargs):
        pass

    def create_representation_logs(self, instance):
        pass


class Snapshot(ReplicatedModel):
    """
    Represents a snapshot of a database at a given point in time.
    Used to efficiently bootstrap a database on a new device.
    """

    url = models.URLField()
    sync_token = models.CharField(max_length=255)
