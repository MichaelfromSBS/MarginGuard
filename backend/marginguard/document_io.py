"""Bounded local reading for supported invoice/receipt document formats."""
import base64
from dataclasses import dataclass
from io import BytesIO
import warnings

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_PDF_PAGES = 10
MAX_TEXT_CHARACTERS = 64_000
MAX_PAGE_CONTENT_BYTES = 2_000_000
SUPPORTED_MEDIA_TYPES = frozenset({"application/pdf", "image/png", "image/jpeg"})


@dataclass(frozen=True)
class PreparedDocument:
    source_text: str | None
    page_texts: list[str]
    page_count: int
    image_data_url: str | None


class DocumentReadError(Exception):
    """A safe document-level failure, without parser internals or source contents."""

    def __init__(self, code: str, message: str, needs_review: bool = True):
        super().__init__(message)
        self.code = code
        self.message = message
        self.needs_review = needs_review


def read_document(data: bytes, media_type: str) -> PreparedDocument:
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise DocumentReadError("unsupported_media_type", "Use a readable PDF, PNG or JPEG document.", False)
    if not data:
        raise DocumentReadError("empty_document", "The uploaded document is empty.", False)
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentReadError("document_too_large", "Documents must be no larger than 4 MB.", False)
    if media_type == "application/pdf":
        return _read_pdf(data)
    return _read_image(data, media_type)


def _read_pdf(data: bytes) -> PreparedDocument:
    if not data.startswith(b"%PDF-"):
        raise DocumentReadError("invalid_pdf", "The file does not contain a valid supported PDF.")
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise DocumentReadError("encrypted_pdf", "Encrypted PDFs need an unlocked copy before processing.")
        page_count = len(reader.pages)
        if page_count < 1:
            raise DocumentReadError("empty_pdf", "The PDF has no pages.")
        if page_count > MAX_PDF_PAGES:
            raise DocumentReadError("pdf_page_limit", "PDF documents may contain at most 10 pages.")
        page_texts = []
        count = 0
        for page in reader.pages:
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > MAX_PAGE_CONTENT_BYTES:
                raise DocumentReadError("pdf_content_limit", "A PDF page is too complex for this prototype. Export a simpler readable copy.")
            text = page.extract_text() or ""
            if not text.strip():
                raise DocumentReadError("pdf_no_readable_text", "A PDF page has no readable text. Scanned PDFs need OCR or a supported image upload.")
            count += len(text)
            if count > MAX_TEXT_CHARACTERS:
                raise DocumentReadError("pdf_text_limit", "PDF text must contain no more than 64,000 characters.")
            page_texts.append(text)
        source_text = "\n\n".join(page_texts)
        if len(source_text) > MAX_TEXT_CHARACTERS:
            raise DocumentReadError("pdf_text_limit", "PDF text must contain no more than 64,000 characters.")
        return PreparedDocument(source_text, page_texts, page_count, None)
    except DocumentReadError:
        raise
    except (PdfReadError, ValueError, TypeError, KeyError, IndexError, OSError, RecursionError, NotImplementedError) as exc:
        raise DocumentReadError("invalid_pdf", "The PDF could not be read safely. Re-export it with a standard PDF tool.") from exc


def _read_image(data: bytes, media_type: str) -> PreparedDocument:
    if len(data) > MAX_IMAGE_BYTES:
        raise DocumentReadError("image_too_large", "Image documents must be no larger than 3 MB.", False)
    expected_format = {"image/png": "PNG", "image/jpeg": "JPEG"}[media_type]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != expected_format:
                    raise DocumentReadError("image_type_mismatch", "The image contents do not match the declared PNG or JPEG type.")
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise DocumentReadError("image_pixel_limit", "Images may contain no more than 20 million pixels.")
                image.verify()
            # Verify checks structure; load a fresh handle to ensure pixels decode.
            with Image.open(BytesIO(data)) as image:
                image.load()
    except DocumentReadError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError, SyntaxError) as exc:
        raise DocumentReadError("invalid_image", "The image could not be decoded safely. Export a fresh PNG or JPEG.") from exc
    encoded = base64.b64encode(data).decode("ascii")
    return PreparedDocument(None, [], 1, f"data:{media_type};base64,{encoded}")
