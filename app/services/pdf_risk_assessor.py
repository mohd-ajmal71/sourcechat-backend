
import json
import re
from app.services.llm import model


LICENSE_CLASSIFICATIONS = {
    "DOCUMENT_WIDE_LICENSE",
    "SECTION_SPECIFIC_LICENSE",
    "LICENSE_TEMPLATE_OR_EXAMPLE",
    "PUBLIC_DOMAIN_CONTENT",
    "COPYRIGHT_RESERVED",
    "LICENSE_SCOPE_UNCLEAR"
}


def prepare_assessment_data(verification_report):
    evidence = verification_report.get("evidence", [])
    external_sources = verification_report.get("external_sources", [])
    search_queries = verification_report.get("search_queries", [])

    unique_evidence = []
    seen_evidence = set()

    for item in evidence:
        evidence_type = item.get("type", "unknown")
        page = item.get("page")
        evidence_text = str(item.get("text", "")).strip()

        normalized_text = re.sub(
            r"\s+",
            " ",
            evidence_text
        ).lower()

        key = (
            evidence_type,
            page,
            normalized_text
        )

        if key in seen_evidence:
            continue

        seen_evidence.add(key)

        unique_evidence.append({
            "type": evidence_type,
            "page": page,
            "text": evidence_text[:350]
        })

        if len(unique_evidence) >= 40:
            break

    selected_sources = []

    for source in external_sources[:5]:
        selected_sources.append({
            "title": source.get("title", ""),
            "url": source.get("url", ""),
            "content": str(source.get("content", ""))[:1200],
            "document_page": source.get("document_page"),
            "text_overlap": source.get("text_overlap", 0),
            "matched_terms": source.get("matched_terms", [])[:15],
            "matching_sequences": source.get("matching_sequences", [])[:5],
            "sequence_match_count": source.get("sequence_match_count", 0)
        })

    selected_queries = []

    for query in search_queries[:3]:
        selected_queries.append({
            "sentence": str(query.get("sentence", ""))[:700],
            "page": query.get("page"),
            "score": query.get("score")
        })

    metadata = verification_report.get("metadata", {})

    return {
        "metadata": {
            "source": str(metadata.get("source", "")),
            "page": metadata.get("page")
        },
        "total_pages": verification_report.get("total_pages", 0),
        "total_evidence": verification_report.get("total_evidence", len(evidence)),
        "evidence_included": len(unique_evidence),
        "evidence": unique_evidence,
        "search_queries": selected_queries,
        "external_sources": selected_sources
    }


def extract_json_response(response_text):
    if not response_text:
        raise ValueError("Gemini returned an empty response")

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
        raise ValueError("No JSON object found in Gemini response")

    try:
        result, _ = json.JSONDecoder().raw_decode(
            response_text[start:]
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON returned by Gemini: {error}"
        )

    if not isinstance(result, dict):
        raise ValueError("Gemini response must be a JSON object")

    return result


