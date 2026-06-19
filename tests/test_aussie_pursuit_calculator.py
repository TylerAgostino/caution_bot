"""Unit tests for the Aussie Pursuit hold-time calculator.

Values are cross-checked against the spreadsheet: Aussie Pursuit_Master_V2.xlsx,
Build sheet, columns M (modified lap time) and R (hold seconds).
"""

import pytest
from modules.aussie_pursuit_calculator import calculate_hold_times, filter_outlier_laps


# ---------------------------------------------------------------------------
# Spreadsheet-verified fixture (Charlotte Oval, 23 laps)
# Global: position_mod_step=0.0003, passing_modifier=1.0025, race_laps=23
# ---------------------------------------------------------------------------

RACE_LAPS = 23
POS_STEP = 0.0003
PASS_MOD = 1.0025


def _make_driver(car_number, driver_name, car_class, lap_time_seconds,
                 comp_adj_lower=0.0, comp_adj_extra_hold=0.0):
    return {
        "car_number": car_number,
        "driver_name": driver_name,
        "car_class": car_class,
        "lap_time_seconds": lap_time_seconds,
        "comp_adj_lower": comp_adj_lower,
        "comp_adj_extra_hold": comp_adj_extra_hold,
    }


# Two cars taken directly from the spreadsheet rows 22-23
DRIVERS_TWO = [
    _make_driver("19", "Driver A", "Legends", 45.94),
    _make_driver("51", "Driver B", "Formula Vee", 51.007),
]


class TestCalculateHoldTimes:
    def test_slowest_car_gets_drive_through(self):
        results = calculate_hold_times(DRIVERS_TWO, RACE_LAPS, POS_STEP, PASS_MOD)
        slowest = next(r for r in results if r["car_number"] == "51")
        assert slowest["hold_seconds"] == "D"

    def test_fastest_car_hold_matches_spreadsheet(self):
        # Spreadsheet row 23: Legends '34 Rookie, 45.94s → hold = 116s
        results = calculate_hold_times(DRIVERS_TWO, RACE_LAPS, POS_STEP, PASS_MOD)
        legends = next(r for r in results if r["car_number"] == "19")
        assert legends["hold_seconds"] == 116

    def test_results_sorted_slowest_first(self):
        results = calculate_hold_times(DRIVERS_TWO, RACE_LAPS, POS_STEP, PASS_MOD)
        times = [r["lap_time_seconds"] for r in results]
        assert times == sorted(times, reverse=True)

    def test_position_indices_correct(self):
        results = calculate_hold_times(DRIVERS_TWO, RACE_LAPS, POS_STEP, PASS_MOD)
        assert results[0]["position_index"] == 0
        assert results[1]["position_index"] == 1

    def test_empty_input(self):
        assert calculate_hold_times([], RACE_LAPS, POS_STEP, PASS_MOD) == []

    def test_single_driver_gets_drive_through(self):
        results = calculate_hold_times(
            [_make_driver("7", "Solo", "Class", 50.0)],
            RACE_LAPS, POS_STEP, PASS_MOD,
        )
        assert results[0]["hold_seconds"] == "D"

    def test_comp_adj_lower_increases_hold(self):
        # Subtracting from a faster car's modified time makes it appear even faster,
        # giving it a longer hold than without the adjustment.
        base = calculate_hold_times(DRIVERS_TWO, RACE_LAPS, POS_STEP, PASS_MOD)
        adjusted_drivers = [
            _make_driver("19", "Driver A", "Legends", 45.94, comp_adj_lower=1.0),
            _make_driver("51", "Driver B", "Formula Vee", 51.007),
        ]
        adjusted = calculate_hold_times(adjusted_drivers, RACE_LAPS, POS_STEP, PASS_MOD)
        base_hold = next(r["hold_seconds"] for r in base if r["car_number"] == "19")
        adj_hold = next(r["hold_seconds"] for r in adjusted if r["car_number"] == "19")
        assert adj_hold > base_hold

    def test_comp_adj_extra_hold_adds_directly(self):
        base = calculate_hold_times(DRIVERS_TWO, RACE_LAPS, POS_STEP, PASS_MOD)
        adjusted_drivers = [
            _make_driver("19", "Driver A", "Legends", 45.94, comp_adj_extra_hold=30.0),
            _make_driver("51", "Driver B", "Formula Vee", 51.007),
        ]
        adjusted = calculate_hold_times(adjusted_drivers, RACE_LAPS, POS_STEP, PASS_MOD)
        base_hold = next(r["hold_seconds"] for r in base if r["car_number"] == "19")
        adj_hold = next(r["hold_seconds"] for r in adjusted if r["car_number"] == "19")
        assert adj_hold == base_hold + 30

    def test_input_dicts_not_mutated(self):
        originals = [dict(d) for d in DRIVERS_TWO]
        calculate_hold_times(DRIVERS_TWO, RACE_LAPS, POS_STEP, PASS_MOD)
        for original, after in zip(originals, DRIVERS_TWO):
            assert original == after

    def test_more_race_laps_increases_hold(self):
        short = calculate_hold_times(DRIVERS_TWO, 10, POS_STEP, PASS_MOD)
        long = calculate_hold_times(DRIVERS_TWO, 30, POS_STEP, PASS_MOD)
        legends_short = next(r["hold_seconds"] for r in short if r["car_number"] == "19")
        legends_long = next(r["hold_seconds"] for r in long if r["car_number"] == "19")
        assert legends_long > legends_short


class TestFilterOutlierLaps:
    def test_fewer_than_three_laps_unchanged(self):
        assert filter_outlier_laps([]) == []
        assert filter_outlier_laps([50.0]) == [50.0]
        assert filter_outlier_laps([50.0, 51.0]) == [50.0, 51.0]

    def test_outlier_slow_lap_removed(self):
        # A lap 5s slower than the others should be filtered
        laps = [46.0, 46.1, 46.2, 51.5]
        result = filter_outlier_laps(laps)
        assert 51.5 not in result
        assert 46.0 in result

    def test_identical_laps_unchanged(self):
        laps = [46.0, 46.0, 46.0, 46.0]
        result = filter_outlier_laps(laps)
        assert result == laps
