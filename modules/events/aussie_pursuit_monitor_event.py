import threading

from modules.events import BaseEvent
from modules.aussie_pursuit_calculator import filter_outlier_laps


class AussiePursuitMonitorEvent(BaseEvent):
    """Monitors lap times during a practice session for Aussie Pursuit pace estimation.

    Accumulates each driver's raw lap times as they complete laps, filters outliers,
    and exposes pace estimates via get_pace_estimates(). Designed to run as a long-lived
    background thread during practice; stop via cancel_event.
    """

    def __init__(self, *args, **kwargs):
        self._lap_data: dict[str, dict] = {}
        self._prev_last_lap: dict[int, float] = {}
        self._lock = threading.Lock()
        super().__init__(*args, **kwargs)

    def event_sequence(self):
        while not self.cancel_event.is_set():
            try:
                self.sdk.freeze_var_buffer_latest()
                driver_info = self.sdk["DriverInfo"]
                last_lap_times = self.sdk["CarIdxLastLapTime"] or []

                if driver_info:
                    for driver in driver_info.get("Drivers", []):
                        idx = driver.get("CarIdx", -1)
                        car_num = str(driver.get("CarNumber", "")).strip()
                        if not car_num or car_num in ("0", "PACE01"):
                            continue
                        if idx < 0 or idx >= len(last_lap_times):
                            continue

                        lap_time = last_lap_times[idx]
                        if lap_time > 0 and lap_time != self._prev_last_lap.get(idx, 0):
                            with self._lock:
                                if car_num not in self._lap_data:
                                    self._lap_data[car_num] = {
                                        "driver_name": driver.get("UserName", ""),
                                        "car_class": driver.get("CarClassShortName", ""),
                                        "laps": [],
                                    }
                                self._lap_data[car_num]["laps"].append(lap_time)
                            self._prev_last_lap[idx] = lap_time
                            self.logger.debug(
                                f"Aussie Pursuit monitor: car {car_num} lap {lap_time:.3f}s"
                            )
            except Exception as e:
                self.logger.error(f"AussiePursuitMonitorEvent error: {e}")

            self.sleep(1)

    def get_pace_estimates(self) -> dict[str, dict]:
        """Return per-car pace estimates with outliers filtered.

        Returns:
            Dict keyed by car_number, each value containing:
                - driver_name (str)
                - car_class (str)
                - lap_count (int): total raw laps recorded
                - pace (float | None): median of filtered laps, or None if no laps
        """
        with self._lock:
            snapshot = {k: dict(v, laps=list(v["laps"])) for k, v in self._lap_data.items()}

        estimates = {}
        for car_num, data in snapshot.items():
            filtered = filter_outlier_laps(data["laps"])
            from statistics import median

            estimates[car_num] = {
                "driver_name": data["driver_name"],
                "car_class": data["car_class"],
                "lap_count": len(data["laps"]),
                "pace": median(filtered) if filtered else None,
            }
        return estimates

    def total_lap_count(self) -> int:
        with self._lock:
            return sum(len(v["laps"]) for v in self._lap_data.values())

    def car_count(self) -> int:
        with self._lock:
            return len(self._lap_data)
