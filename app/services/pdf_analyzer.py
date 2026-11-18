
import re
import math
from urllib.parse import urlparse, urlunparse

from app.services.pdf_loader import load_pdf
from app.services.pdf_evidence_extractor import extract_evidence
from app.services.source_search import search_external_sources


STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was",
    "were", "be", "been", "being", "to", "of", "in", "on", "at",
    "for", "with", "by", "from", "as", "that", "this", "these",
    "those", "it", "its", "their", "they", "them", "we", "our",
    "can", "could", "should", "would", "will", "may", "might",
    "has", "have", "had", "do", "does", "did", "not", "which",
    "who", "what", "when", "where", "how", "into", "through",
    "using", "used", "use", "also", "such", "than", "then",
    "more", "most", "some", "any", "all", "each", "other",
    "about", "between", "within", "while", "based", "both",
    "only", "own", "per", "one", "two", "there", "following",
    "document", "documents", "page", "pages", "chapter",
    "section", "figure", "table", "example", "examples"
}


EXCLUDED_PHRASES = [
    "table of contents",
    "submitted by",
    "prepared by",
    "under the guidance",
    "course code",
    "course objectives",
    "grading criteria",
    "progress report",
    "required texts",
    "reference list",
    "bibliography",
    "deliverables",
    "milestones",
    "page number",
    "all rights reserved",
    "preliminary results",
    "implementation status",
    "learning outcomes",
    "expected result",
    "expected output",
    "assignment question",
    "answer the following",
    "discuss with your mentor",
    "submission deadline",
    "date of submission"
]


def clean_pdf_text(text: str):
    text = re.sub(r"(?<=\w)-\s+(?=[A-Za-z])", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_text(text: str):
    text = text.lower()
    text = re.sub(r"(?<=\w)-\s+(?=[a-z])", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_valid_sentence(sentence: str):
    sentence = sentence.strip()

    if len(sentence) < 120 or len(sentence) > 500:
        return False

    lower_sentence = sentence.lower()

    if any(phrase in lower_sentence for phrase in EXCLUDED_PHRASES):
        return False

    if "http://" in lower_sentence or "https://" in lower_sentence:
        return False

    if "www." in lower_sentence:
        return False

    if "[" in sentence or "]" in sentence:
        return False

    if sentence.count(":") > 2:
        return False

    words = re.findall(r"[a-zA-Z]+", sentence)

    if len(words) < 20:
        return False

    meaningful_words = [
        word for word in words
        if word.lower() not in STOP_WORDS and len(word) >= 3
    ]

    if len(meaningful_words) < 10:
        return False

    long_words = [word for word in words if len(word) > 20]

    if len(long_words) > 1:
        return False

    digit_count = sum(char.isdigit() for char in sentence)

    if digit_count / max(len(sentence), 1) > 0.12:
        return False

    if sentence.count("(") > 3 or sentence.count(")") > 3:
        return False

    return True


def extract_page_sentences(text: str):
    text = clean_pdf_text(text)

    sentences = re.split(r"(?<=[.!?])\s+", text)

    return [
        sentence.strip()
        for sentence in sentences
        if is_valid_sentence(sentence)
    ]


def select_search_queries(documents, max_queries: int = 3):
    candidates = []
    word_frequency = {}
    total_sentences = 0

    for page_number, document in enumerate(documents, start=1):
        sentences = extract_page_sentences(document.page_content)

        for sentence in sentences:
            normalized = normalize_text(sentence)
            words = normalized.split()

            meaningful_words = [
                word for word in words
                if word not in STOP_WORDS and len(word) >= 3
            ]

            if len(set(meaningful_words)) < 10:
                continue

            for word in set(meaningful_words):
                word_frequency[word] = word_frequency.get(word, 0) + 1

            candidates.append({
                "sentence": sentence,
                "page": page_number,
                "words": set(meaningful_words)
            })

            total_sentences += 1

    if not candidates:
        return []

    for item in candidates:
        distinctiveness = sum(
            math.log(
                1 + total_sentences / word_frequency.get(word, 1)
            )
            for word in item["words"]
        )

        specific_word_bonus = sum(
            1.5 for word in item["words"]
            if len(word) >= 9
        )

        item["score"] = distinctiveness + specific_word_bonus

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    selected = []
    selected_pages = set()
    seen_sentences = set()

    for item in candidates:
        normalized = normalize_text(item["sentence"])

        if normalized in seen_sentences:
            continue

        if item["page"] in selected_pages:
            continue

        selected.append({
            "sentence": item["sentence"],
            "page": item["page"],
            "score": round(item["score"], 2)
        })

        seen_sentences.add(normalized)
        selected_pages.add(item["page"])

        if len(selected) >= max_queries:
            break

    return selected


def calculate_text_overlap(query: str, source_content: str):
    query_words = {
        word for word in normalize_text(query).split()
        if word not in STOP_WORDS and len(word) >= 3
    }

    source_words = {
        word for word in normalize_text(source_content).split()
        if word not in STOP_WORDS and len(word) >= 3
    }

    if not query_words:
        return 0, []

    matched_terms = sorted(query_words.intersection(source_words))

    overlap = round(
        len(matched_terms) / len(query_words) * 100,
        2
    )

    return overlap, matched_terms


def find_matching_sequences(query: str, source_content: str, n: int = 8):
    query_words = normalize_text(query).split()
    source_words = normalize_text(source_content).split()

    query_grams = {
        tuple(query_words[i:i + n])
        for i in range(len(query_words) - n + 1)
    }

    source_grams = {
        tuple(source_words[i:i + n])
        for i in range(len(source_words) - n + 1)
    }

    matched_grams = query_grams.intersection(source_grams)

    sequences = [
        " ".join(gram)
        for gram in sorted(matched_grams)
    ]

    return sequences[:10]


def normalize_url(url: str):
    try:
        parsed = urlparse(url.strip())

        if not parsed.scheme or not parsed.netloc:
            return url.strip().rstrip("/")

        return urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            parsed.query,
            ""
        ))
    except Exception:
        return url.strip().rstrip("/")


