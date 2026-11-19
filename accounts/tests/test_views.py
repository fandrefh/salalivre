"""Testes dos endpoints de autenticação: cadastro, login (JWT), refresh e rate limit."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from accounts.models import User, UserRole

REGISTER_URL = "/api/auth/register"
LOGIN_URL = "/api/auth/login"
REFRESH_URL = "/api/auth/refresh"

PASSWORD = "Segura@2030"


def error_of(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """O contador do rate limit fica no cache; sem limpar, ele vaza de um teste para outro."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def carla(db):
    return User.objects.create_user(username="carla", email="carla@example.com", password=PASSWORD)


def login(client, username="carla", password=PASSWORD):
    return client.post(LOGIN_URL, {"username": username, "password": password}, format="json")


@pytest.mark.django_db
class TestRegister:
    def test_creates_user_and_hides_password(self, client):
        response = client.post(
            REGISTER_URL,
            {"username": "carla", "email": "carla@example.com", "password": PASSWORD},
            format="json",
        )

        assert response.status_code == 201
        assert response.json() == {
            "id": response.json()["id"],
            "username": "carla",
            "email": "carla@example.com",
            "role": UserRole.USER,
        }

    def test_password_is_stored_as_argon2_hash(self, client):
        client.post(
            REGISTER_URL,
            {"username": "carla", "email": "carla@example.com", "password": PASSWORD},
            format="json",
        )

        user = User.objects.get(username="carla")
        assert user.password.startswith("argon2$")
        assert user.check_password(PASSWORD)

    def test_role_in_payload_is_ignored(self, client):
        """Cadastro público nunca cria admin (evita escalada de privilégio)."""
        response = client.post(
            REGISTER_URL,
            {
                "username": "carla",
                "email": "carla@example.com",
                "password": PASSWORD,
                "role": "admin",
            },
            format="json",
        )

        assert response.json()["role"] == UserRole.USER
        assert User.objects.get(username="carla").role == UserRole.USER

    @pytest.mark.parametrize(
        ("data", "field"),
        [
            pytest.param(
                {"username": "carla", "email": "outra@example.com", "password": PASSWORD},
                "username",
                id="username-repetido",
            ),
            pytest.param(
                {"username": "outra", "email": "carla@example.com", "password": PASSWORD},
                "email",
                id="email-repetido",
            ),
            pytest.param(
                {"username": "dani", "email": "dani@example.com", "password": "123"},
                "password",
                id="senha-fraca",
            ),
            pytest.param(
                {"username": "dani", "email": "dani@example.com", "password": "dani@example.com"},
                "password",
                id="senha-parecida-com-email",
            ),
            pytest.param(
                {"username": "dani", "email": "nao-e-email", "password": PASSWORD},
                "email",
                id="email-invalido",
            ),
        ],
    )
    def test_invalid_data_returns_400_with_field(self, client, carla, data, field):
        response = client.post(REGISTER_URL, data, format="json")

        assert error_of(response) == (400, "validation_error")
        assert field in response.json()["error"]["details"]

    def test_missing_fields_returns_400(self, client):
        response = client.post(REGISTER_URL, {}, format="json")

        assert error_of(response) == (400, "validation_error")
        assert set(response.json()["error"]["details"]) == {"username", "email", "password"}


@pytest.mark.django_db
class TestLoginAndRefresh:
    def test_login_returns_access_and_refresh(self, client, carla):
        response = login(client)

        assert response.status_code == 200
        assert set(response.json()) == {"access", "refresh"}

    def test_wrong_password_returns_401(self, client, carla):
        response = login(client, password="errada")

        assert error_of(response) == (401, "no_active_account")

    def test_unknown_user_gets_same_response_as_wrong_password(self, client, carla):
        """Não revela se o username existe."""
        wrong_password = login(client, password="errada")
        unknown_user = login(client, username="ninguem")

        assert wrong_password.json() == unknown_user.json()

    def test_access_token_authenticates_protected_endpoint(self, client, carla):
        access = login(client).json()["access"]

        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        assert api.get("/api/reservations").status_code == 200

    def test_invalid_token_on_protected_endpoint_returns_401(self, client):
        client.credentials(HTTP_AUTHORIZATION="Bearer token-invalido")

        response = client.get("/api/reservations")

        assert error_of(response) == (401, "token_not_valid")

    def test_refresh_returns_new_access(self, client, carla):
        refresh = login(client).json()["refresh"]

        response = client.post(REFRESH_URL, {"refresh": refresh}, format="json")

        assert response.status_code == 200
        assert "access" in response.json()

    def test_invalid_refresh_returns_401(self, client):
        response = client.post(REFRESH_URL, {"refresh": "token-invalido"}, format="json")

        assert error_of(response) == (401, "token_not_valid")


@pytest.mark.django_db
class TestLoginRateLimit:
    # Fixa a taxa no teste, independentemente do LOGIN_THROTTLE_RATE do .env.
    @pytest.fixture(autouse=True)
    def fixed_login_rate(self, monkeypatch):
        # THROTTLE_RATES é atributo de classe lido do settings na importação do DRF;
        # override_settings não o alcança, então o valor é trocado direto na classe.
        monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"login": "3/min"})

    def test_blocks_after_limit_with_429(self, client, carla):
        statuses = [login(client, password="errada").status_code for _ in range(4)]

        assert statuses == [401, 401, 401, 429]

    def test_correct_password_is_also_blocked_while_throttled(self, client, carla):
        for _ in range(3):
            login(client, password="errada")

        response = login(client)

        assert error_of(response) == (429, "throttled")

    def test_register_is_not_throttled(self, client):
        for i in range(5):
            response = client.post(
                REGISTER_URL,
                {"username": f"user{i}", "email": f"user{i}@example.com", "password": PASSWORD},
                format="json",
            )
            assert response.status_code == 201
