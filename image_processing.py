import io

from PIL import Image, ImageOps

# A stored receipt photo needs to look sharp at full-screen size in the
# in-app lightbox, not just as a small PDF thumbnail, so this is a more
# generous target than the separate (lower-res) downscaling done when
# embedding receipts into the PDF report or sending them to the AI parser.
STORED_IMAGE_MAX_DIMENSION = 1800
STORED_IMAGE_JPEG_QUALITY = 85


def downscale_receipt_image(file_storage):
    """Given a Flask FileStorage for an uploaded receipt, returns downscaled
    JPEG bytes suitable for permanent storage, or None if the file isn't a
    resizeable image (a PDF, or a format Pillow can't decode) -- callers
    should fall back to saving the original bytes unchanged in that case."""
    try:
        image = Image.open(file_storage.stream)
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.thumbnail((STORED_IMAGE_MAX_DIMENSION, STORED_IMAGE_MAX_DIMENSION), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=STORED_IMAGE_JPEG_QUALITY, optimize=True)
        return buf.getvalue()
    except Exception:
        return None
    finally:
        file_storage.stream.seek(0)
