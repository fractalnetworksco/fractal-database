import pytest
from django.db.utils import IntegrityError
from fractal_database.models import Database, ReplicationTarget


@pytest.mark.django_db
async def test_cant_have_two_primary_databases(database: Database):
    """
    FIXME: Figure out how to disable the post migration signal handlers so that
           we can create RootDatabases vs Instance Databases
    """
    with pytest.raises(IntegrityError):
        t1 = await ReplicationTarget.objects.acreate(
            name="target1", database=database, primary=True, content_type_id=1
        )
        t2 = await ReplicationTarget.objects.acreate(
            name="target2", database=database, primary=True, content_type_id=1
        )
