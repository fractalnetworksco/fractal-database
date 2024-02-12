import os

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from fractal_database.models import Database


@pytest.mark.django_db()
async def test_app_config_initializes_everything_post_migrate():
    """
    Verify that post_migrate signal handlers create a project database,
    and creates a MatrixReplicationTarget for the project database.
    """
    # there should only be one database and its name should the same as the project name
    d = await Database.objects.aget()
    assert d and d.name == os.path.basename(settings.BASE_DIR)

    number_of_targets = await sync_to_async(d.replicationtarget_set.count)()
    assert number_of_targets == 2

    targets = d.replicationtarget_set.all()

    targets = await sync_to_async(list)(targets)

    # dummy and matrix targets should be in the database's targets
    assert "dummy" and "matrix" in [target.name for target in targets]
