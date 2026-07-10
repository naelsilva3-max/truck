import io
from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image

from accounts.models import UserProfile
from trucks.models import Truck, TruckBrand, TruckModel, TruckPhoto


def make_user():
    user = User.objects.create_user(username='admin', password='pass')
    user.profile.role = UserProfile.MASTER
    user.profile.save()
    return user


def make_truck_model(brand_name='Volvo', model_name='FH'):
    brand, _ = TruckBrand.objects.get_or_create(name=brand_name)
    truck_model, _ = TruckModel.objects.get_or_create(brand=brand, name=model_name)
    return truck_model


def make_truck(**kw):
    defaults = dict(
        license_plate='ABC1D23', truck_model=make_truck_model(),
        color='branca', chassis='12345678901234567', year=2020,
    )
    defaults.update(kw)
    return Truck.objects.create(**defaults)


def _make_valid_jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), color='white').save(buffer, format='JPEG')
    return buffer.getvalue()


def _truck_form_data(truck_model, **overrides):
    data = {
        'license_plate': 'XYZ9A87', 'truck_model': truck_model.pk,
        'color': 'azul', 'chassis': '98765432109876543', 'year': '2021',
        'is_active': 'on',
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestTruckPhotoUploadValidation:
    def test_rejects_non_image_photo_on_create(self):
        user = make_user()
        truck_model = make_truck_model()
        client = Client()
        client.force_login(user)
        fake_photo = SimpleUploadedFile('malicious.jpg', b'not-an-image-at-all', content_type='image/jpeg')

        response = client.post(
            reverse('trucks:create'),
            {**_truck_form_data(truck_model), 'photos': [fake_photo]},
        )

        assert response.status_code == 200
        assert not Truck.objects.filter(license_plate='XYZ9A87').exists()
        assert TruckPhoto.objects.count() == 0

    def test_accepts_valid_image_photo_on_create(self):
        user = make_user()
        truck_model = make_truck_model()
        client = Client()
        client.force_login(user)
        photo = SimpleUploadedFile('truck.jpg', _make_valid_jpeg_bytes(), content_type='image/jpeg')

        response = client.post(
            reverse('trucks:create'),
            {**_truck_form_data(truck_model), 'photos': [photo]},
        )

        assert response.status_code == 302
        truck = Truck.objects.get(license_plate='XYZ9A87')
        assert truck.photos.count() == 1

    def test_rejects_non_image_photo_on_update_without_saving_truck_changes(self):
        user = make_user()
        truck = make_truck()
        client = Client()
        client.force_login(user)
        fake_photo = SimpleUploadedFile('malicious.jpg', b'not-an-image-at-all', content_type='image/jpeg')

        response = client.post(
            reverse('trucks:update', kwargs={'pk': truck.pk}),
            {**_truck_form_data(truck.truck_model, license_plate=truck.license_plate, chassis=truck.chassis), 'photos': [fake_photo]},
        )

        assert response.status_code == 200
        assert truck.photos.count() == 0
