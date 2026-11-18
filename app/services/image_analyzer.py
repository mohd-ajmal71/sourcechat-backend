
import json
import re
from pathlib import Path
from io import BytesIO
import xml.etree.ElementTree as ET

from PIL import Image, ExifTags
from google.genai import types

from app.services.llm import client, MODEL_NAME, model
from app.services.source_search import search_external_sources
from app.services.wikimedia_lookup import lookup_wikimedia_commons


MAX_IMAGE_SIZE = 10 * 1024 * 1024

IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp"
}

EXIF_FIELDS = {
    "ImageDescription",
    "Artist",
    "Copyright",
    "DateTime",
    "DateTimeOriginal",
    "DateTimeDigitized",
    "Make",
    "Model",
    "Software",
    "HostComputer",
    "XPTitle",
    "XPComment",
    "XPAuthor",
    "XPKeywords",
    "UserComment",
    "ImageUniqueID",
    "LensModel",
    "OwnerName",
    "CameraOwnerName"
}

XMP_FIELDS = {
    "creator",
    "rights",
    "description",
    "title",
    "date",
    "source",
    "publisher",
    "rightsmarked",
    "webstatement",
    "usageterms",
    "license",
    "licenseurl",
    "credit",
    "artist",
    "author",
    "copyright",
    "createdate"
}

IMAGE_INFO_FIELDS = {
    "title",
    "author",
    "artist",
    "copyright",
    "description",
    "comment",
    "software",
    "source",
    "license",
    "creator",
    "date",
    "creation time"
}


def validate_image_bytes(image_bytes: bytes, extension: str):

    extension = extension.lower()

    if not image_bytes:
        raise ValueError("The uploaded image is empty.")

    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise ValueError("Image size must not exceed 10 MB.")

    if extension not in IMAGE_TYPES:
        raise ValueError(
            "Unsupported image format. Upload JPG, JPEG, PNG or WEBP."
        )

    if extension in [".jpg", ".jpeg"]:
        if not image_bytes.startswith(b"\xff\xd8\xff"):
            raise ValueError("The uploaded file is not a valid JPEG image.")

    elif extension == ".png":
        if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("The uploaded file is not a valid PNG image.")

    elif extension == ".webp":
        if (
            len(image_bytes) < 12
            or image_bytes[:4] != b"RIFF"
            or image_bytes[8:12] != b"WEBP"
        ):
            raise ValueError("The uploaded file is not a valid WEBP image.")

    return IMAGE_TYPES[extension]


def convert_metadata_value(value, field_name=""):

    if value is None:
        return None

    if isinstance(value, bytes):

        if field_name in {
            "XPTitle",
            "XPComment",
            "XPAuthor",
            "XPKeywords"
        }:
            decoded = value.decode(
                "utf-16-le",
                errors="ignore"
            ).rstrip("\x00").strip()

            return decoded or None

        if field_name == "UserComment":

            if value.startswith(b"ASCII\x00\x00\x00"):
                value = value[8:]

            elif value.startswith(b"UNICODE\x00"):
                value = value[8:]

        decoded = value.decode(
            "utf-8",
            errors="replace"
        ).strip("\x00").strip()

        return decoded or None

    if isinstance(value, (tuple, list)):
        return [
            convert_metadata_value(item, field_name)
            for item in value
        ]

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def extract_exif_metadata(image):

    extracted = {}

    try:
        exif = image.getexif()

        if not exif:
            return extracted

        ifd_entries = [exif]

        try:
            ifd_entries.append(
                exif.get_ifd(ExifTags.IFD.Exif)
            )
        except Exception:
            pass

        for ifd in ifd_entries:

            for tag_id, value in ifd.items():

                field_name = ExifTags.TAGS.get(
                    tag_id,
                    str(tag_id)
                )

                if field_name not in EXIF_FIELDS:
                    continue

                converted = convert_metadata_value(
                    value,
                    field_name
                )

                if converted is None or converted == "":
                    continue

                extracted[field_name] = converted

    except Exception:
        pass

    return extracted


