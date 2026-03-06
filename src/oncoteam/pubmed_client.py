from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from .config import NCBI_API_KEY, NCBI_BASE_URL
from .models import PubMedArticle


def _base_params() -> dict:
    params: dict = {"retmode": "xml"}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    return params


async def fetch_article(pmid: str) -> PubMedArticle | None:
    """Fetch a single PubMed article by PMID via efetch."""
    async with httpx.AsyncClient(timeout=30) as client:
        params = {**_base_params(), "db": "pubmed", "id": pmid}
        resp = await client.get(f"{NCBI_BASE_URL}/efetch.fcgi", params=params)
        resp.raise_for_status()
        articles = _parse_efetch(resp.text)
        return articles[0] if articles else None


async def search_pubmed(query: str, max_results: int = 10) -> list[PubMedArticle]:
    """Search PubMed via E-utilities: esearch → efetch → parse."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Step 1: esearch to get PMIDs
        params = {**_base_params(), "db": "pubmed", "term": query, "retmax": max_results}
        resp = await client.get(f"{NCBI_BASE_URL}/esearch.fcgi", params=params)
        resp.raise_for_status()

        pmids = _parse_esearch(resp.text)
        if not pmids:
            return []

        # Step 2: efetch to get article details
        params = {**_base_params(), "db": "pubmed", "id": ",".join(pmids)}
        resp = await client.get(f"{NCBI_BASE_URL}/efetch.fcgi", params=params)
        resp.raise_for_status()

        return _parse_efetch(resp.text)


def _parse_esearch(xml_text: str) -> list[str]:
    """Extract PMIDs from esearch XML response."""
    root = ET.fromstring(xml_text)
    return [id_elem.text for id_elem in root.findall(".//Id") if id_elem.text]


def _parse_efetch(xml_text: str) -> list[PubMedArticle]:
    """Parse efetch XML into PubMedArticle models."""
    root = ET.fromstring(xml_text)
    articles = []

    for article_elem in root.findall(".//PubmedArticle"):
        medline = article_elem.find(".//MedlineCitation")
        if medline is None:
            continue

        pmid_elem = medline.find("PMID")
        pmid = pmid_elem.text if pmid_elem is not None and pmid_elem.text else ""

        article = medline.find(".//Article")
        if article is None:
            continue

        title_elem = article.find("ArticleTitle")
        title = title_elem.text if title_elem is not None and title_elem.text else ""

        abstract_elem = article.find(".//AbstractText")
        abstract = abstract_elem.text if abstract_elem is not None and abstract_elem.text else ""

        journal_elem = article.find(".//Journal/Title")
        journal = journal_elem.text if journal_elem is not None and journal_elem.text else ""

        authors = []
        for author in article.findall(".//Author"):
            last = author.find("LastName")
            fore = author.find("ForeName")
            if last is not None and last.text:
                name = last.text
                if fore is not None and fore.text:
                    name = f"{fore.text} {name}"
                authors.append(name)

        pub_date = ""
        date_elem = article.find(".//PubDate")
        if date_elem is not None:
            year = date_elem.find("Year")
            month = date_elem.find("Month")
            if year is not None and year.text:
                pub_date = year.text
                if month is not None and month.text:
                    pub_date = f"{year.text} {month.text}"

        doi = ""
        for eid in article_elem.findall(".//ArticleId"):
            if eid.get("IdType") == "doi" and eid.text:
                doi = eid.text
                break

        articles.append(
            PubMedArticle(
                pmid=pmid,
                title=title,
                abstract=abstract,
                authors=authors,
                journal=journal,
                pub_date=pub_date,
                doi=doi,
            )
        )

    return articles
