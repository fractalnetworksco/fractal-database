import logging
from importlib import import_module
from typing import Any, Dict, List, Optional
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
from fractal_database.representations import Representation

# TODO shouldn't be importing fractal_database_matrix stuff here
# figure out a way to register representations on remote models from
# fractal_database_matrix
from fractal_database_matrix.representations import MatrixRoom

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


class DatabaseConfig(BaseModel):
    """
    Model for storing the local database configuration.
    """

    current_db = models.ForeignKey("fractal_database.Database", on_delete=models.CASCADE)
    singleton = SingletonField(unique=True, default=True)

    class Meta:
        # enforce that only one root=True RootDatabase can exist per RootDatabase
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"],
                condition=models.Q(singleton=True),
                name="unique_database_singleton",
            )
        ]


class ReplicatedModel(BaseModel):
    object_version = models.PositiveIntegerField(default=0)
    # {"<target_type": { repr_metadata }}
    # Stores a map of representation data associated with each of the model's replication targets
    # for example, a model that replicated to a MatrixReplicationTarget will store its associated
    # Matrix room_id in this property
    reprlog_set = GenericRelation("fractal_database.RepresentationLog")

    models = []

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
        try:
            database = Database.current_db()
        except DatabaseConfig.DoesNotExist as e:
            logger.error("Unable to get current database from schedule_replication")
            return
        # TODO replication targets to implement their own serialization strategy
        targets = database.get_all_replication_targets()  # type: ignore
        repr_logs = None
        for target in targets:
            # pass this replicated model instance to the target's replication method
            if created:
                repr_logs = target.create_representation_logs(self)
            else:
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

    name = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    database = models.ForeignKey("fractal_database.Database", on_delete=models.CASCADE)
    # replication events are only consumed from the primary target for a database
    primary = models.BooleanField(default=False)
    # metadata is a map of properties that are specific to the target
    metadata = models.JSONField(default=dict)

    class Meta:
        # enforce that only one primary=True ReplicationTarget can exist per Database
        # a primary replication target represents the canonical source of truth for a database
        # secondary replication targets serve as a fallback in case the primary target is unavailable
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=["database"],
                condition=models.Q(primary=True),
                name="%(app_label)s_%(class)s_unique_primary_per_database",
            )
        ]

    # TODO move these to a replicationtargetcredentials model that point back to the target
    access_token = models.CharField(max_length=255, blank=True, null=True)
    homeserver = models.CharField(max_length=255, blank=True, null=True)

    @property
    def repr_metadata_props(self) -> Dict[str, str]:
        """
        Returns the representation metadata properties for this target.
        """

        def get_nested_attr(obj, attr_path):
            """
            Recursively get nested attributes of an object.

            :param obj: The object from which attributes are fetched.
            :param attr_path: String path of nested attributes separated by dots.
            :return: Value of the nested attribute.
            """
            if "." in attr_path:
                head, rest = attr_path.split(".", 1)
                return get_nested_attr(getattr(obj, head), rest)
            else:
                return getattr(obj, attr_path)

        metadata_props = {"uuid": "uuid", "name": "database.name"}
        return {
            prop_name: get_nested_attr(self, prop) for prop_name, prop in metadata_props.items()
        }

    async def push_replication_log(self, fixture: List[Dict[str, Any]]) -> None:
        """
        Pushes a replication log to the replication target as a replicate. Uses taskiq
        to "kick" a replication task that all devices in the object's
        configured room will load.
        """
        raise NotImplementedError()

    async def replicate(self) -> None:
        """
        Get the pending replication logs and their associated representation logs.

        Apply the representation logs then push the replication logs.
        """
        transaction_logs_querysets = await self.get_repl_logs_by_txn()

        # collect all of the payloads from the replication logs into a single array
        for queryset in transaction_logs_querysets:
            fixture = []
            logger.debug("Querying for representation logs...")
            async for log in queryset:
                async for repr_log in log.repr_logs.select_related(
                    "content_type", "target_type"
                ).filter(deleted=False).order_by("date_created"):
                    try:
                        print("Calling apply for repr log: ", repr_log)
                        await repr_log.apply()
                        # after applying a representation for this target,
                        # we need to refresh ourself to get any latest metadata
                        if repr_log.content_type.model_class() == self.__class__:
                            logger.info(f"Refreshing {self} after applying representation")
                            await self.arefresh_from_db()
                        # call replicate again since apply will create new
                        # replication logs
                        return await self.replicate()
                    except Exception as e:
                        logger.error(f"Error applying representation log: {e}")
                        continue
                fixture.append(log.payload[0])

            try:
                await self.push_replication_log(fixture)
                # bulk update all of the logs in the queryset to deleted
                await queryset.aupdate(deleted=True)
            except Exception as e:
                logger.error(f"Error pushing replication log: {e}")

    async def store_metadata(self, metadata: dict) -> None:
        """
        Store the Matrix room_id on target
        """
        self.metadata["room_id"] = metadata["room_id"]
        await self.asave()

    def create_representation_logs(self, instance: "ReplicatedModel"):
        """
        Create the representation logs (tasks) for creating a Matrix space
        """
        repr_logs = []
        repr_type = RepresentationLog._get_repr_instance(self.representation_module)
        if not repr_type:
            return []

        print(f"Creating repr {repr_type} logs for instance {instance} on target {self}")
        metadata_props = instance.repr_metadata_props
        repr_logs.extend(repr_type.create_representation_logs(instance, self, metadata_props))
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

    def __str__(self) -> str:
        return f"{self.name}"

    @property
    def representation_module(self) -> str:
        """
        Returns the representation module for this target.
        """
        raise NotImplementedError()


