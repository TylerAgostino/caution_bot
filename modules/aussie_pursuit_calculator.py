import math
import statistics


def calculate_hold_times(
    drivers: list[dict],
    race_laps: int,
    position_mod_step: float,
    passing_modifier: float,
) -> list[dict]:
    """Calculate black-flag hold times for an Aussie Pursuit format race.

    Drivers are sorted slowest-first. The slowest car receives a drive-through ("D");
    all others receive a timed hold long enough that, in theory, every car finishes
    the race simultaneously.

    Args:
        drivers: Each dict must contain:
            - car_number (str)
            - driver_name (str)
            - car_class (str)
            - lap_time_seconds (float)
            - comp_adj_lower (float, optional): subtract from modified time (penalises sandbagging)
            - comp_adj_extra_hold (float, optional): add to final hold (accounts for planned pit stops)
        race_laps: Number of laps in the race.
        position_mod_step: Per-position increment, e.g. 0.0003.
        passing_modifier: Multiplier applied to all cars, e.g. 1.0025.

    Returns:
        A new list sorted slowest-first, each dict extended with:
            - position_index (int): 0 = slowest
            - modified_lap_time (float): adjusted time in seconds
            - hold_seconds (int | "D"): "D" for drive-through, else seconds
    """
    if not drivers:
        return []

    sorted_drivers = sorted(
        [dict(d) for d in drivers],
        key=lambda d: d["lap_time_seconds"],
        reverse=True,
    )

    for i, driver in enumerate(sorted_drivers):
        position_modifier = 1 + i * position_mod_step
        modified = (
            driver["lap_time_seconds"] * passing_modifier * position_modifier
            - driver.get("comp_adj_lower", 0.0)
        )
        driver["position_index"] = i
        driver["modified_lap_time"] = modified

    max_modified = math.floor(
        max(d["modified_lap_time"] for d in sorted_drivers) * 1000
    ) / 1000

    for driver in sorted_drivers:
        raw_hold = math.floor(
            (max_modified - driver["modified_lap_time"]) * race_laps
        ) + driver.get("comp_adj_extra_hold", 0.0)
        driver["hold_seconds"] = "D" if raw_hold <= 0 else int(raw_hold)

    return sorted_drivers


def filter_outlier_laps(laps: list[float]) -> list[float]:
    """Remove laps more than one standard deviation above the median.

    Filters out slow laps caused by traffic, incidents, or yellow-flag periods.
    Returns the original list unchanged when fewer than 3 laps are present.
    """
    if len(laps) < 3:
        return laps
    med = statistics.median(laps)
    stdev = statistics.stdev(laps)
    return [t for t in laps if t <= med + stdev]