def extract_xmp_packet(image_bytes):

    if not image_bytes.startswith(b"\xff\xd8"):
        return None

    xmp_header = b"http://ns.adobe.com/xap/1.0/\x00"

    offset = 2

    while offset < len(image_bytes) - 4:

        if image_bytes[offset] != 0xFF:
            break

        while (
            offset < len(image_bytes)
            and image_bytes[offset] == 0xFF
        ):
            offset += 1

        if offset >= len(image_bytes):
            break

        marker = image_bytes[offset]
        offset += 1

        if marker in [0xD8, 0xD9, 0x01]:
            continue

        if 0xD0 <= marker <= 0xD7:
            continue

        if marker == 0xDA:
            break

        if offset + 2 > len(image_bytes):
            break

        segment_length = int.from_bytes(
            image_bytes[offset:offset + 2],
            "big"
        )

        if segment_length < 2:
            break

        segment_start = offset + 2
        segment_end = offset + segment_length

        if segment_end > len(image_bytes):
            break

        if marker == 0xE1:

            segment = image_bytes[
                segment_start:segment_end
            ]

            header_position = segment.find(xmp_header)

            if header_position != -1:
                return segment[
                    header_position + len(xmp_header):
                ]

        offset = segment_end

    return None


def extract_xmp_metadata(image_bytes, image_info=None):

    extracted = {}

    packet = extract_xmp_packet(image_bytes)

    if not packet and image_info:

        for key, value in image_info.items():

            if str(key).lower() in [
                "xmp",
                "xml:com.adobe.xmp"
            ]:

                if isinstance(value, str):
                    packet = value.encode("utf-8")

                elif isinstance(value, bytes):
                    packet = value

                break

    if not packet:
        return extracted

    try:
        match = re.search(
            rb"<(?:[a-zA-Z0-9_]+:)?xmpmeta\b[\s\S]*?</(?:[a-zA-Z0-9_]+:)?xmpmeta\s*>",
            packet
        )

        if not match:
            return extracted

        root = ET.fromstring(match.group(0))

        for element in root.iter():

            field_name = element.tag.split("}")[-1]
            field_key = field_name.lower()

            if field_key in XMP_FIELDS:

                value = " ".join(
                    text.strip()
                    for text in element.itertext()
                    if text and text.strip()
                )

                if value:
                    extracted.setdefault(
                        field_name,
                        []
                    ).append(value[:1000])

            for attribute_name, attribute_value in element.attrib.items():

                attribute_name = attribute_name.split("}")[-1]
                attribute_key = attribute_name.lower()

                if attribute_key in XMP_FIELDS:

                    value = str(attribute_value).strip()

                    if value:
                        extracted.setdefault(
                            attribute_name,
                            []
                        ).append(value[:1000])

        for key, values in extracted.items():
            extracted[key] = list(dict.fromkeys(values))

    except Exception:
        return {}

    return extracted


def extract_image_text_metadata(image):

    extracted = {}

    try:
        for key, value in image.info.items():

            normalized_key = str(key).strip().lower()

            if normalized_key not in IMAGE_INFO_FIELDS:
                continue

            converted = convert_metadata_value(value, key)

            if converted is None or converted == "":
                continue

            extracted[str(key)] = str(converted)[:1000]

    except Exception:
        pass

    return extracted


