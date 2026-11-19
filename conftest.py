import pytest
from rest_framework.test import APIClient

from accounts.models import User, UserRole
from rooms.models import Room


@pytest.fixture
def user(db):
    return User.objects.create_user(username="ana", email="ana@example.com", password="Senha@123")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username="bruno", email="bruno@example.com", password="Senha@123"
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="admin", email="admin@example.com", password="Senha@123", role=UserRole.ADMIN
    )


@pytest.fixture
def room(db):
    return Room.objects.create(name="Sala Azul", capacity=8, location="2º andar")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client
