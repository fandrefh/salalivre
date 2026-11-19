"""Testes unitários do cálculo de disponibilidade (funções puras, sem banco)."""

from datetime import date, datetime

import pytest

from reservations.availability import day_window, free_intervals
from reservations.rules import BUSINESS_TZ

DAY = date(2030, 1, 10)
BEFORE_DAY = datetime(2030, 1, 1, tzinfo=BUSINESS_TZ)


def at(hour: int, minute: int = 0, day: int = 10) -> datetime:
    """Data/hora no fuso de negócio, em janeiro de 2030."""
    return datetime(2030, 1, day, hour, minute, tzinfo=BUSINESS_TZ)


def as_text(intervals: list[tuple[datetime, datetime]]) -> list[str]:
    """Formata os intervalos como 'HH:MM-HH:MM' para asserts legíveis."""
    return [f"{start:%H:%M}-{end:%H:%M}" for start, end in intervals]


class TestDayWindow:
    def test_future_day_uses_full_business_hours(self):
        assert day_window(DAY, BEFORE_DAY) == (at(7), at(20))

    def test_today_starts_at_now(self):
        assert day_window(DAY, at(10, 30)) == (at(10, 30), at(20))

    def test_today_before_opening_starts_at_opening(self):
        assert day_window(DAY, at(6)) == (at(7), at(20))

    @pytest.mark.parametrize(
        "now",
        [
            pytest.param(at(20), id="hoje-exatamente-20h"),
            pytest.param(at(21), id="hoje-apos-20h"),
            pytest.param(at(9, day=11), id="dia-passado"),
        ],
    )
    def test_returns_none_when_nothing_is_left(self, now):
        assert day_window(DAY, now) is None

    def test_window_is_in_business_timezone(self):
        start, end = day_window(DAY, BEFORE_DAY)
        assert start.tzinfo == BUSINESS_TZ
        assert end.tzinfo == BUSINESS_TZ


class TestFreeIntervals:
    @pytest.mark.parametrize(
        ("busy", "expected"),
        [
            pytest.param([], ["07:00-20:00"], id="sem-reservas"),
            pytest.param([(at(9), at(10))], ["07:00-09:00", "10:00-20:00"], id="uma-reserva"),
            pytest.param(
                [(at(9), at(10)), (at(10), at(11))],
                ["07:00-09:00", "11:00-20:00"],
                id="adjacentes-sem-lacuna-vazia",
            ),
            pytest.param(
                [(at(14), at(15)), (at(9), at(10))],
                ["07:00-09:00", "10:00-14:00", "15:00-20:00"],
                id="entrada-fora-de-ordem",
            ),
            pytest.param([(at(7), at(9))], ["09:00-20:00"], id="reserva-na-abertura"),
            pytest.param([(at(18), at(20))], ["07:00-18:00"], id="reserva-no-fechamento"),
            pytest.param(
                [(at(7), at(11)), (at(11), at(15)), (at(15), at(19)), (at(19), at(20))],
                [],
                id="dia-cheio",
            ),
            pytest.param(
                [(at(7), at(9)), (at(9, 15), at(20))],
                ["09:00-09:15"],
                id="lacuna-menor-que-30min-e-devolvida",
            ),
        ],
    )
    def test_full_day(self, busy, expected):
        assert as_text(free_intervals(at(7), at(20), busy)) == expected

    @pytest.mark.parametrize(
        ("busy", "expected"),
        [
            pytest.param([], ["10:30-20:00"], id="sem-reservas"),
            pytest.param([(at(9), at(11))], ["11:00-20:00"], id="reserva-em-andamento-ocupa"),
            pytest.param([(at(8), at(9))], ["10:30-20:00"], id="reserva-ja-encerrada-ignorada"),
        ],
    )
    def test_window_clipped_by_now(self, busy, expected):
        window = day_window(DAY, at(10, 30))
        assert as_text(free_intervals(*window, busy)) == expected
