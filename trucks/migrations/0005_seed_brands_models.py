from django.db import migrations

BRANDS_AND_MODELS = {
    'Mercedes-Benz': [
        'Actros 2651', 'Actros 2546', 'Actros 2548', 'Actros 2553',
        'Axor 2544', 'Axor 2041', 'Axor 1933',
        'Atego 1719', 'Atego 2426', 'Atego 1726',
        'Accelo 815', 'Accelo 1016',
    ],
    'Volvo': [
        'FH 540', 'FH 460', 'FH 420', 'FH 500',
        'FM 370', 'FM 330', 'FM 460',
        'FMX 500', 'FMX 460',
        'VM 270', 'VM 330',
    ],
    'Scania': [
        'R 540', 'R 500', 'R 450', 'R 410',
        'S 500', 'S 540',
        'G 410', 'G 360',
        'P 360', 'P 310', 'P 250',
    ],
    'Iveco': [
        'Stralis 600S', 'Stralis 480S', 'Stralis 440S',
        'Trakker 720T', 'Trakker 450T',
        'Daily 70-170', 'Daily 55-170',
        'Vertis 130V18',
    ],
    'Volkswagen': [
        'Constellation 25.460', 'Constellation 19.360', 'Constellation 17.280',
        'Delivery 11.180', 'Delivery 9.170',
        'Meteor 29.520', 'Meteor 25.420',
    ],
    'Ford': [
        'Cargo 2429', 'Cargo 1933', 'Cargo 1723',
        'Cargo 816', 'Cargo 1119',
        'F-MAX 500',
    ],
    'DAF': [
        'XF 530', 'XF 480', 'XF 450',
        'CF 370', 'CF 330',
        'LF 230',
    ],
    'MAN': [
        'TGX 29.530', 'TGX 28.480', 'TGX 24.480',
        'TGS 26.360', 'TGS 19.360',
        'TGL 11.190', 'TGL 8.190',
    ],
    'Renault': [
        'T 520', 'T 480', 'T 460',
        'C 430', 'C 380',
        'K 430', 'K 380',
        'D 250', 'D 180',
    ],
    'Hyundai': [
        'Xcient', 'HD 270', 'HD 120',
    ],
}


def populate(apps, schema_editor):
    TruckBrand = apps.get_model('trucks', 'TruckBrand')
    TruckModel = apps.get_model('trucks', 'TruckModel')
    for brand_name, models in BRANDS_AND_MODELS.items():
        brand, _ = TruckBrand.objects.get_or_create(name=brand_name)
        for model_name in models:
            TruckModel.objects.get_or_create(brand=brand, name=model_name)


class Migration(migrations.Migration):
    dependencies = [
        ('trucks', '0004_truck_photos'),
    ]

    operations = [
        migrations.RunPython(populate, migrations.RunPython.noop),
    ]
