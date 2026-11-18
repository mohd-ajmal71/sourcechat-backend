
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from io import BytesIO

from PIL import Image, ImageChops, ImageOps


API_URL = "https://commons.wikimedia.org/w/api.php"

USER_AGENT = (
    "SourceChatVerifier/1.0 "
    "(educational image-source verification project)"
)

MAX_DOWNLOAD_SIZE = 15 * 1024 * 1024
MAX_DHASH_DISTANCE = 6
MAX_AHASH_DISTANCE = 10


class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())

    def get_text(self):
        return " ".join(self.parts)


def clean_metadata_value(value):
    if value is None:
        return None

    if isinstance(value, dict):
        value = value.get("value", "")

    parser = HTMLTextExtractor()

    try:
        parser.feed(str(value))
        text = parser.get_text()
    except Exception:
        text = str(value)

    text = re.sub(r"\s+", " ", text).strip()

    return text or None


def make_filename_candidates(filename):
    basename = Path(filename).name
    candidates = []

    def add_candidate(name):
        name = name.strip()

        if not name:
            return

        if name not in candidates:
            candidates.append(name)

    add_candidate(basename)

    without_thumbnail_prefix = re.sub(
        r"^\d+px-",
        "",
        basename,
        flags=re.IGNORECASE
    )

    if without_thumbnail_prefix != basename:
        add_candidate(without_thumbnail_prefix)

    current_candidates = list(candidates)

    for candidate in current_candidates:
        without_copy_suffix = re.sub(
            r"\s*\(\d+\)(?=\.[^.]+$)",
            "",
            candidate
        )

        add_candidate(without_copy_suffix)

    return candidates


def api_request(params):
    query_params = {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        **params
    }

    url = API_URL + "?" + urlencode(query_params)

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json"
        }
    )

    with urlopen(request, timeout=20) as response:
        response_data = response.read(5 * 1024 * 1024)

    return json.loads(response_data.decode("utf-8"))


def download_image(url):
    if not url:
        return None

    try:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT
            }
        )

        with urlopen(request, timeout=20) as response:
            image_bytes = response.read(MAX_DOWNLOAD_SIZE + 1)

        if len(image_bytes) > MAX_DOWNLOAD_SIZE:
            return None

        return image_bytes

    except Exception:
        return None


def prepare_image(image_bytes):
    with Image.open(BytesIO(image_bytes)) as image:
        image = ImageOps.exif_transpose(image)
        return image.convert("L").copy()


def calculate_dhash(image):
    resampling = getattr(
        Image,
        "Resampling",
        Image
    )

    resized = image.resize(
        (9, 8),
        resampling.LANCZOS
    )

    pixels = list(resized.getdata())
    hash_value = 0

    for row in range(8):
        for column in range(8):
            left = pixels[row * 9 + column]
            right = pixels[row * 9 + column + 1]

            hash_value = (hash_value << 1) | (left > right)

    return hash_value


def calculate_ahash(image):
    resampling = getattr(
        Image,
        "Resampling",
        Image
    )

    resized = image.resize(
        (8, 8),
        resampling.LANCZOS
    )

    pixels = list(resized.getdata())
    average = sum(pixels) / len(pixels)

    hash_value = 0

    for pixel in pixels:
        hash_value = (hash_value << 1) | (pixel >= average)

    return hash_value


def hamming_distance(hash_one, hash_two):
    return (hash_one ^ hash_two).bit_count()


def compare_image_pixels(uploaded_bytes, source_bytes):
    if not source_bytes:
        return False

    try:
        with Image.open(BytesIO(uploaded_bytes)) as uploaded:
            with Image.open(BytesIO(source_bytes)) as source:
                uploaded_rgb = ImageOps.exif_transpose(
                    uploaded
                ).convert("RGB")

                source_rgb = ImageOps.exif_transpose(
                    source
                ).convert("RGB")

                if uploaded_rgb.size != source_rgb.size:
                    return False

                difference = ImageChops.difference(
                    uploaded_rgb,
                    source_rgb
                )

                return difference.getbbox() is None

    except Exception:
        return False


def compare_image_similarity(uploaded_bytes, source_bytes):
    if not source_bytes:
        return False

    try:
        uploaded_image = prepare_image(uploaded_bytes)
        source_image = prepare_image(source_bytes)

        uploaded_dhash = calculate_dhash(uploaded_image)
        source_dhash = calculate_dhash(source_image)

        uploaded_ahash = calculate_ahash(uploaded_image)
        source_ahash = calculate_ahash(source_image)

        dhash_distance = hamming_distance(
            uploaded_dhash,
            source_dhash
        )

        ahash_distance = hamming_distance(
            uploaded_ahash,
            source_ahash
        )

        return (
            dhash_distance <= MAX_DHASH_DISTANCE
            and ahash_distance <= MAX_AHASH_DISTANCE
        )

    except Exception:
        return False


