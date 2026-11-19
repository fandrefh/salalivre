"""Dados de exemplo para avaliação: usuários de cada papel e algumas salas.

Idempotente: pode rodar várias vezes (o entrypoint roda a cada `docker compose up`)
sem duplicar registros nem sobrescrever senhas já alteradas.
Não cria reservas: elas dependem da data atual (R2) e ficariam no passado.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User, UserRole
from rooms.models import Room

USERS = [
    {
        "username": "admin",
        "email": "admin@salalivre.dev",
        "password": "Admin@123",
        "role": UserRole.ADMIN,
        "is_staff": True,
        "is_superuser": True,
    },
    {
        "username": "ana",
        "email": "ana@salalivre.dev",
        "password": "User@123",
        "role": UserRole.USER,
    },
    {
        "username": "bruno",
        "email": "bruno@salalivre.dev",
        "password": "User@123",
        "role": UserRole.USER,
    },
]

ROOMS = [
    {"name": "Sala Azul", "capacity": 8, "location": "2º andar"},
    {"name": "Sala Verde", "capacity": 4, "location": "3º andar"},
    {"name": "Auditório", "capacity": 30, "location": "Térreo"},
    # Inativa de propósito, para testar a R7.
    {"name": "Sala Laranja", "capacity": 6, "location": "1º andar", "is_active": False},
]


class Command(BaseCommand):
    help = "Cria usuários (admin e user) e salas de exemplo. Idempotente."

    @transaction.atomic
    def handle(self, *args, **options):
        for data in USERS:
            data = dict(data)
            password = data.pop("password")
            user, created = User.objects.get_or_create(username=data["username"], defaults=data)
            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
            self._report("Usuário", f"{user.username} [{user.role}]", created)

        for data in ROOMS:
            room, created = Room.objects.get_or_create(name=data["name"], defaults=data)
            self._report("Sala", room.name, created)

    def _report(self, kind, label, created):
        status = "criado" if created else "já existia"
        self.stdout.write(f"{kind}: {label} ({status})")