def apply_license_scope_safeguards(assessment, evidence):
    document_scope_phrases = [
        "entire document",
        "whole document",
        "throughout this document",
        "entire publication",
        "whole publication",
        "throughout this publication",
        "this publication is licensed under",
        "this document is licensed under",
        "this work is licensed under",
        "this work is available open access by complying with"
    ]

    license_grant_phrases = [
        "licensed under",
        "licenced under",
        "available under the terms",
        "made available under",
        "distributed under",
        "released under",
        "open access under",
        "reuse is permitted under",
        "this work is available open access by complying with"
    ]

    evidence_text = " ".join(
        str(item.get("text", ""))
        for item in evidence
        if isinstance(item, dict)
    ).lower()

    for item in assessment:
        if not isinstance(item, dict):
            continue

        classification = str(
            item.get("classification", "")
        ).upper()

        if classification not in LICENSE_CLASSIFICATIONS:
            classification = "LICENSE_SCOPE_UNCLEAR"

        item["classification"] = classification

        supporting_evidence = item.get(
            "supporting_evidence",
            []
        )

        if not isinstance(supporting_evidence, list):
            supporting_evidence = []

        item["supporting_evidence"] = supporting_evidence

        uncertainties = item.get("uncertainties", [])

        if not isinstance(uncertainties, list):
            uncertainties = [str(uncertainties)]

        item["uncertainties"] = uncertainties

        scope = str(item.get("scope", "")).lower()

        has_document_scope = any(
            phrase in evidence_text
            for phrase in document_scope_phrases
        )

        has_license_grant = any(
            phrase in evidence_text
            for phrase in license_grant_phrases
        )

        has_template_reference = any(
            phrase in evidence_text
            for phrase in [
                "annex",
                "template",
                "sample",
                "example",
                "model license"
            ]
        )

        if classification == "DOCUMENT_WIDE_LICENSE":
            if not has_document_scope or not has_license_grant:
                item["classification"] = "LICENSE_SCOPE_UNCLEAR"
                item["scope"] = "Unclear"

                uncertainties.append(
                    "The available evidence does not explicitly establish "
                    "that the license applies to the entire document."
                )

        elif classification == "SECTION_SPECIFIC_LICENSE":
            if not has_license_grant:
                if has_template_reference:
                    item["classification"] = (
                        "LICENSE_TEMPLATE_OR_EXAMPLE"
                    )

                    item["scope"] = "Template/example only"

                    uncertainties.append(
                        "The license text appears to be included as a "
                        "template or example. Its application to actual "
                        "document content is not established."
                    )

                else:
                    item["classification"] = "LICENSE_SCOPE_UNCLEAR"
                    item["scope"] = "Unclear"

                    uncertainties.append(
                        "The evidence identifies a license but does not "
                        "clearly establish that it applies to this section."
                    )

        elif classification == "COPYRIGHT_RESERVED":
            if "document-wide" in scope or "entire document" in scope:
                if not has_document_scope:
                    item["scope"] = "Unclear"

                    uncertainties.append(
                        "Copyright notices were identified on specific "
                        "pages, but their applicability to the entire "
                        "document is not established."
                    )

        elif classification == "LICENSE_TEMPLATE_OR_EXAMPLE":
            item["scope"] = "Template/example only"

        elif classification == "LICENSE_SCOPE_UNCLEAR":
            item["scope"] = "Unclear"

        item.setdefault("license_name", "Not identified")
        item.setdefault("license_version", "Unspecified")
        item.setdefault("applicable_pages", [])
        item.setdefault("applicable_section", "Not identified")

    return assessment