def extract_image_metadata(image_bytes: bytes):

    metadata = {
        "embedded_metadata_found": False,
        "metadata_sources": [],
        "image_properties": {},
        "exif": {},
        "xmp": {},
        "image_text_metadata": {},
        "limitations": []
    }

    try:
        with Image.open(BytesIO(image_bytes)) as image:

            metadata["image_properties"] = {
                "format": image.format,
                "width": image.width,
                "height": image.height,
                "mode": image.mode
            }

            exif_data = extract_exif_metadata(image)

            xmp_data = extract_xmp_metadata(
                image_bytes,
                image.info
            )

            image_text_data = extract_image_text_metadata(image)

            metadata["exif"] = exif_data
            metadata["xmp"] = xmp_data
            metadata["image_text_metadata"] = image_text_data

            if exif_data:
                metadata["metadata_sources"].append("EXIF")

            if xmp_data:
                metadata["metadata_sources"].append("XMP")

            if image_text_data:
                metadata["metadata_sources"].append(
                    "Image text metadata"
                )

            metadata["embedded_metadata_found"] = bool(
                exif_data or xmp_data or image_text_data
            )

            if not metadata["embedded_metadata_found"]:
                metadata["limitations"].append(
                    "No relevant embedded EXIF, XMP or image text metadata was found."
                )

            has_creator = any(
                key in exif_data
                for key in ["Artist", "Copyright", "XPAuthor", "OwnerName"]
            )

            has_xmp_creator = any(
                key.lower() in [
                    "creator",
                    "artist",
                    "author",
                    "rights",
                    "copyright"
                ]
                for key in xmp_data
            )

            if not has_creator and not has_xmp_creator:
                metadata["limitations"].append(
                    "No embedded creator or copyright ownership information was found."
                )

    except Exception as error:

        metadata["limitations"].append(
            f"Metadata extraction could not be completed: {str(error)}"
        )

    metadata["limitations"].append(
        "Embedded metadata can be edited or removed and does not independently prove copyright ownership or license validity."
    )

    return metadata


def extract_json_response(response_text):

    if not response_text:
        raise ValueError("Gemini returned an empty response.")

    response_text = response_text.strip()

    response_text = re.sub(
        r"^```(?:json)?\s*",
        "",
        response_text
    )

    response_text = re.sub(
        r"\s*```$",
        "",
        response_text
    )

    start = response_text.find("{")

    if start == -1:
        raise ValueError("No JSON object found in Gemini response.")

    try:
        result, _ = json.JSONDecoder().raw_decode(
            response_text[start:]
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON returned by Gemini: {error}"
        )

    if not isinstance(result, dict):
        raise ValueError("Gemini response must be a JSON object.")

    return result


def add_ai_creator_findings(image_analysis, risk_assessment):

    possible_creators = image_analysis.get(
        "possible_creators_or_owners",
        []
    )

    if not isinstance(possible_creators, list):
        possible_creators = []

    risk_assessment.setdefault("ownership_findings", [])

    if not isinstance(risk_assessment["ownership_findings"], list):
        risk_assessment["ownership_findings"] = []

    existing_findings = risk_assessment["ownership_findings"]

    for creator in possible_creators:

        if not isinstance(creator, str):
            continue

        creator = creator.strip()

        if not creator:
            continue

        finding = (
            f"{creator} — AI-suggested identification based on "
            "visual recognition; not independently verified as "
            "the creator or copyright owner."
        )

        if not any(
            creator.lower() in str(existing).lower()
            for existing in existing_findings
        ):
            existing_findings.append(finding)

    if possible_creators:
        image_analysis["creator_identification_status"] = (
            "AI_SUGGESTED_NOT_VERIFIED"
        )
    else:
        image_analysis["creator_identification_status"] = (
            "NO_CREATOR_IDENTIFIED"
        )

    return image_analysis, risk_assessment


def check_source_and_license_verification(
    external_sources,
    wikimedia_lookup
):

    verified_original_source = False
    verified_license = False

    for source in external_sources:

        if not isinstance(source, dict):
            continue

        if (
            source.get("visual_match_verified") is True
            and source.get("is_original_source") is True
        ):
            verified_original_source = True

        if (
            source.get("license_verified") is True
            and source.get("license_name")
        ):
            verified_license = True

    commons_matches = wikimedia_lookup.get(
        "matches",
        []
    )

    for source in commons_matches:

        if not isinstance(source, dict):
            continue

        if source.get("visual_match_verified") is True:

            verified_original_source = True

            if source.get("license_listed"):
                verified_license = True

    return {
        "original_source": (
            "VERIFIED"
            if verified_original_source
            else "NOT_VERIFIED"
        ),
        "license": (
            "VERIFIED"
            if verified_license
            else "NOT_VERIFIED"
        )
    }


