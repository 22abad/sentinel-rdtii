from __future__ import annotations

import re

from country_detector import detect_country
from schemas import IndicatorMapping
from timeframe_extractor import format_to_month_year


def format_and_clean_mapping(mapping: IndicatorMapping, raw_data: dict, chunk_text: str):
    """Post-processing interceptor to clean and format extracted fields to UN standards."""
    article_clause = (raw_data.get("article_clause") or "").strip()

    if not article_clause:
        leg_title = (raw_data.get("source_legislation") or "").strip()
        match = re.search(
            r"\b(?:Article|Section|Sec|Clause|Paragraph|Para|Ch|Part)\.?\s*(\d+(?:\s*(?:\([^)]+\)|[a-zA-Z]))?)\b",
            leg_title,
            re.IGNORECASE,
        )
        if match:
            article_clause = match.group(0).strip()
        else:
            quote = (raw_data.get("verbatim_quote") or "").strip()
            match = re.match(
                r"^\s*(?:Article|Section|Sec|Clause|Paragraph|Para)\.?\s*(\d+(?:\s*(?:\([^)]+\)|[a-zA-Z]))?)\b",
                quote,
                re.IGNORECASE,
            )
            if match:
                article_clause = match.group(0).strip()
            else:
                match = re.search(
                    r"\b(?:Article|Section|Sec|Clause|Paragraph|Para)\.?\s*(\d+(?:\s*(?:\([^)]+\)|[a-zA-Z]))?)\b",
                    quote,
                    re.IGNORECASE,
                )
                if match:
                    article_clause = match.group(0).strip()

    if article_clause:
        article_clause = re.sub(r"\s+", " ", article_clause).strip()
        article_clause = article_clause.rstrip(".,-:")
        article_clause = article_clause[0].upper() + article_clause[1:] if len(article_clause) > 1 else article_clause.upper()
    mapping.article_clause = article_clause

    source_leg = (raw_data.get("source_legislation") or "").strip()
    if source_leg:
        source_leg = re.sub(
            r"(?i)\s*(?:[-–—:|]|\bof\b)?\s*\b(?:Article|Section|Sec|Clause|Paragraph|Para|Part|Ch)\b\.?\s*\d+.*$",
            "",
            source_leg,
        ).strip()
        source_leg = source_leg.rstrip("-,.:;—– \t")

        country = detect_country(chunk_text, mapping.source_url, source_leg)
        country_name = country.get("name") or ""

        has_country = False
        if country_name:
            adj_map = {
                "Thailand": ["thai"],
                "Malaysia": ["malaysia", "malaysian"],
                "Singapore": ["singapore", "singaporean"],
                "China": ["china", "chinese"],
                "Australia": ["australia", "australian"],
                "India": ["india", "indian"],
                "Philippines": ["philippines", "philippine"],
            }
            search_terms = [country_name.lower()] + adj_map.get(country_name, [])
            has_country = any(term in source_leg.lower() for term in search_terms)

        if country_name and not has_country:
            known_countries = ["thailand", "singapore", "malaysia", "australia", "china", "india"]
            if not any(country in source_leg.lower() for country in known_countries):
                source_leg = f"{country_name} {source_leg}"

        year_match = re.search(r"\b(\d{4})\b", source_leg)
        if year_match:
            year = year_match.group(1)
            idx = year_match.start(1)
            if idx > 1:
                before = source_leg[:idx].rstrip()
                if not before.endswith(","):
                    source_leg = f"{before}, {year}" + source_leg[idx + 4 :]

        source_leg = re.sub(r"\s+", " ", source_leg).strip()
        source_leg = source_leg.rstrip("-, \t")

    mapping.source_legislation = source_leg

    if mapping.article_clause and mapping.impact:
        prefix = f"[{mapping.article_clause}] "
        if not mapping.impact.startswith(prefix):
            mapping.impact = f"{prefix}{mapping.impact}"

    if mapping.last_update:
        formatted_date = format_to_month_year(mapping.last_update)
        if formatted_date:
            mapping.last_update = formatted_date