def apply_risk_level_safeguards(result, evidence):
    license_info = result.get("license_assessment", {})

    if not isinstance(license_info, dict):
        license_info = {}

    scope_assessment = result.get(
        "license_scope_assessment",
        []
    )

    if not isinstance(scope_assessment, list):
        scope_assessment = []

    evidence_assessment = result.get(
        "evidence_assessment",
        []
    )

    if not isinstance(evidence_assessment, list):
        evidence_assessment = []

    identified_licenses = license_info.get(
        "identified_licenses",
        []
    )

    if not isinstance(identified_licenses, list):
        identified_licenses = []

    concerns = license_info.get("concerns", [])

    if not isinstance(concerns, list):
        concerns = [str(concerns)]

    classifications = {
        str(item.get("classification", "")).upper()
        for item in scope_assessment
        if isinstance(item, dict)
    }

    evidence_text_parts = []

    for item in evidence:
        if isinstance(item, dict):
            evidence_text_parts.append(
                str(item.get("text", ""))
            )

    for item in evidence_assessment:
        if isinstance(item, dict):
            evidence_text_parts.append(
                str(item.get("finding", ""))
            )

    evidence_text_parts.extend(
        str(concern)
        for concern in concerns
    )

    evidence_text = " ".join(evidence_text_parts).lower()

    reserved_phrases = [
        "all rights reserved",
        "rights reserved",
        "copyright reserved"
    ]

    has_reserved_notice = (
        "COPYRIGHT_RESERVED" in classifications
        or any(
            phrase in evidence_text
            for phrase in reserved_phrases
        )
    )

    license_names = []

    for license_name in identified_licenses:
        if isinstance(license_name, dict):
            name = str(
                license_name.get("name", "")
            ).strip()
        else:
            name = str(license_name).strip()

        if name.lower() not in {
            "",
            "not identified",
            "unknown",
            "unspecified",
            "none"
        }:
            license_names.append(name)

    for item in scope_assessment:
        if isinstance(item, dict):
            name = str(
                item.get("license_name", "")
            ).strip()

            if name.lower() not in {
                "",
                "not identified",
                "unknown",
                "unspecified",
                "none"
            }:
                license_names.append(name)

    has_document_wide_license = (
        "DOCUMENT_WIDE_LICENSE" in classifications
        and bool(license_names)
    )

    current_risk = str(
        result.get("risk_level", "INCONCLUSIVE")
    ).upper()

    if current_risk not in {
        "LOW",
        "MEDIUM",
        "HIGH",
        "INCONCLUSIVE"
    }:
        current_risk = "INCONCLUSIVE"

    if has_reserved_notice and not has_document_wide_license:
        result["risk_level"] = "HIGH"

        result["summary"] = (
            "High copyright and licensing risk. The document contains "
            "an explicit copyright-reserved or all-rights-reserved notice, "
            "and an applicable document-wide reuse license has not been "
            "established. Permission should be verified before reusing "
            "the protected content."
        )

    elif classifications.intersection({
        "LICENSE_SCOPE_UNCLEAR",
        "LICENSE_TEMPLATE_OR_EXAMPLE",
        "SECTION_SPECIFIC_LICENSE"
    }):
        if current_risk in {"LOW", "INCONCLUSIVE"}:
            result["risk_level"] = "MEDIUM"

            existing_summary = str(
                result.get("summary", "")
            ).strip()

            additional_summary = (
                "The license scope is unclear, limited to a section, "
                "or appears in a template/example. Its applicability "
                "to the content being reused should be verified."
            )

            result["summary"] = (
                f"{existing_summary} {additional_summary}"
                if existing_summary
                else additional_summary
            )

    return result


