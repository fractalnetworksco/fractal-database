# Generated by Django 4.2.4 on 2023-11-04 17:29

from django.db import migrations, models
import django.db.models.deletion
import fractal_database.fields
import fractal_database_matrix.representations
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='Database',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('deleted', models.BooleanField(default=False)),
                ('object_version', models.PositiveIntegerField(default=0)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
            ],
            options={
                'abstract': False,
            },
            bases=(fractal_database_matrix.representations.Space, models.Model),
        ),
        migrations.CreateModel(
            name='RootDatabase',
            fields=[
                ('database_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='fractal_database.database')),
                ('root', fractal_database.fields.SingletonField(default=True, unique=True)),
            ],
            bases=('fractal_database.database',),
        ),
        migrations.CreateModel(
            name='RepresentationLog',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('deleted', models.BooleanField(default=False)),
                ('method', models.CharField(max_length=255)),
                ('object_id', models.CharField(max_length=255)),
                ('content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_content_type', to='contenttypes.contenttype')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ReplicationTarget',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('deleted', models.BooleanField(default=False)),
                ('name', models.CharField(max_length=255)),
                ('module', models.CharField(max_length=255)),
                ('enabled', models.BooleanField(default=True)),
                ('primary', models.BooleanField(default=False)),
                ('has_repr', models.BooleanField(default=False)),
                ('database', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fractal_database.database')),
            ],
        ),
        migrations.CreateModel(
            name='ReplicationLog',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('deleted', models.BooleanField(default=False)),
                ('payload', models.JSONField()),
                ('object_version', models.PositiveIntegerField(default=0)),
                ('object_id', models.CharField(max_length=255)),
                ('content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_content_type', to='contenttypes.contenttype')),
                ('repr_log', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='fractal_database.representationlog')),
                ('target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fractal_database.replicationtarget')),
            ],
        ),
        migrations.CreateModel(
            name='ReplicatedModelRepresentation',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('deleted', models.BooleanField(default=False)),
                ('metadata', models.JSONField(default=dict)),
                ('object_id', models.CharField(max_length=255)),
                ('content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_content_type', to='contenttypes.contenttype')),
                ('target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fractal_database.replicationtarget')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddConstraint(
            model_name='rootdatabase',
            constraint=models.UniqueConstraint(condition=models.Q(('root', True)), fields=('root',), name='unique_root_database_singleton'),
        ),
        migrations.AddConstraint(
            model_name='replicationtarget',
            constraint=models.UniqueConstraint(condition=models.Q(('primary', True)), fields=('database',), name='unique_primary_per_database'),
        ),
        migrations.AddIndex(
            model_name='replicationlog',
            index=models.Index(fields=['content_type', 'object_id'], name='fractal_dat_content_59a6e8_idx'),
        ),
        migrations.AddField(
            model_name='database',
            name='database',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_root_database', to='fractal_database.rootdatabase'),
        ),
    ]
