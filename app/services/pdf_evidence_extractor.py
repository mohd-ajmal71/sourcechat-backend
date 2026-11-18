
import re


def extract_evidence(text: str):
    patterns = {
        "copyright_notice": [
            r"©\s*(?:\d{4}(?:\s*[-–]\s*\d{4})?\s*)?(?:[A-Z][A-Za-z0-9&.,' -]{2,})?",
            r"\(c\)\s*\d{4}",
            r"copyright\s*(?:©|\(c\))?\s*(?:\d{4})"
        ],

        "all_rights_reserved": [
            r"all rights reserved"
        ],

        "author": [
            r"written by\s+.{2,}",
            r"author\s*:\s*.+",
            r"authors\s*:\s*.+"
        ],

        "ownership": [
            r"owned by\s+.{2,}",
            r"property of\s+.{2,}",
            r"copyright owner\s*:\s*.+"
        ],

        "license": [
            r"creative commons(?:\s+(?:attribution|sharealike|noncommercial|no derivatives))?",
            r"\bCC BY(?:-SA|-NC|-ND)?(?:\s+\d\.\d)?\b",
            r"\bMIT License\b",
            r"\bApache License(?:\s+Version\s+\d(?:\.\d)?)?\b",
            r"\bGNU General Public License(?:\s+version\s+\d(?:\.\d)?)?\b",
            r"\bGPL(?:v\d(?:\.\d)?)?\b"
        ],

        "public_domain": [
            r"\bin the public domain\b",
            r"\bpublic domain dedication\b",
            r"\bCC0\b"
        ]
    }

    evidence = []

    sentences = re.split(r'(?<=[.!?])\s+|\n+', text)

    for sentence in sentences:
        sentence = sentence.strip()

        if not sentence:
            continue

        for evidence_type, regex_patterns in patterns.items():
            for pattern in regex_patterns:
                if re.search(pattern, sentence, re.IGNORECASE):
                    evidence.append({
                        "type": evidence_type,
                        "text": sentence
                    })
                    break

    return evidence