def apply_risk_safeguards(
    risk_assessment,
    external_sources,
    wikimedia_lookup
):

    allowed_risk_levels = {
        "LOW",
        "MEDIUM",
        "HIGH",
        "INCONCLUSIVE"
    }

    if risk_assessment.get("risk_level") not in allowed_risk_levels:
        risk_assessment["risk_level"] = "INCONCLUSIVE"

    verification_status = check_source_and_license_verification(
        external_sources,
        wikimedia_lookup
    )

    risk_assessment["verification_status"] = verification_status

    risk_assessment.setdefault("summary", "")
    risk_assessment.setdefault("copyright_indicators", [])
    risk_assessment.setdefault("possible_source_matches", [])
    risk_assessment.setdefault("ownership_findings", [])
    risk_assessment.setdefault("license_findings", [])
    risk_assessment.setdefault("recommendations", [])
    risk_assessment.setdefault("limitations", [])

    if not isinstance(risk_assessment["recommendations"], list):
        risk_assessment["recommendations"] = []

    if not isinstance(risk_assessment["limitations"], list):
        risk_assessment["limitations"] = []

    source_verified = (
        verification_status["original_source"] == "VERIFIED"
    )

    license_verified = (
        verification_status["license"] == "VERIFIED"
    )

    if not source_verified or not license_verified:

        missing_items = []

        if not source_verified:
            missing_items.append("the original image source")

        if not license_verified:
            missing_items.append("the applicable license")

        explanation = (
            "The system could not verify "
            + " and ".join(missing_items)
            + ". Text-based search results and visually similar images "
            "do not establish the original source or usage rights."
        )

        if explanation not in risk_assessment["limitations"]:
            risk_assessment["limitations"].append(explanation)

        recommendation = (
            "Verify the original source and applicable license before "
            "reusing or publishing this image."
        )

        if recommendation not in risk_assessment["recommendations"]:
            risk_assessment["recommendations"].insert(
                0,
                recommendation
            )

        if risk_assessment["risk_level"] == "LOW":

            risk_assessment["risk_level"] = "INCONCLUSIVE"

            risk_assessment["summary"] = (
                "The image analysis did not identify strong visible "
                "copyright indicators. However, the original source "
                "and applicable license have not both been verified. "
                "Therefore, the copyright and reuse status remains "
                "inconclusive. Absence of a watermark or copyright "
                "notice does not establish that the image is free to use."
            )

    return risk_assessment


