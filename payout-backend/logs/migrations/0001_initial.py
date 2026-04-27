from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='LogEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('level', models.CharField(
                    choices=[('DEBUG','Debug'),('INFO','Info'),('WARNING','Warning'),('ERROR','Error'),('CRITICAL','Critical')],
                    db_index=True, max_length=10,
                )),
                ('logger_name', models.CharField(max_length=200)),
                ('message', models.TextField()),
                ('module', models.CharField(blank=True, max_length=200)),
                ('func_name', models.CharField(blank=True, max_length=200)),
                ('line_no', models.IntegerField(null=True)),
                ('context', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={'verbose_name_plural': 'log entries', 'ordering': ['-created_at']},
        ),
    ]