def get_image_match_details(uploaded_bytes, source_bytes):
    if not source_bytes:
        return {
            "matched": False,
            "method": "NO_MATCH",
            "dhash_distance": None,
            "ahash_distance": None
        }

    if compare_image_pixels(uploaded_bytes, source_bytes):
        return {
            "matched": True,
            "method": "EXACT_PIXEL_MATCH",
            "dhash_distance": 0,
            "ahash_distance": 0
        }

    try:
        uploaded_image = prepare_image(uploaded_bytes)
        source_image = prepare_image(source_bytes)

        dhash_distance = hamming_distance(
            calculate_dhash(uploaded_image),
            calculate_dhash(source_image)
        )

        ahash_distance = hamming_distance(
            calculate_ahash(uploaded_image),
            calculate_ahash(source_image)
        )

        matched = (
            dhash_distance <= MAX_DHASH_DISTANCE
            and ahash_distance <= MAX_AHASH_DISTANCE
        )

        return {
            "matched": matched,
            "method": (
                "PERCEPTUAL_HASH_MATCH"
                if matched
                else "NO_MATCH"
            ),
            "dhash_distance": dhash_distance,
            "ahash_distance": ahash_distance
        }

    except Exception:
        return {
            "matched": False,
            "method": "NO_MATCH",
            "dhash_distance": None,
            "ahash_distance": None
        }


def compare_with_commons_image(
    uploaded_bytes,
    image_info,
    uploaded_width,
    uploaded_height
):
    source_url = image_info.get("url")

    source_bytes = download_image(source_url)

    if not source_bytes:
        return False

    match_details = get_image_match_details(
        uploaded_bytes,
        source_bytes
    )

    return match_details["matched"]


def get_metadata_value(extmetadata, key):
    value = extmetadata.get(key)

    if isinstance(value, dict):
        return clean_metadata_value(value.get("value"))

    return clean_metadata_value(value)


def create_file_result(
    page,
    image_info,
    uploaded_bytes=None,
    uploaded_width=None,
    uploaded_height=None,
    match_method="FILENAME_MATCH"
):
    extmetadata = image_info.get("extmetadata", {})

    match_details = {
        "matched": False,
        "method": "NOT_CHECKED",
        "dhash_distance": None,
        "ahash_distance": None
    }

    if uploaded_bytes is not None:
        source_bytes = download_image(
            image_info.get("url")
        )

        match_details = get_image_match_details(
            uploaded_bytes,
            source_bytes
        )

    visual_match_verified = match_details["matched"]
    verification_method = match_details["method"]

    license_name = get_metadata_value(
        extmetadata,
        "LicenseShortName"
    )

    license_url = get_metadata_value(
        extmetadata,
        "LicenseUrl"
    )

    creator = get_metadata_value(
        extmetadata,
        "Artist"
    )

    if verification_method == "EXACT_PIXEL_MATCH":
        match_confidence = "EXACT_PIXEL_MATCH"

    elif verification_method == "PERCEPTUAL_HASH_MATCH":
        match_confidence = "HIGH_VISUAL_SIMILARITY"

    elif match_method in [
        "FILENAME_MATCH",
        "THUMBNAIL_FILENAME_MATCH"
    ]:
        match_confidence = "FILENAME_MATCH_ONLY"

    else:
        match_confidence = "DESCRIPTION_SEARCH_CANDIDATE"

    result = {
        "source": "Wikimedia Commons",
        "found": True,
        "file_title": page.get("title"),
        "source_page_url": image_info.get("descriptionurl"),
        "original_file_url": image_info.get("url"),
        "thumbnail_url": image_info.get("thumburl"),
        "match_method": match_method,
        "match_confidence": match_confidence,
        "visual_match_verified": visual_match_verified,
        "verification_method": verification_method,
        "dhash_distance": match_details["dhash_distance"],
        "ahash_distance": match_details["ahash_distance"],
        "creator": creator,
        "uploader": image_info.get("user"),
        "credit": get_metadata_value(
            extmetadata,
            "Credit"
        ),
        "license_name": license_name,
        "license_url": license_url,
        "usage_terms": get_metadata_value(
            extmetadata,
            "UsageTerms"
        ),
        "attribution_required": get_metadata_value(
            extmetadata,
            "AttributionRequired"
        ),
        "copyrighted": get_metadata_value(
            extmetadata,
            "Copyrighted"
        ),
        "date_original": get_metadata_value(
            extmetadata,
            "DateTimeOriginal"
        ),
        "description": get_metadata_value(
            extmetadata,
            "ImageDescription"
        ),
        "permission": get_metadata_value(
            extmetadata,
            "Permission"
        ),
        "source_credit": get_metadata_value(
            extmetadata,
            "Source"
        ),
        "width": image_info.get("width"),
        "height": image_info.get("height"),
        "file_size_bytes": image_info.get("size"),
        "sha1": image_info.get("sha1"),
        "uploaded_version_date": image_info.get("timestamp"),
        "license_listed": bool(
            license_name or license_url
        ),
        "limitations": []
    }

    if verification_method == "EXACT_PIXEL_MATCH":
        result["limitations"].append(
            "The uploaded image pixels exactly match the "
            "corresponding Wikimedia Commons file."
        )

    elif verification_method == "PERCEPTUAL_HASH_MATCH":
        result["limitations"].append(
            "The uploaded image has a strong perceptual similarity "
            "to the Wikimedia Commons file. Resizing or compression "
            "may explain pixel differences. This is not proof of "
            "ownership or an independent legal determination."
        )

    else:
        result["limitations"].append(
            "The Commons result was found through filename or "
            "description search, but visual identity could not "
            "be confirmed."
        )

    result["limitations"].append(
        "Wikimedia Commons metadata is supplied by the file page "
        "and uploader. It should not be treated as an independent "
        "legal determination of ownership."
    )

    return result


