"""Testes dos endpoints de reserva: contrato HTTP, permissões e formato de erro.

As regras em si estão cobertas em test_rules.py e test_services.py; aqui cada regra tem uma
verificação de ponta a ponta (status HTTP + `error.code`) e o foco é o que a camada HTTP
acrescenta: autenticação, escopo por papel, filtros, paginação, fusos e formato da resposta.
"""

from datetime import datetime

import pytest
import time_machine
from rest_framework.test import APIClient

from reservations.models import Reservation, ReservationStatus
from reservations.rules import BUSINESS_TZ
from rooms.models import Room

NOW = datetime(2030, 1, 9, 12, 0, tzinfo=BUSINESS_TZ)
TODAY = "2030-01-09"
TOMORROW = "2030-01-10"

RESERVATIONS_URL = "/api/reservations"


def cancel_url(pk: int) -> str:
    return f"{RESERVATIONS_URL}/{pk}/cancel"


def availability_url(room_pk: int, day: str | None = TOMORROW) -> str:
    url = f"/api/rooms/{room_pk}/availability"
    return f"{url}?date={day}" if day else url


def at(hour: int, minute: int = 0, day: int = 10) -> datetime:
    return datetime(2030, 1, day, hour, minute, tzinfo=BUSINESS_TZ)


