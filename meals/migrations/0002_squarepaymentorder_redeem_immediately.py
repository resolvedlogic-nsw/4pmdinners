from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("meals", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="squarepaymentorder",
            name="redeem_immediately",
            field=models.BooleanField(default=False),
        ),
    ]