def get_file_information(
    title,
    uploaded_bytes=None,
    uploaded_width=None,
    uploaded_height=None,
    match_method="FILENAME_MATCH"
):
    response = api_request({
        "prop": "imageinfo",
        "titles": (
            title
            if title.startswith("File:")
            else f"File:{title}"
        ),
        "iiprop": (
            "url|size|sha1|timestamp|user|extmetadata"
        ),
        "iiextmetadatafilter": (
            "Artist|Credit|LicenseShortName|LicenseUrl|"
            "UsageTerms|AttributionRequired|Copyrighted|"
            "DateTimeOriginal|ImageDescription|Permission|"
            "Source|ObjectName|Restrictions"
        ),
        "iiurlwidth": max(
            1,
            min(uploaded_width or 1280, 4096)
        )
    })

    pages = response.get(
        "query",
        {}
    ).get(
        "pages",
        []
    )

    if not isinstance(pages, list):
        pages = list(pages.values())

    for page in pages:
        if "missing" in page:
            continue

        image_infos = page.get("imageinfo", [])

        if not image_infos:
            continue

        return create_file_result(
            page,
            image_infos[0],
            uploaded_bytes,
            uploaded_width,
            uploaded_height,
            match_method
        )

    return None


def search_commons_by_description(
    description,
    uploaded_bytes,
    uploaded_width,
    uploaded_height
):
    if not description:
        return []

    search_query = re.sub(
        r"\s+",
        " ",
        description
    ).strip()[:250]

    response = api_request({
        "list": "search",
        "srnamespace": 6,
        "srsearch": search_query,
        "srlimit": 10
    })

    search_results = response.get(
        "query",
        {}
    ).get(
        "search",
        []
    )

    matches = []

    for item in search_results:
        title = item.get("title")

        if not title:
            continue

        try:
            result = get_file_information(
                title,
                uploaded_bytes,
                uploaded_width,
                uploaded_height,
                match_method="DESCRIPTION_SEARCH"
            )

            if result:
                matches.append(result)

        except Exception:
            continue

    matches.sort(
        key=lambda item: (
            item.get("visual_match_verified") is True,
            item.get("verification_method") == "EXACT_PIXEL_MATCH"
        ),
        reverse=True
    )

    return matches


def lookup_wikimedia_commons(
    filename,
    uploaded_bytes,
    image_description=None
):
    result = {
        "found": False,
        "source": "Wikimedia Commons",
        "match_method": "NOT_FOUND",
        "matches": [],
        "limitations": []
    }

    try:
        with Image.open(BytesIO(uploaded_bytes)) as image:
            image = ImageOps.exif_transpose(image)
            uploaded_width, uploaded_height = image.size

    except Exception:
        result["limitations"].append(
            "Could not read the uploaded image dimensions."
        )

        return result

    filename_candidates = make_filename_candidates(
        filename
    )

    for candidate in filename_candidates:
        try:
            match_method = (
                "THUMBNAIL_FILENAME_MATCH"
                if re.match(
                    r"^\d+px-",
                    Path(filename).name,
                    re.IGNORECASE
                ) and candidate != Path(filename).name
                else "FILENAME_MATCH"
            )

            match = get_file_information(
                candidate,
                uploaded_bytes,
                uploaded_width,
                uploaded_height,
                match_method
            )

            if match:
                result["found"] = True
                result["match_method"] = match_method
                result["matches"] = [match]

                return result

        except Exception:
            continue

    if image_description:
        try:
            description_matches = search_commons_by_description(
                image_description,
                uploaded_bytes,
                uploaded_width,
                uploaded_height
            )

            if description_matches:
                result["found"] = True
                result["match_method"] = "DESCRIPTION_SEARCH"
                result["matches"] = description_matches

                result["limitations"].append(
                    "These results were discovered using a text "
                    "description. They are possible source matches "
                    "unless visual similarity is independently detected."
                )

                return result

        except Exception:
            pass

    result["limitations"].append(
        "No matching file was found on Wikimedia Commons through "
        "filename or description search."
    )

    return result
