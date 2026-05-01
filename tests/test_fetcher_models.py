from src.fetcher.models import (
    Article,
    filter_supported_articles,
    is_supported_article_language,
)


def test_filter_supported_articles_detects_unlabeled_languages() -> None:
    filtered = filter_supported_articles(
        [
            Article(
                title="Nvidia demand stays firm",
                body="Customers still expect strong AI server orders this quarter.",
                url="https://example.com/en",
                source="Reuters",
                published_at="2026-04-26T07:30:00+00:00",
                raw_tags=("NVDA",),
            ),
            Article(
                title="La demanda de Nvidia sigue firme",
                body="Los clientes mantienen pedidos solidos de servidores de IA.",
                url="https://example.com/es",
                source="Expansion",
                published_at="2026-04-26T07:00:00+00:00",
                raw_tags=("NVDA",),
            ),
            Article(
                title="La demande de Nvidia reste solide",
                body="Les clients continuent d'augmenter les commandes de serveurs.",
                url="https://example.com/fr",
                source="Les Echos",
                published_at="2026-04-26T06:30:00+00:00",
                raw_tags=("NVDA",),
            ),
            Article(
                title="Спрос на Nvidia остается высоким",
                body="Клиенты продолжают увеличивать заказы на серверы ИИ.",
                url="https://example.com/ru",
                source="РБК",
                published_at="2026-04-26T06:00:00+00:00",
                raw_tags=("NVDA",),
            ),
        ]
    )

    assert [article.url for article in filtered] == [
        "https://example.com/en",
        "https://example.com/es",
        "https://example.com/ru",
    ]


def test_supported_article_language_uses_detector_for_ambiguous_metadata() -> None:
    article = Article(
        title="Nvidia demand remains strong in Europe",
        body="Channel checks still point to resilient AI infrastructure budgets.",
        url="https://example.com/ambiguous",
        source="Bloomberg",
        published_at="2026-04-26T06:00:00+00:00",
        raw_tags=("NVDA",),
        language="und",
    )

    assert is_supported_article_language(article) is True


def test_supported_article_language_allows_short_russian_fallback() -> None:
    article = Article(
        title="Спрос высок",
        body="",
        url="https://example.com/short-ru",
        source="РБК",
        published_at="2026-04-26T06:00:00+00:00",
        raw_tags=("NVDA",),
    )

    assert is_supported_article_language(article) is True