def assess_copyright_risk(verification_report):
    assessment_data = prepare_assessment_data(
        verification_report
    )

    prompt = f"""
You are an AI assistant performing preliminary copyright and
license-risk analysis of an uploaded PDF.

Analyze the supplied document evidence and external source matches.

DOCUMENT INFORMATION:

{json.dumps(assessment_data, ensure_ascii=False, indent=2)}

IMPORTANT ANALYSIS RULES:

1. ORIGINAL SOURCE MATCHING

- Identify whether an external source is the same document
  as the uploaded PDF.
- An exact match to the original document is not evidence
  of copyright infringement.
- High text overlap alone does not prove infringement.
- Standard legal wording and common terminology can produce
  legitimate text similarities.
- Do not describe partial similarity as confirmed copying.

2. COPYRIGHT EVIDENCE

- Identify copyright notices, ownership information,
  all-rights-reserved statements and author references.
- Do not assume that a copyright notice on one page
  automatically applies to every page.
- Do not assume that copyright ownership means reuse is
  always prohibited.
- Report the actual evidence and its page numbers.

3. LICENSE SCOPE CLASSIFICATION

Classify each meaningful license-related finding using
one of these exact classifications:

DOCUMENT_WIDE_LICENSE:

Use only when there is explicit evidence that a license
applies to the entire uploaded document or publication.

SECTION_SPECIFIC_LICENSE:

Use only when evidence explicitly establishes that a license
applies to a particular section, annex, contribution or part.

LICENSE_TEMPLATE_OR_EXAMPLE:

Use when sample license text, model license terms,
copyright-page examples or licensing templates are included.

The presence of a license's legal text does not automatically
mean the uploaded document is licensed under it.

PUBLIC_DOMAIN_CONTENT:

Use only when evidence establishes that particular content
is actually in the public domain.

A general discussion of public-domain material is insufficient.

COPYRIGHT_RESERVED:

Use when an explicit copyright-reserved or all-rights-reserved
notice is identified.

LICENSE_SCOPE_UNCLEAR:

Use when a license is mentioned but its actual applicability
cannot be established.

4. IMPORTANT LICENSE RULES

- A Creative Commons license mentioned in a document does
  not automatically apply to the entire document.
- A license reproduced in an annex may be a template or example.
- A sample copyright notice is not proof of the actual license
  applied to the uploaded publication.
- Do not infer a document-wide license from a section-specific
  license.
- Do not infer document-wide copyright scope merely because
  copyright notices appear on multiple pages.
- When the available evidence is insufficient, state that
  the scope is unclear.
- Use only evidence and page numbers provided in the input.
- Do not invent license versions, permissions, owners or dates.

5. OWNERSHIP AND RISK

- Identify ownership only when supported by evidence.
- Distinguish original material from third-party contributions.
- Explain any uncertainty about ownership or licensing.
- Do not treat external legal references as proof of infringement.
- Do not make definitive legal conclusions.

6. RECOMMENDATIONS

Provide practical recommendations based on the findings.

Mention when a user should verify the license of a particular
publication or section before reusing it.

RETURN ONLY VALID JSON.

Use exactly this structure:

{{
    "risk_level": "LOW | MEDIUM | HIGH | INCONCLUSIVE",
    "summary": "Brief overall assessment",
    "original_source_matches": [
        {{
            "title": "Source title",
            "url": "Source URL",
            "reason": "Why this source is considered the original"
        }}
    ],
    "evidence_assessment": [
        {{
            "type": "Evidence type",
            "page": 0,
            "finding": "Explanation of the evidence"
        }}
    ],
    "source_assessment": [
        {{
            "title": "Source title",
            "url": "Source URL",
            "document_page": 0,
            "text_overlap": 0,
            "sequence_match_count": 0,
            "match_type": "ORIGINAL_DOCUMENT | PARTIAL_MATCH | UNCERTAIN | NO_MATCH",
            "reason": "Explanation"
        }}
    ],
    "license_assessment": {{
        "identified_licenses": [],
        "ownership_findings": [],
        "concerns": []
    }},
    "license_scope_assessment": [
        {{
            "classification": "LICENSE_SCOPE_UNCLEAR",
            "license_name": "License name if identified",
            "license_version": "Version if identified",
            "applicable_pages": [],
            "applicable_section": "Section or annex if identified",
            "scope": "Document-wide, section-specific, template/example only or unclear",
            "supporting_evidence": [],
            "uncertainties": []
        }}
    ],
    "recommendations": [],
    "limitations": []
}}

Make sure every classification in license_scope_assessment
uses one of the six exact classification values provided above.

Do not invent evidence. If no license scope finding can be
established, return an empty license_scope_assessment list.

This is a preliminary automated assessment, not legal advice.
"""

    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.2,
            "max_output_tokens": 5000,
            "response_mime_type": "application/json"
        }
    )

    result = extract_json_response(response.text)

    required_fields = [
        "risk_level",
        "summary",
        "original_source_matches",
        "evidence_assessment",
        "source_assessment",
        "license_assessment",
        "license_scope_assessment",
        "recommendations",
        "limitations"
    ]

    missing_fields = [
        field
        for field in required_fields
        if field not in result
    ]

    if missing_fields:
        raise ValueError(
            f"Gemini response is missing fields: {missing_fields}"
        )

    allowed_risk_levels = {
        "LOW",
        "MEDIUM",
        "HIGH",
        "INCONCLUSIVE"
    }

    if result["risk_level"] not in allowed_risk_levels:
        result["risk_level"] = "INCONCLUSIVE"

    if not isinstance(result["license_scope_assessment"], list):
        raise ValueError(
            "Invalid license_scope_assessment returned by Gemini"
        )

    result["license_scope_assessment"] = apply_license_scope_safeguards(
        result["license_scope_assessment"],
        assessment_data["evidence"]
    )

    result = apply_risk_level_safeguards(
        result,
        assessment_data["evidence"]
    )

    return result
