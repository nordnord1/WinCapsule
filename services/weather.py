"""OpenWeather API client with full meteorological metrics (wind, pressure, rain, visibility)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests
from PySide6.QtCore import QObject, QTimer, Signal

from core.i18n import get_language, tr


def deg_to_compass_uk(deg: float) -> str:
    """Convert wind direction degrees (0..360) to Ukrainian cardinal label."""
    dirs = ("Пн", "ПнСх", "Сх", "ПдСх", "Пд", "ПдЗх", "Зх", "ПнЗх")
    idx = int((deg + 22.5) // 45.0) % 8
    return dirs[idx]


def deg_to_compass_local(deg: float) -> str:
    """Convert wind direction degrees (0..360) to localized cardinal label."""
    keys = ("dir_N", "dir_NE", "dir_E", "dir_SE", "dir_S", "dir_SW", "dir_W", "dir_NW")
    idx = int((deg + 22.5) // 45.0) % 8
    return tr(keys[idx])


@dataclass
class WeatherData:
    temp: float
    feels_like: float
    humidity: int
    description: str
    city: str
    icon_code: str
    units: str = "metric"
    temp_min: float = 0.0
    temp_max: float = 0.0
    pressure_mmhg: int = 760
    wind_speed: float = 0.0
    wind_deg: float = 0.0
    rain_mm: float = 0.0
    clouds_pct: int = 0
    visibility_km: float = 10.0
    updated_at: str = ""

    @property
    def unit_symbol(self) -> str:
        return "°F" if self.units == "imperial" else "°C"

    @property
    def wind_unit(self) -> str:
        return tr("wind_mph") if self.units == "imperial" else tr("wind_ms")

    @property
    def wind_dir_label(self) -> str:
        return deg_to_compass_local(self.wind_deg)

    @property
    def humidity_comfort(self) -> str:
        if self.humidity < 35:
            return tr("hum_dry")
        if self.humidity <= 65:
            return tr("hum_comfort")
        return tr("hum_humid")

    @property
    def vector_kind(self) -> str:
        code = self.icon_code[:2]
        mapping = {
            "01": "sun",
            "02": "cloud_sun",
            "03": "cloud",
            "04": "cloud",
            "09": "rain",
            "10": "rain",
            "11": "storm",
            "13": "snow",
            "50": "mist",
        }
        return mapping.get(code, "cloud_sun")


def parse_weather_response(payload: dict[str, Any], units: str = "metric") -> WeatherData:
    """Parse OpenWeather current weather JSON response into full WeatherData."""
    main = payload["main"]
    weather = payload["weather"][0]
    wind = payload.get("wind", {})
    clouds = payload.get("clouds", {})
    rain_obj = payload.get("rain", {})
    snow_obj = payload.get("snow", {})

    temp = float(main["temp"])
    t_min = float(main.get("temp_min", temp))
    t_max = float(main.get("temp_max", temp))
    pressure_hpa = float(main.get("pressure", 1013.0))
    pressure_mmhg = round(pressure_hpa * 0.750062)

    precip_mm = float(
        rain_obj.get("1h", rain_obj.get("3h", 0.0))
        + snow_obj.get("1h", snow_obj.get("3h", 0.0))
    )
    vis_m = float(payload.get("visibility", 10000.0))

    return WeatherData(
        temp=temp,
        feels_like=float(main.get("feels_like", temp)),
        humidity=int(main.get("humidity", 50)),
        description=str(weather.get("description", "")).capitalize(),
        city=str(payload.get("name", "")),
        icon_code=str(weather.get("icon", "01d")),
        units=units,
        temp_min=t_min,
        temp_max=t_max,
        pressure_mmhg=pressure_mmhg,
        wind_speed=float(wind.get("speed", 0.0)),
        wind_deg=float(wind.get("deg", 0.0)),
        rain_mm=round(precip_mm, 1),
        clouds_pct=int(clouds.get("all", 0)),
        visibility_km=round(vis_m / 1000.0, 1),
        updated_at=datetime.now().strftime("%H:%M"),
    )


class WeatherService(QObject):
    """Fetches current weather from OpenWeather API on a timer."""

    weather_updated = Signal(object)  # WeatherData
    weather_error = Signal(str)

    API_URL = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(
        self,
        api_key: str,
        city: str,
        units: str = "metric",
        refresh_minutes: int = 15,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._api_key = api_key.strip()
        self._city = city.strip()
        self._units = units
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self.set_refresh_minutes(refresh_minutes)

    def set_refresh_minutes(self, minutes: int) -> None:
        self._timer.setInterval(max(5, minutes) * 60 * 1000)

    def configure(self, api_key: str, city: str, units: str, refresh_minutes: int) -> None:
        self._api_key = api_key.strip()
        self._city = city.strip()
        self._units = units
        self.set_refresh_minutes(refresh_minutes)
        self.refresh()

    def set_city(self, city: str) -> None:
        if city.strip():
            self._city = city.strip()
            self.refresh()

    def start(self) -> None:
        self.refresh()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def refresh(self) -> None:
        if not self._api_key:
            self.weather_error.emit(tr("w_err_no_key"))
            return
        if not self._city:
            self.weather_error.emit(tr("w_err_no_city"))
            return
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self) -> None:
        try:
            owm_lang = get_language() if get_language() in ("uk", "ru", "en") else "en"
            resp = requests.get(
                self.API_URL,
                params={
                    "q": self._city,
                    "appid": self._api_key,
                    "units": self._units,
                    "lang": owm_lang,
                },
                timeout=8,
            )
            if resp.status_code == 401:
                self.weather_error.emit(tr("w_err_bad_key"))
                return
            if resp.status_code == 404:
                self.weather_error.emit(tr("w_err_city_404").format(city=self._city))
                return
            resp.raise_for_status()
            data = parse_weather_response(resp.json(), units=self._units)
            self.weather_updated.emit(data)
        except requests.RequestException:
            self.weather_error.emit(tr("w_err_net"))
        except (KeyError, IndexError, ValueError):
            self.weather_error.emit(tr("w_err_api"))
