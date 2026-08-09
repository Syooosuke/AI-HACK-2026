"""EXIF抽出（docs/06-phases.md Phase 4 作業5）。

ブラウザ撮影ではEXIFにGPSが入らないため、**あくまで補助的な検証材料**として扱う（D-02）。
抽出に失敗しても提出処理は続行する。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PIL import ExifTags, Image, UnidentifiedImageError

from app.core.logging import get_logger

logger = get_logger(__name__)

_GPS_IFD_TAG = 0x8825
# GPS IFD 内のタグ番号（PIL.ExifTags.GPSTAGS の逆引き）
_GPS_LATITUDE_REF = 1
_GPS_LATITUDE = 2
_GPS_LONGITUDE_REF = 3
_GPS_LONGITUDE = 4


def extract_exif(data: bytes) -> dict[str, Any] | None:
    """EXIFから検証に使う項目だけを取り出す。取得できなければ None。"""
    try:
        with Image.open(_buffer(data)) as image:
            exif = image.getexif()
    except (UnidentifiedImageError, OSError, ValueError):
        logger.warning("画像を開けずEXIFを抽出できませんでした")
        return None

    if not exif:
        return None

    result: dict[str, Any] = {}
    tag_names = {value: key for key, value in ExifTags.Base.__members__.items()}

    for tag_id, value in exif.items():
        name = tag_names.get(tag_id)
        if name in ("Make", "Model", "Software", "Orientation"):
            result[_snake(name)] = _plain(value)

    # 撮影時刻は Exif IFD 側にある
    try:
        exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
    except (KeyError, ValueError):
        exif_ifd = {}
    for tag_id, value in (exif_ifd or {}).items():
        name = tag_names.get(tag_id)
        if name in ("DateTimeOriginal", "DateTimeDigitized"):
            result[_snake(name)] = _plain(value)

    gps = _extract_gps(exif)
    if gps is not None:
        result["gps_lat"], result["gps_lng"] = gps

    return result or None


def exif_datetime(exif: dict[str, Any] | None) -> datetime | None:
    """`DateTimeOriginal`（"YYYY:MM:DD HH:MM:SS"）を datetime にする。タイムゾーンは不明。"""
    if not exif:
        return None
    raw = exif.get("date_time_original") or exif.get("date_time_digitized")
    if not isinstance(raw, str):
        return None
    try:
        # EXIFの撮影時刻にタイムゾーン情報は含まれないため naive のまま返す。
        # 位置チェックでは参考表示にのみ使い、時刻の合否判定には使わない。
        return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")  # noqa: DTZ007
    except ValueError:
        return None


def _extract_gps(exif: Any) -> tuple[float, float] | None:
    try:
        gps = exif.get_ifd(_GPS_IFD_TAG)
    except (KeyError, ValueError):
        return None
    if not gps:
        return None

    lat = _to_degrees(gps.get(_GPS_LATITUDE))
    lng = _to_degrees(gps.get(_GPS_LONGITUDE))
    if lat is None or lng is None:
        return None

    if str(gps.get(_GPS_LATITUDE_REF, "N")).upper().startswith("S"):
        lat = -lat
    if str(gps.get(_GPS_LONGITUDE_REF, "E")).upper().startswith("W"):
        lng = -lng
    return lat, lng


def _to_degrees(value: Any) -> float | None:
    """(度, 分, 秒) の有理数タプルを10進度へ変換する。"""
    if not value or len(value) < 3:
        return None
    try:
        degrees, minutes, seconds = (float(part) for part in value[:3])
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return degrees + minutes / 60 + seconds / 3600


def _plain(value: Any) -> Any:
    """jsonb に入れられる形へ落とす。"""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[:200]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:200]


def _snake(name: str) -> str:
    out: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index > 0:
            out.append("_")
        out.append(char.lower())
    return "".join(out)


def _buffer(data: bytes):
    import io

    return io.BytesIO(data)