class RepresentationLog(BaseModel):
    target = GenericForeignKey("target_type", "target_id")
    target_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_target_type",
    )
    target_id = models.CharField(max_length=255)
    method = models.CharField(max_length=255)
    instance: "ReplicatedModel" = GenericForeignKey()  # type: ignore
    object_id = models.CharField(max_length=255)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_content_type",
    )
    metadata = models.JSONField(default=dict, encoder=DjangoJSONEncoder)

    @classmethod
    def _get_repr_instance(cls, module: Optional[str] = None) -> Optional[Representation]:
        """
        Imports and returns the provided method.
        """
        if not module:
            if not hasattr(cls, "representation_module"):
                return None
            else:
                module = cls.representation_module

        repr_module, repr_class = module.rsplit(".", 1)  # type: ignore
        repr_module = import_module(repr_module)
        repr_class = getattr(repr_module, repr_class)
        return repr_class()

    async def apply(self) -> None:
        model: models.Model = self.content_type.model_class()  # type: ignore
        instance = await model.objects.aget(uuid=self.object_id)
        repr_instance = self._get_repr_instance(self.method)
        print("Calling create_representation method on: ", repr_instance)
        metadata = await repr_instance.create_representation(self, self.target_id)  # type: ignore
        if metadata:
            await instance.store_metadata(metadata)  # type: ignore
        await self.aupdate(deleted=True)


class DummyReplicationTarget(ReplicationTarget):
    async def replicate(*args, **kwargs):
        pass

    def create_representation_logs(self, instance):
        pass


class Database(ReplicatedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    devices = models.ManyToManyField("fractal_database.Device")

    def __str__(self) -> str:
        return self.name

    def primary_target(self) -> ReplicationTarget:
        """
        Returns the primary replication target for this database.
        """
        for subclass in ReplicationTarget.__subclasses__():
            target = subclass.objects.filter(primary=True)
            if target.exists():
                return target[0]

    async def aprimary_target(self) -> ReplicationTarget:
        return await sync_to_async(self.primary_target)()

    def get_all_replication_targets(self) -> List[ReplicationTarget]:
        targets = []
        # this is a hack, for some reason we arent able to set abstract = True on a subclass of an already abstract model
        for subclass in ReplicationTarget.__subclasses__():
            targets.extend(subclass.objects.filter(database=self).select_related("database"))
        return targets

    async def aget_all_replication_targets(self) -> List[ReplicationTarget]:
        targets = []
        for subclass in ReplicationTarget.__subclasses__():
            async for t in subclass.objects.filter(database=self).select_related("database"):
                targets.append(t)
        return targets

    @classmethod
    def current_db(cls) -> "Database":
        """
        Returns the current database.
        """
        return (
            DatabaseConfig.objects.select_related("current_db")
            .prefetch_related("current_db__matrixreplicationtarget_set")
            .get()
            .current_db
        )

    @classmethod
    async def acurrent_db(cls) -> "Database":
        """
        Returns the current database.
        """
        return await sync_to_async(cls.current_db)()


class AppMetadata(ReplicatedModel, MatrixRoom):
    """
    created when doing `fractal publish`
    """

    name = models.CharField(max_length=255)
    # can be used to install app with `fractal install <app_id>`
    # figure out how to enforce type safety on this field
    # this field should only be set when creating the representation for an App
    app_ids = models.JSONField(default=list)
    git_url = models.URLField()
    checksum = models.CharField(max_length=255)

    async def store_metadata(self, metadata: dict) -> None:
        self.app_ids.append(metadata["room_id"])
        await self.asave()

    def clean(self):
        """
        Custom validation for the app_ids field
        """
        if not isinstance(self.app_ids, list):
            raise ValidationError({"App.app_ids": "This field must be a list."})

    def save(self, *args, **kwargs):
        # ensure app_ids is a list
        self.clean()
        super().save(*args, **kwargs)


class App(ReplicatedModel):
    """
    created when doing `fractal install`
    """

    app_instance_id = models.CharField(max_length=255, unique=True)
    metadata = models.ForeignKey(AppMetadata, on_delete=models.DO_NOTHING)
    devices = models.ManyToManyField("fractal_database.Device")


class Device(ReplicatedModel):
    device_id = models.CharField(max_length=255, unique=True)


class Snapshot(ReplicatedModel):
    """
    Represents a snapshot of a database at a given point in time.
    Used to efficiently bootstrap a database on a new device.
    """

    url = models.URLField()
    sync_token = models.CharField(max_length=255)
