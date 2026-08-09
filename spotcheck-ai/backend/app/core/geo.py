"""座標計算。PostGISは導入せず、バウンディングボックス＋Haversineで扱う（docs/02-database.md 2.2）。"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0
#: 緯度1度あたりの距離（約111.32km）
METERS_PER_DEGREE_LAT = 111_320.0


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """2点間の大円距離をメートルで返す。"""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """粗い絞り込み用の矩形 (min_lat, max_lat, min_lng, max_lng) を返す。

    経度方向の1度あたりの距離は緯度によって変わるため cos で補正する。
    高緯度・極付近では補正値が0に近づくため、下限を設けて全経度を含める。
    """
    radius_m = radius_km * 1000
    d_lat = radius_m / METERS_PER_DEGREE_LAT
    cos_lat = math.cos(math.radians(lat))
    if abs(cos_lat) < 1e-6:
        return (max(-90.0, lat - d_lat), min(90.0, lat + d_lat), -180.0, 180.0)
    d_lng = radius_m / (METERS_PER_DEGREE_LAT * abs(cos_lat))
    return (
        max(-90.0, lat - d_lat),
        min(90.0, lat + d_lat),
        max(-180.0, lng - d_lng),
        min(180.0, lng + d_lng),
    )