def payload(room, start: str, end: str, day: str = TOMORROW) -> dict:
    """Corpo do POST com horários locais (-03:00), ex.: payload(room, "09:00", "10:00")."""
    return {
        "room": room.pk,
        "start_at": f"{day}T{start}:00-03:00",
        "end_at": f"{day}T{end}:00-03:00",
    }


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def error_of(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


@pytest.fixture(autouse=True)
def frozen_now():
    """A view usa timezone.now(): congela o relógio em NOW para os testes serem determinísticos."""
    with time_machine.travel(NOW, tick=False):
        yield


@pytest.fixture
def ana(user):
    return client_for(user)


@pytest.fixture
def bruno(other_user):
    return client_for(other_user)


@pytest.fixture
def admin(admin_user):
    return client_for(admin_user)


@pytest.fixture
def inactive_room(db):
    return Room.objects.create(
        name="Sala Laranja", capacity=6, location="1º andar", is_active=False
    )


def make_reservation(user, room, start_at, end_at, **kwargs) -> Reservation:
    """Cria direto pelo ORM, para montar cenários sem depender do endpoint em teste."""
    return Reservation.objects.create(
        user=user, room=room, start_at=start_at, end_at=end_at, **kwargs
    )


@pytest.mark.django_db
class TestAuthentication:
    @pytest.mark.parametrize(
        ("method", "url"),
        [
            pytest.param("get", RESERVATIONS_URL, id="listar"),
            pytest.param("post", RESERVATIONS_URL, id="criar"),
            pytest.param("post", cancel_url(1), id="cancelar"),
            pytest.param("get", availability_url(1), id="disponibilidade"),
        ],
    )
    def test_requires_token(self, api_client, method, url):
        response = getattr(api_client, method)(url)

        assert error_of(response) == (401, "not_authenticated")


@pytest.mark.django_db
class TestCreateReservation:
    def test_returns_201_with_reservation_in_business_timezone(self, ana, user, room):
        response = ana.post(RESERVATIONS_URL, payload(room, "09:00", "10:00"), format="json")

        assert response.status_code == 201
        body = response.json()
        assert body["room"] == room.pk
        assert body["user"] == user.pk
        assert body["status"] == ReservationStatus.ACTIVE
        assert body["start_at"] == "2030-01-10T09:00:00-03:00"
        assert body["end_at"] == "2030-01-10T10:00:00-03:00"
        assert body["cancelled_at"] is None

    def test_owner_is_always_the_authenticated_user(self, ana, user, other_user, room):
        data = {**payload(room, "09:00", "10:00"), "user": other_user.pk}

        response = ana.post(RESERVATIONS_URL, data, format="json")

        assert response.json()["user"] == user.pk

    def test_utc_input_is_converted_to_business_timezone(self, ana, room):
        data = {
            "room": room.pk,
            "start_at": f"{TOMORROW}T12:00:00Z",
            "end_at": f"{TOMORROW}T13:00:00Z",
        }

        response = ana.post(RESERVATIONS_URL, data, format="json")

        assert response.status_code == 201
        assert response.json()["start_at"] == "2030-01-10T09:00:00-03:00"

    def test_input_without_timezone_is_read_as_business_timezone(self, ana, room):
        data = {
            "room": room.pk,
            "start_at": f"{TOMORROW}T14:00:00",
            "end_at": f"{TOMORROW}T15:00:00",
        }

        response = ana.post(RESERVATIONS_URL, data, format="json")

        assert response.status_code == 201
        assert response.json()["start_at"] == "2030-01-10T14:00:00-03:00"

    def test_malformed_payload_returns_400_with_field_details(self, ana):
        response = ana.post(RESERVATIONS_URL, {"room": 999, "start_at": "amanhã"}, format="json")

        assert error_of(response) == (400, "validation_error")
        assert set(response.json()["error"]["details"]) == {"room", "start_at", "end_at"}

    def test_r1_overlap_returns_409(self, ana, bruno, room):
        ana.post(RESERVATIONS_URL, payload(room, "09:00", "10:00"), format="json")

        response = bruno.post(RESERVATIONS_URL, payload(room, "09:30", "11:00"), format="json")

        assert error_of(response) == (409, "room_unavailable")

    def test_r2_past_returns_422(self, ana, room):
        response = ana.post(
            RESERVATIONS_URL, payload(room, "09:00", "10:00", day=TODAY), format="json"
        )

        assert error_of(response) == (422, "start_in_past")

    def test_r3_invalid_duration_returns_422(self, ana, room):
        response = ana.post(RESERVATIONS_URL, payload(room, "09:00", "09:29"), format="json")

        assert error_of(response) == (422, "invalid_duration")

    def test_r4_outside_business_hours_returns_422(self, ana, room):
        response = ana.post(RESERVATIONS_URL, payload(room, "19:00", "20:01"), format="json")

        assert error_of(response) == (422, "outside_business_hours")

    def test_r5_fourth_active_future_reservation_returns_409(self, ana, room):
        for start, end in [("08:00", "09:00"), ("10:00", "11:00"), ("12:00", "13:00")]:
            assert (
                ana.post(RESERVATIONS_URL, payload(room, start, end), format="json").status_code
                == 201
            )

        response = ana.post(RESERVATIONS_URL, payload(room, "14:00", "15:00"), format="json")

        assert error_of(response) == (409, "reservation_limit_reached")

    def test_r7_inactive_room_returns_422(self, ana, inactive_room):
        response = ana.post(
            RESERVATIONS_URL, payload(inactive_room, "09:00", "10:00"), format="json"
        )

        assert error_of(response) == (422, "room_inactive")


@pytest.mark.django_db
class TestListReservations:
    @pytest.fixture
    def reservations(self, user, other_user, room):
        other_room = Room.objects.create(name="Sala Verde", capacity=4, location="3º andar")
        return {
            "ana_tomorrow": make_reservation(user, room, at(9), at(10)),
            "bruno_tomorrow": make_reservation(other_user, other_room, at(9), at(10)),
            "bruno_next_week": make_reservation(other_user, room, at(9, day=17), at(10, day=17)),
        }

    @staticmethod
    def ids(response) -> set[int]:
        return {item["id"] for item in response.json()["results"]}

    def test_user_sees_only_own_reservations(self, ana, reservations):
        response = ana.get(RESERVATIONS_URL)

        assert response.status_code == 200
        assert self.ids(response) == {reservations["ana_tomorrow"].pk}

    def test_filters_are_ignored_for_user(self, ana, other_user, reservations):
        response = ana.get(RESERVATIONS_URL, {"user": other_user.pk})

        assert self.ids(response) == {reservations["ana_tomorrow"].pk}

    def test_admin_sees_all_reservations(self, admin, reservations):
        response = admin.get(RESERVATIONS_URL)

        assert self.ids(response) == {r.pk for r in reservations.values()}

    def test_admin_filters_by_room(self, admin, room, reservations):
        response = admin.get(RESERVATIONS_URL, {"room": room.pk})

        assert self.ids(response) == {
            reservations["ana_tomorrow"].pk,
            reservations["bruno_next_week"].pk,
        }

    def test_admin_filters_by_user(self, admin, other_user, reservations):
        response = admin.get(RESERVATIONS_URL, {"user": other_user.pk})

        assert self.ids(response) == {
            reservations["bruno_tomorrow"].pk,
            reservations["bruno_next_week"].pk,
        }

    def test_admin_filters_by_inclusive_date_range(self, admin, reservations):
        response = admin.get(RESERVATIONS_URL, {"date_from": TOMORROW, "date_to": TOMORROW})

        assert self.ids(response) == {
            reservations["ana_tomorrow"].pk,
            reservations["bruno_tomorrow"].pk,
        }

    def test_date_filter_uses_business_timezone(self, admin, user, room):
        """19:30 local do dia 10 é 22:30 UTC — ainda dia 10. Às 21:30 local seria dia 11 em UTC."""
        late = make_reservation(user, room, at(19), at(19, 30))

        response = admin.get(RESERVATIONS_URL, {"date_from": TOMORROW, "date_to": TOMORROW})

        assert late.pk in self.ids(response)

    def test_invalid_date_filter_returns_400(self, admin):
        response = admin.get(RESERVATIONS_URL, {"date_from": "10/01/2030"})

        assert error_of(response) == (400, "validation_error")

    def test_includes_cancelled_reservations(self, ana, user, room):
        make_reservation(user, room, at(9), at(10), status=ReservationStatus.CANCELLED)

        response = ana.get(RESERVATIONS_URL)

        assert [item["status"] for item in response.json()["results"]] == ["cancelled"]

    def test_is_paginated(self, ana, user, room):
        for hour in range(7, 12):
            make_reservation(user, room, at(hour), at(hour, 30))

        response = ana.get(RESERVATIONS_URL, {"page_size": 2})

        body = response.json()
        assert body["count"] == 5
        assert len(body["results"]) == 2
        assert body["next"] is not None


@pytest.mark.django_db
class TestCancelReservation:
    @pytest.fixture
    def reservation(self, user, room):
        return make_reservation(user, room, at(9), at(10))

    def test_owner_cancels_and_gets_updated_reservation(self, ana, reservation):
        response = ana.post(cancel_url(reservation.pk))

        assert response.status_code == 200
        assert response.json()["status"] == ReservationStatus.CANCELLED
        assert response.json()["cancelled_at"] == "2030-01-09T12:00:00-03:00"

    def test_someone_elses_reservation_looks_like_it_does_not_exist(self, bruno, reservation):
        other = bruno.post(cancel_url(reservation.pk))
        missing = bruno.post(cancel_url(999_999))

        assert error_of(other) == (404, "not_found")
        # Mesma resposta para "não existe" e "é de outro usuário": não revela existência.
        assert other.json() == missing.json()
        assert other.json()["error"]["message"] == "Não encontrado."

    def test_admin_cancels_any_reservation(self, admin, reservation):
        response = admin.post(cancel_url(reservation.pk))

        assert response.status_code == 200

    def test_already_cancelled_returns_409(self, ana, reservation):
        ana.post(cancel_url(reservation.pk))

        response = ana.post(cancel_url(reservation.pk))

        assert error_of(response) == (409, "reservation_not_active")

    def test_r6_less_than_one_hour_before_returns_422(self, ana, user, room):
        soon = make_reservation(user, room, at(12, 30, day=9), at(13, 30, day=9))

        response = ana.post(cancel_url(soon.pk))

        assert error_of(response) == (422, "cancellation_too_late")


@pytest.mark.django_db
class TestRoomAvailability:
    @staticmethod
    def free(response) -> list[str]:
        return [f"{i['start_at'][11:16]}-{i['end_at'][11:16]}" for i in response.json()["free"]]

    def test_returns_free_intervals_ignoring_cancelled(self, ana, user, other_user, room):
        make_reservation(user, room, at(9), at(10))
        make_reservation(other_user, room, at(14), at(15), status=ReservationStatus.CANCELLED)

        response = ana.get(availability_url(room.pk))

        assert response.status_code == 200
        assert response.json()["room"] == room.pk
        assert response.json()["date"] == TOMORROW
        assert self.free(response) == ["07:00-09:00", "10:00-20:00"]

    def test_today_starts_at_current_time(self, ana, room):
        response = ana.get(availability_url(room.pk, TODAY))

        assert self.free(response) == ["12:00-20:00"]

    def test_past_day_is_empty(self, ana, room):
        response = ana.get(availability_url(room.pk, "2030-01-08"))

        assert response.json()["free"] == []

    def test_inactive_room_returns_422(self, ana, inactive_room):
        response = ana.get(availability_url(inactive_room.pk))

        assert error_of(response) == (422, "room_inactive")

    def test_unknown_room_returns_404(self, ana):
        response = ana.get(availability_url(999_999))

        assert error_of(response) == (404, "not_found")
        assert response.json()["error"]["message"] == "Não encontrado."

    @pytest.mark.parametrize(
        "day",
        [pytest.param("10/01/2030", id="formato-invalido"), pytest.param(None, id="ausente")],
    )
    def test_invalid_or_missing_date_returns_400(self, ana, room, day):
        response = ana.get(availability_url(room.pk, day))

        assert error_of(response) == (400, "validation_error")
