import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("meals", "0002_squarepaymentorder_redeem_immediately"),
    ]

    operations = [
        migrations.AddField(
            model_name="qrcodenonce",
            name="order",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="redemption_nonce",
                to="meals.squarepaymentorder",
            ),
        ),
    ]
