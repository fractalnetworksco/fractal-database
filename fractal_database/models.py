import logging
from importlib import import_module
from typing import Callable, List, Optional
from uuid import uuid4

from asgiref.sync import sync_to_async
from django.apps import apps
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.serializers import serialize
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.db.models.manager import BaseManager
from fractal_database.exceptions import StaleObjectException

# TODO shouldn't be importing fractal_database_matrix stuff here
# figure out a way to register representations on remote models from
# fractal_database_matrix
from fractal_database_matrix.representations import MatrixRoom, MatrixSpace

from .fields import SingletonField
from .signals import defer_replication

logger = logging.getLogger(__name__)
# to get console output from logger:
# logger = logging.getLogger("django")


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
        from fractal_database.signals import object_post_save  # , set_object_database

        for model_class in cls.models:
            logger.info(
                'Registering replication signals for model "{}"'.format(model_class.__name__)
            )
            # pre save signal to automatically set the database property on all ReplicatedModels
            # models.signals.pre_save.connect(set_object_database, sender=model_class)
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
            try:
                root_database_model = apps.get_model("fractal_database", "RootDatabase")
                database = root_database_model.objects.get()
            except RootDatabase.DoesNotExist:
                app_database_model = apps.get_model("fractal_database", "AppInstance")
                database = app_database_model.objects.get()

        # TODO replication targets to implement their own serialization strategy
        targets = database.get_all_replication_targets()
        repr_logs = None
        for target in targets:
            # target = parent_target.target
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


class ReplicationLog(BaseModel):
    payload = models.JSONField(encoder=DjangoJSONEncoder)
    object_version = models.PositiveIntegerField(default=0)
    target = GenericForeignKey("target_type", "target_id")
    target_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="%(app_label)s_%(class)s_target_type",
    )
    target_id = models.CharField(max_length=255)
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


class ReplicationTarget(ReplicatedModel):
    """
    Why replicate ReplicationTargets?

    In our original design ReplicationTargets were not ReplicatedModels
    we decided to make them ReplicatedModels because we thought it would make things easier for end users.

    For example, in a private context you may want to configure all of your devices to start replicating to
    another target.

    In a public context users may want to contribute to the resilience of a dataset by publishing their
    homeserver as a replication target.

    In general, because ReplicationTargets store the necessary context needed to sync and replicate data
    from/to remote datastores, replicating them allows new devices to contribute to the replication
    swarm.

    In the future, perhaps replicating the same dataset to different Matrix rooms (as oppose to relying
    solely on Matrix's federation) would lend itself to a more scalable decentralized replication model.
    """

    name = models.CharField(max_length=255, unique=True)
    enabled = models.BooleanField(default=True)
    database = GenericForeignKey()
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="%(app_label)s_%(class)s_content_type",
    )
    object_id = models.CharField(max_length=255)
    # replication events are only consumed from the primary target for a database
    primary = models.BooleanField(default=False)
    # This field will store the content type of the subclass
    # content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    # # This is the generic foreign key to the subclass
    # content_object = GenericForeignKey("content_type", "uuid")
    # metadata is a map of properties that are specific to the target
    metadata = models.JSONField(default=dict)

    class Meta:
        # enforce that only one primary=True ReplicationTarget can exist per Database
        # a primary replication target represents the canonical source of truth for a database
        # secondary replication targets serve as a fallback in case the primary target is unavailable
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=["content_type"],
                condition=models.Q(primary=True),
                name="%(app_label)s_%(class)s_unique_primary_per_database",
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
            ReplicationLog.objects.filter(target_id=self.uuid, deleted=False)
            .values_list("txn_id", flat=True)
            .distinct()
        )
        return [
            ReplicationLog.objects.filter(
                txn_id=txn_id, deleted=False, target_id=self.uuid
            ).order_by("date_created")
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
    target = GenericForeignKey("target_type", "target_id")
    target_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="%(app_label)s_%(class)s_target_type",
    )
    target_id = models.CharField(max_length=255)
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

    async def apply(self) -> None:
        create_representation = self._import_method(self.method)
        print("Calling ReplicationLog's create_representation method: ", create_representation)
        metadata = await create_representation(self, self.target_id)  # type: ignore
        model = self.content_type.model_class()
        instance = await model.objects.aget(uuid=self.object_id)
        await instance.store_metadata(metadata)
        await self.aupdate(deleted=True)


class DummyReplicationTarget(ReplicationTarget):
    async def replicate(*args, **kwargs):
        pass

    def create_representation_logs(self, instance):
        pass


class Database(ReplicatedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return self.name

    def get_all_replication_targets(self) -> List[Optional[ReplicationTarget]]:
        targets = []
        for subclass in ReplicationTarget.__subclasses__():
            targets.extend(
                subclass.objects.filter(object_id=self.uuid).select_related("content_type")
            )
        return targets

    async def aget_all_replication_targets(self) -> List[Optional[ReplicationTarget]]:
        targets = []
        for subclass in ReplicationTarget.__subclasses__():
            async for t in subclass.objects.filter(object_id=self.uuid).select_related(
                "content_type"
            ):
                targets.append(t)
        return targets

    async def store_metadata(self, metadata: dict) -> None:
        """
        Store the Matrix room_id on all
        """
        targets = await self.aget_all_replication_targets()
        for target in targets:
            target.metadata["room_id"] = metadata["room_id"]
            await target.asave()


class App(ReplicatedModel, MatrixRoom):
    """
    created when doing `fractal publish`
    """

    name = models.CharField(max_length=255)
    # can be used to install app with `fractal install <app_id>`
    # figure out how to enforce type safety on this field
    # this field should only be set when creating the representation for an App
    app_id = models.JSONField(default=list)
    git_url = models.URLField()
    checksum = models.CharField(max_length=255)

    async def store_metadata(self, metadata: dict) -> None:
        self.app_id.append(metadata["room_id"])
        await self.asave()

    def clean(self):
        # Custom validation to ensure my_field is a list
        if not isinstance(self.app_id, list):
            raise ValidationError({"App.app_id": "This field must be a list."})

    def save(self, *args, **kwargs):
        # Call the custom validation
        self.clean()
        # Call the original save method
        super().save(*args, **kwargs)


class AppInstance(Database, MatrixSpace):
    """
    created when doing `fractal install`
    """

    app_instance_id = models.CharField(max_length=255, unique=True)
    app = models.ForeignKey(App, on_delete=models.DO_NOTHING)
    devices = models.ManyToManyField("fractal_database.Device")


class Device(ReplicatedModel):
    device_id = models.CharField(max_length=255, unique=True)


class RootDatabase(Database, MatrixSpace):
    """
    created when doing `fractal init`
    """

    root = SingletonField()
    devices = models.ManyToManyField("fractal_database.Device")

    class Meta:
        # enforce that only one root=True RootDatabase can exist per RootDatabase
        constraints = [
            models.UniqueConstraint(
                fields=["root"],
                condition=models.Q(root=True),
                name="unique_root_database_singleton",
            )
        ]


class Snapshot(ReplicatedModel):
    """
    Represents a snapshot of a database at a given point in time.
    Used to efficiently bootstrap a database on a new device.
    """

    url = models.URLField()
    sync_token = models.CharField(max_length=255)
