import json

import pytest
from asgiref.sync import sync_to_async
from fractal_database.models import Database, ReplicationLog
from fractal_database_matrix.models import MatrixReplicationTarget
from nio import AsyncClient, RoomGetStateEventError, SyncError
from taskiq_matrix.filters import create_filter

pytest.skip(allow_module_level=True)

@pytest.mark.django_db
async def test_project_database_represented_in_matrix(matrix_client: AsyncClient):
    """
    Project database should have a representation in Matrix
    """
    
    # post migrate signal should create a database for us
    proj_database = await Database.objects.aget()
    matrix_target = await proj_database.replicationtarget_set.aget(name="matrix")  # type: ignore

    # get room id from representation
    room_id = matrix_target.metadata["room_id"]
    assert room_id

    # attempt to get the room name from the room state
    res = await matrix_client.room_get_state_event(room_id, "m.room.create")
    assert not isinstance(res, RoomGetStateEventError)

    # should be a space
    assert res.content["type"] == "m.space"

    res = await matrix_client.room_get_state_event(room_id, "m.room.name")
    assert not isinstance(res, RoomGetStateEventError)

    # room name should be the same as the database name
    assert res.content["name"] == proj_database.name


@pytest.mark.django_db
async def test_project_database_replicated_to_matrix(matrix_client: AsyncClient):
    """
    Project database object fixture should be replicated into its Matrix room id
    """
    proj_database = await Database.objects.aget()
    matrix_target = await proj_database.replicationtarget_set.aget(name="matrix")  # type: ignore

    # get room id from representation
    room_id = matrix_target.metadata["room_id"]
    assert room_id

    # filter for replication events in the database's room
    sync_filter = create_filter(room_id, types=[MatrixRootReplicationTarget.event_type])
    res = await matrix_client.sync(sync_filter=sync_filter)
    assert not isinstance(res, SyncError)

    # there should be one replication event in the room
    events = res.rooms.join[room_id].timeline.events
    assert len(events) == 1
    fixture = res.rooms.join[room_id].timeline.events[0].source["content"]["body"]

    # fetch replicationlog in order to verify fixture payload that is the the room is the same
    repl_logs = ReplicationLog.objects.filter(object_id=proj_database.uuid, target=matrix_target)
    repl_logs = await sync_to_async(list)(repl_logs)
    payload = repl_logs[0].payload

    # should be serialized as a string
    assert isinstance(fixture, str)

    # load the fixture and verify that it is the same as the payload
    assert json.loads(fixture) == payload

    # trigger more replication events
    # FIXME: Figure out how to use a transaction for this. `with transaction.atomic()` doesn't work in async
    #        Doing so will allow us to verify that multiple saves in a transaction only send a single event
    await proj_database.asave()
    await proj_database.asave()

    # there should be two replication events in the room
    res = await matrix_client.sync(sync_filter=sync_filter)
    assert not isinstance(res, SyncError)

    events = res.rooms.join[room_id].timeline.events
    assert len(events) == 2


@pytest.mark.django_db
async def only_one_database_in_instance_database():
    """
    A database should already exist since the post_migrate signal handler
    creates one, so attemping to create another database should raise an exception.
    """
    with pytest.raises(Exception):
        await Database.objects.acreate(name="test_database")
