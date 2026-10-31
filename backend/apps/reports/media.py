"""Upload handling: validate, strip EXIF (privacy), downscale, hash, and extract authenticity signals."""
import io
from datetime import datetime, timedelta

import imagehash
from django.core.files.base import ContentFile
from PIL import ExifTags, Image, ImageOps

from apps.authorities.geo import haversine_m

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_AUDIO_BYTES = 6 * 1024 * 1024
MAX_VIDEO_BYTES = 30 * 1024 * 1024
AUDIO_EXT = ("webm", "ogg", "opus", "mp3", "wav", "m4a", "aac", "flac")
VIDEO_EXT = ("mp4", "webm", "mov")


class MediaError(ValueError):
    pass


def _gps_from_exif(exif):
    try:
        gps = exif.get_ifd(0x8825)
        if not gps:
            return None

        def conv(v, ref):
            d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
            return -d if ref in ("S", "W") else d

        return conv(gps[2], gps[1]), conv(gps[4], gps[3])
    except Exception:  # noqa: BLE001
        return None


def process_image(upload, lat, lng):
    """Returns (ContentFile jpeg without EXIF, phash hex, flags list)."""
    if upload.size > MAX_IMAGE_BYTES:
        raise MediaError("Image is too large (max 12 MB).")
    try:
        data = upload.read()
        im = Image.open(io.BytesIO(data))
        im.verify()
        im = Image.open(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise MediaError("The image file could not be read.") from exc

    flags = []
    try:
        exif = im.getexif()
        taken = exif.get(ExifTags.Base.DateTime) or exif.get_ifd(0x8769).get(0x9003)
        if taken:
            when = datetime.strptime(str(taken)[:19], "%Y:%m:%d %H:%M:%S")
            if datetime.now() - when > timedelta(days=30):
                flags.append(f"photo was taken on {when:%Y-%m-%d}, more than 30 days before submission")
        pos = _gps_from_exif(exif)
        if pos and haversine_m(pos[0], pos[1], lat, lng) > 1000:
            flags.append("photo GPS location differs from the reported location by more than 1 km")
    except Exception:  # noqa: BLE001
        pass

    im = ImageOps.exif_transpose(im).convert("RGB")  # transposing/convert drops EXIF
    im.thumbnail((1600, 1600))
    ph = str(imagehash.phash(im))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)  # no exif= argument -> metadata stripped
    return ContentFile(buf.getvalue(), name="photo.jpg"), ph, flags


def check_audio(upload):
    ext = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
    if ext not in AUDIO_EXT:
        raise MediaError("Unsupported audio format.")
    if upload.size > MAX_AUDIO_BYTES:
        raise MediaError("Voice note is too long (max about 30 seconds).")


def check_video(upload):
    ext = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
    if ext not in VIDEO_EXT:
        raise MediaError("Unsupported video format.")
    if upload.size > MAX_VIDEO_BYTES:
        raise MediaError("Video is too large (max 30 MB).")
