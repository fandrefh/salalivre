from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models


class UserRole(models.TextChoices):
    USER = "user", "Usuário"
    ADMIN = "admin", "Administrador"


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        """Superusuário (ex.: `createsuperuser`) também é admin da API.

        Sem isso, ele entraria no Django Admin mas teria role=user na API.
        """
        extra_fields.setdefault("role", UserRole.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    email = models.EmailField("e-mail", unique=True)
    role = models.CharField(max_length=10, choices=UserRole.choices, default=UserRole.USER)

    objects = UserManager()

    @property
    def is_admin_role(self) -> bool:
        return self.role == UserRole.ADMIN

    def __str__(self) -> str:
        return self.username
