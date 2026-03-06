import pytest
import respx
from httpx import Response

from oncoteam.config import NCBI_BASE_URL
from oncoteam.pubmed_client import _parse_efetch, _parse_esearch, fetch_article, search_pubmed

ESEARCH_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>2</Count>
  <RetMax>2</RetMax>
  <IdList>
    <Id>12345678</Id>
    <Id>87654321</Id>
  </IdList>
</eSearchResult>"""

EFETCH_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345678</PMID>
      <Article>
        <ArticleTitle>FOLFOX in colorectal cancer treatment</ArticleTitle>
        <Abstract>
          <AbstractText>A study on FOLFOX efficacy in sigmoid colon cancer.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Smith</LastName>
            <ForeName>John</ForeName>
          </Author>
        </AuthorList>
        <Journal>
          <Title>Journal of Oncology</Title>
        </Journal>
        <ArticleDate>
          <Year>2025</Year>
          <Month>06</Month>
        </ArticleDate>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1234/test.2025</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>87654321</PMID>
      <Article>
        <ArticleTitle>Oxaliplatin neurotoxicity management</ArticleTitle>
        <Journal>
          <Title>Cancer Research</Title>
        </Journal>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""


class TestParseEsearch:
    def test_extracts_pmids(self):
        pmids = _parse_esearch(ESEARCH_RESPONSE)
        assert pmids == ["12345678", "87654321"]

    def test_empty_result(self):
        xml = "<eSearchResult><IdList></IdList></eSearchResult>"
        assert _parse_esearch(xml) == []


class TestParseEfetch:
    def test_parses_articles(self):
        articles = _parse_efetch(EFETCH_RESPONSE)
        assert len(articles) == 2

        first = articles[0]
        assert first.pmid == "12345678"
        assert "FOLFOX" in first.title
        assert "sigmoid" in first.abstract
        assert first.authors == ["John Smith"]
        assert first.journal == "Journal of Oncology"
        assert first.doi == "10.1234/test.2025"

    def test_article_with_missing_fields(self):
        articles = _parse_efetch(EFETCH_RESPONSE)
        second = articles[1]
        assert second.pmid == "87654321"
        assert second.abstract == ""
        assert second.authors == []


class TestSearchPubmed:
    @respx.mock
    @pytest.mark.asyncio
    async def test_search_returns_articles(self):
        respx.get(f"{NCBI_BASE_URL}/esearch.fcgi").mock(
            return_value=Response(200, text=ESEARCH_RESPONSE)
        )
        respx.get(f"{NCBI_BASE_URL}/efetch.fcgi").mock(
            return_value=Response(200, text=EFETCH_RESPONSE)
        )

        articles = await search_pubmed("colorectal cancer FOLFOX", max_results=2)
        assert len(articles) == 2
        assert articles[0].pmid == "12345678"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_no_results(self):
        empty = "<eSearchResult><IdList></IdList></eSearchResult>"
        respx.get(f"{NCBI_BASE_URL}/esearch.fcgi").mock(return_value=Response(200, text=empty))

        articles = await search_pubmed("nonexistent query xyz")
        assert articles == []


class TestFetchArticle:
    @respx.mock
    @pytest.mark.asyncio
    async def test_fetches_single_article(self):
        respx.get(f"{NCBI_BASE_URL}/efetch.fcgi").mock(
            return_value=Response(200, text=EFETCH_RESPONSE)
        )

        article = await fetch_article("12345678")
        assert article is not None
        assert article.pmid == "12345678"
        assert "FOLFOX" in article.title

    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        empty = '<?xml version="1.0"?><PubmedArticleSet></PubmedArticleSet>'
        respx.get(f"{NCBI_BASE_URL}/efetch.fcgi").mock(
            return_value=Response(200, text=empty)
        )

        article = await fetch_article("00000000")
        assert article is None
