from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    USER = "user", "Usuário"
    ADMIN = "admin", "Administrador"


class User(AbstractUser):
    email = models.EmailField("e-mail", unique=True)
    role = models.CharField(max_length=10, choices=UserRole.choices, default=UserRole.USER)

    @property
    def is_admin_role(self) -> bool:
        return self.role == UserRole.ADMIN

    def __str__(self) -> str:
        return self.username