def analyze_pdf(file_path: str):
    documents = load_pdf(file_path)

    all_evidence = []

    for page_number, document in enumerate(documents, start=1):
        evidence = extract_evidence(document.page_content)

        for item in evidence:
            item["page"] = page_number
            all_evidence.append(item)

    metadata = documents[0].metadata if documents else {}

    search_queries = select_search_queries(documents)

    external_sources = []
    seen_urls = set()
    seen_content = set()

    for item in search_queries:
        query = f'"{item["sentence"]}"'

        results = search_external_sources(
            query,
            max_results=5
        )

        for result in results:
            url = result.get("url")

            if not url:
                continue

            normalized_url = normalize_url(url)

            if normalized_url in seen_urls:
                continue

            source_content = result.get("content") or ""
            normalized_content = normalize_text(source_content)

            if not normalized_content:
                continue

            content_signature = normalized_content[:500]

            if content_signature in seen_content:
                continue

            seen_urls.add(normalized_url)
            seen_content.add(content_signature)

            overlap, matched_terms = calculate_text_overlap(
                item["sentence"],
                source_content
            )

            matching_sequences = find_matching_sequences(
                item["sentence"],
                source_content
            )

            result["matched_query"] = query
            result["document_page"] = item["page"]
            result["text_overlap"] = overlap
            result["matched_terms"] = matched_terms
            result["matching_sequences"] = matching_sequences
            result["sequence_match_count"] = len(matching_sequences)

            external_sources.append(result)

    external_sources.sort(
        key=lambda item: (
            item["sequence_match_count"],
            item["text_overlap"],
            float(item.get("score") or 0)
        ),
        reverse=True
    )

    return {
        "metadata": metadata,
        "evidence": all_evidence,
        "search_queries": search_queries,
        "external_sources": external_sources[:5],
        "total_pages": len(documents),
        "total_evidence": len(all_evidence)
    }