def analyze_image(file_path: str):

    image_path = Path(file_path)
    image_bytes = image_path.read_bytes()

    mime_type = validate_image_bytes(
        image_bytes,
        image_path.suffix
    )

    image_metadata = extract_image_metadata(
        image_bytes
    )

    image_prompt = """
You are analyzing an uploaded image for a preliminary
copyright and source verification system.

Carefully inspect the actual image.

IMPORTANT: You must distinguish between information that is
visibly printed in the image and information that you may
recognize from your visual knowledge.

Perform BOTH types of identification:

A. VISIBLE EVIDENCE

Identify information directly visible in the image:

1. Image description.
2. Visible text.
3. Copyright notices and copyright symbols.
4. Watermarks and attribution information.
5. Visible creator, brand or organization names.
6. License names or license references.
7. Distinctive visual elements.

B. VISUAL RECOGNITION

Consider whether the image resembles a well-known:

1. Photograph.
2. Painting or artwork.
3. Illustration.
4. Poster or published image.
5. Image associated with a known photographer, artist
   or organization.

If you genuinely recognize a well-known image, you may
suggest its likely title, artist, photographer or creator.

For visual recognition:

- Only provide a creator name when you have a meaningful
  basis for the identification.
- Do not guess a creator just because the image resembles
  a particular style.
- Distinguish a likely identification from a confirmed match.
- A visual resemblance does not prove that the uploaded
  image is the exact original photograph or artwork.
- Do not treat a photographer as the current copyright owner
  without evidence.
- If you cannot confidently identify a creator, return
  an empty array.

The possible_creators_or_owners field should contain
recognized creator names when appropriate, including
AI-suggested identifications that are not independently
verified.

Do not assume that a logo identifies the copyright owner.
Do not assume that the absence of a watermark means an
image is free to use.
Do not invent text, names, sources or licensing information.

Generate up to three useful text-based web search queries.
Queries may use visible text, recognized artwork titles,
creator names, brands or distinctive image descriptions.

Return only valid JSON using this structure:

{
    "image_description": "Description of the image",
    "visible_text": [],
    "copyright_indicators": [
        {
            "type": "copyright notice, watermark, attribution or license",
            "text": "Visible text",
            "location": "Approximate location in image",
            "interpretation": "What the visible indicator suggests"
        }
    ],
    "possible_creators_or_owners": [],
    "creator_identification_basis": [],
    "brands_or_organizations": [],
    "distinctive_visual_features": [],
    "search_queries": [],
    "limitations": []
}

Use empty arrays when no relevant evidence is available.

Do not place an unverified creator in copyright_indicators.
"""

    image_response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            image_prompt,
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=mime_type
            )
        ],
        config={
            "temperature": 0.2,
            "max_output_tokens": 2500,
            "response_mime_type": "application/json"
        }
    )

    image_analysis = extract_json_response(
        image_response.text
    )

    wikimedia_lookup = lookup_wikimedia_commons(
        filename=image_path.name,
        uploaded_bytes=image_bytes,
        image_description=image_analysis.get(
            "image_description"
        )
    )

    search_queries = image_analysis.get(
        "search_queries",
        []
    )

    if not isinstance(search_queries, list):
        search_queries = []

    normalized_queries = []

    for query in search_queries:

        if isinstance(query, str):
            query = query.strip()

        elif isinstance(query, dict):
            query = str(
                query.get("query")
                or query.get("search_query")
                or ""
            ).strip()

        else:
            continue

        if query and query not in normalized_queries:
            normalized_queries.append(query)

        if len(normalized_queries) >= 3:
            break

    external_sources = []
    seen_urls = set()
    search_errors = []

    for query in normalized_queries:

        try:
            results = search_external_sources(query)

            if isinstance(results, dict):
                results = results.get("results", [])

            if not isinstance(results, list):
                continue

            for source in results:

                if not isinstance(source, dict):
                    continue

                url = str(source.get("url", "")).strip()

                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)

                external_sources.append({
                    "title": source.get("title", ""),
                    "url": url,
                    "content": str(
                        source.get("content", "")
                    )[:1200],
                    "score": source.get("score"),
                    "matched_query": query
                })

                if len(external_sources) >= 5:
                    break

        except Exception:
            search_errors.append(
                "An external source search could not be completed."
            )

        if len(external_sources) >= 5:
            break

    risk_prompt = f"""
You are performing a preliminary copyright-risk assessment
of an uploaded image.

IMAGE ANALYSIS:

{json.dumps(image_analysis, ensure_ascii=False, indent=2)}

EMBEDDED IMAGE METADATA:

{json.dumps(image_metadata, ensure_ascii=False, indent=2)}

WIKIMEDIA COMMONS LOOKUP:

{json.dumps(wikimedia_lookup, ensure_ascii=False, indent=2)}

OTHER EXTERNAL SEARCH RESULTS:

{json.dumps(external_sources, ensure_ascii=False, indent=2)}

ANALYSIS RULES:

1. Explain the copyright-related indicators actually visible
   in the image.

2. Examine embedded EXIF, XMP and image text metadata.
   Identify creator, copyright holder and license information
   found in those fields.

3. Camera make, camera model, capture date and technical
   settings are not proof of copyright ownership.

4. Embedded creator and copyright information can be useful
   clues, but it can be modified or removed.

5. Examine the Wikimedia Commons results when available.

6. If visual_match_verified is true, the image pixels exactly
   match the corresponding Commons file or thumbnail.
   You may treat this as an exact source match.

7. If visual_match_verified is false and match_confidence is
   FILENAME_MATCH_ONLY, report the Commons result as a
   filename-based candidate, not a confirmed image match.

8. If match_confidence is DESCRIPTION_SEARCH_CANDIDATE,
   treat the result only as a possible topical match.

9. Report creator and license information as listed on the
   Commons file page. Do not invent missing details.

10. CC BY-SA licenses require appropriate attribution and
    ShareAlike compliance for adaptations.

11. Other external text-search results are possible sources,
    not proof of exact visual identity.

12. A missing copyright notice or watermark does not mean
    the image is free to use.

13. Do not invent an image creator, owner, license or source.

14. If the first image analysis suggests a known photographer
    or artist based on visual recognition, include that name
    in ownership_findings as an AI-suggested identification.
    Clearly state that it is not independently verified and
    does not establish copyright ownership.

15. Keep these concepts separate:
    - A creator visibly named in the image or metadata.
    - A creator suggested through AI visual recognition.
    - A creator or owner supported by verified source evidence.

16. Do not describe an AI-suggested creator as a confirmed
    copyright holder.

17. Explain uncertainty wherever evidence is insufficient.

18. Provide practical recommendations for image reuse.

RISK LEVELS:

LOW:
The available source and license evidence supports a low
level of identified copyright concern. This does not mean
there are no license obligations.

MEDIUM:
Some copyright, attribution, ownership or licensing
indicators require further verification.

HIGH:
Strong evidence suggests that permission or licensing
should be checked before reuse.

INCONCLUSIVE:
The available information is insufficient for a meaningful
assessment of the image's source or licensing status.

Return only valid JSON using this structure:

{{
    "risk_level": "LOW | MEDIUM | HIGH | INCONCLUSIVE",
    "summary": "Overall preliminary assessment",
    "copyright_indicators": [],
    "possible_source_matches": [
        {{
            "title": "Source title",
            "url": "Source URL",
            "reason": "Why this source may be relevant"
        }}
    ],
    "ownership_findings": [],
    "license_findings": [],
    "recommendations": [],
    "limitations": []
}}

Do not present possible source matches as confirmed matches.
This is a preliminary automated assessment, not legal advice.
"""

    risk_response = model.generate_content(
        risk_prompt,
        generation_config={
            "temperature": 0.2,
            "max_output_tokens": 3000,
            "response_mime_type": "application/json"
        }
    )

    risk_assessment = extract_json_response(
        risk_response.text
    )

    image_analysis, risk_assessment = add_ai_creator_findings(
        image_analysis,
        risk_assessment
    )

    risk_assessment = apply_risk_safeguards(
        risk_assessment,
        external_sources,
        wikimedia_lookup
    )

    if not external_sources:
        risk_assessment["limitations"].append(
            "No usable general external source results were obtained."
        )

    if search_errors:
        risk_assessment["limitations"].append(
            "One or more external searches could not be completed."
        )

    if not normalized_queries:
        risk_assessment["limitations"].append(
            "No useful text-based search queries could be generated."
        )

    return {
        "image_analysis": image_analysis,
        "image_metadata": image_metadata,
        "wikimedia_lookup": wikimedia_lookup,
        "search_queries": normalized_queries,
        "external_sources": external_sources,
        "total_sources": len(external_sources),
        "risk_assessment": risk_assessment
    }
