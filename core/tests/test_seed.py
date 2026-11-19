import pytest
from django.core.management import call_command

from accounts.models import User, UserRole
from rooms.models import Room


@pytest.mark.django_db
def test_seed_creates_one_user_per_role_and_rooms():
    call_command("seed")

    admin = User.objects.get(username="admin")
    assert admin.role == UserRole.ADMIN
    assert admin.check_password("Admin@123")
    assert User.objects.filter(role=UserRole.USER).count() == 2
    assert Room.objects.filter(is_active=False).exists()


@pytest.mark.django_db
def test_seed_is_idempotent_and_keeps_changed_passwords():
    call_command("seed")
    admin = User.objects.get(username="admin")
    admin.set_password("NovaSenha@1")
    admin.save()

    call_command("seed")

    assert User.objects.count() == 3
    assert Room.objects.count() == 4
    admin.refresh_from_db()
    assert admin.check_password("NovaSenha@1")
