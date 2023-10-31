# Generated by Django 4.2.4 on 2023-10-31 15:04

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Database",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("date_created", models.DateTimeField(auto_now_add=True)),
                ("date_modified", models.DateTimeField(auto_now=True)),
                ("deleted", models.BooleanField(default=False)),
                ("object_version", models.PositiveIntegerField(default=0)),
                ("repr_metadata", models.JSONField()),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, null=True)),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="ReplicationTarget",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("date_created", models.DateTimeField(auto_now_add=True)),
                ("date_modified", models.DateTimeField(auto_now=True)),
                ("deleted", models.BooleanField(default=False)),
                ("object_version", models.PositiveIntegerField(default=0)),
                ("repr_metadata", models.JSONField()),
                ("name", models.CharField(max_length=255)),
                ("module", models.CharField(max_length=255)),
                ("enabled", models.BooleanField(default=True)),
                ("config", models.JSONField()),
                ("primary", models.BooleanField(default=False)),
                (
                    "database",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="fractal_database.database",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ReplicationLog",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("date_created", models.DateTimeField(auto_now_add=True)),
                ("date_modified", models.DateTimeField(auto_now=True)),
                ("deleted", models.BooleanField(default=False)),
                ("payload", models.JSONField()),
                ("object_version", models.PositiveIntegerField(default=0)),
                (
                    "target",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="fractal_database.replicationtarget",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddConstraint(
            model_name="replicationtarget",
            constraint=models.UniqueConstraint(
                condition=models.Q(("primary", True)),
                fields=("database",),
                name="unique_primary_per_database",
            ),
        ),
    ]
