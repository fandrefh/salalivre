import pytest
from django.core.management import call_command

from accounts.models import User, UserRole


@pytest.mark.django_db
class TestUserManager:
    def test_create_user_defaults_to_user_role(self):
        user = User.objects.create_user(username="ana", email="ana@example.com", password="x")

        assert user.role == UserRole.USER
        assert not user.is_admin_role

    def test_create_superuser_is_api_admin(self):
        user = User.objects.create_superuser(
            username="root", email="root@example.com", password="x"
        )

        assert user.role == UserRole.ADMIN
        assert user.is_admin_role
        assert user.is_superuser and user.is_staff

    def test_createsuperuser_command_creates_api_admin(self, monkeypatch):
        """O comando usa create_superuser: o admin criado por ele vale também na API."""
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "Segura@2030")

        call_command(
            "createsuperuser",
            "--noinput",
            username="root",
            email="root@example.com",
            verbosity=0,
        )

        assert User.objects.get(username="root").role == UserRole.ADMIN
