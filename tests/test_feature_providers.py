from media_importer.features.providers import (
    DimensionMapping,
    TMDbProvider,
    create_providers,
    get_provider_class,
)


class FakeTMDbClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def search_movie_list(self, query, year=None):
        return {
            "total_results": 1,
            "results": [
                {
                    "id": 101,
                    "title": "Inception",
                    "original_title": "Inception",
                    "release_date": "2010-07-16",
                    "poster_path": "/poster.jpg",
                    "vote_average": 8.4,
                }
            ],
        }

    def search_tv_list(self, query, year=None):
        return {"total_results": 0, "results": []}

    def get_movie_details(self, item_id):
        return {
            "id": item_id,
            "title": "Inception",
            "original_title": "Inception",
            "release_date": "2010-07-16",
            "genres": [{"id": 878, "name": "Science Fiction"}],
            "overview": "A thief enters dreams.",
            "vote_average": 8.4,
            "origin_country": ["US"],
            "original_language": "en",
            "adult": False,
            "tagline": "Your mind is the scene of the crime.",
            "poster_path": "/poster.jpg",
        }

    def get_tv_details(self, item_id):
        raise AssertionError("TV details should not be called")

    def get_movie_alternative_titles(self, item_id):
        return [{"title": "As Far as My Feet Will Carry Me"}, {"title": ""}]

    def get_tv_alternative_titles(self, item_id):
        return []

    def get_movie_release_dates(self, item_id):
        return [
            {
                "iso_3166_1": "US",
                "release_dates": [{"certification": "PG-13"}],
            }
        ]

    def get_tv_release_dates(self, item_id):
        return []

    def get_genre_list(self):
        return [{"id": 878, "name": "Science Fiction"}]

    def test_connection(self):
        return True


def test_provider_registry_creates_tmdb_provider_with_mock_client(monkeypatch):
    created_kwargs = []

    def fake_client_factory(**kwargs):
        created_kwargs.append(kwargs)
        return FakeTMDbClient(**kwargs)

    monkeypatch.setattr(
        "media_importer.features.providers.tmdb_provider.TMDbClient",
        fake_client_factory,
    )

    providers = create_providers({
        "metadata": {
            "providers": [
                {
                    "type": "tmdb",
                    "enabled": True,
                    "api_key": "test-key",
                    "language": "zh-CN",
                    "fallback_language": "en-US",
                    "request_timeout": 5,
                    "max_retries": 1,
                }
            ]
        }
    })

    assert get_provider_class("tmdb") is TMDbProvider
    assert len(providers) == 1
    assert isinstance(providers[0], TMDbProvider)
    assert created_kwargs[0]["api_key"] == "test-key"
    assert created_kwargs[0]["timeout"] == 5


# Requirement: REQ-20260831-235616
def test_tmdb_config_schema_requests_v3_api_key_instead_of_read_token():
    schema = TMDbProvider.get_config_schema()
    api_key = next(field for field in schema["fields"] if field["key"] == "api_key")

    assert api_key["label"] == "API Key（v3 auth）"
    assert "不要填写" in api_key["description"]
    assert "API Read Access Token" in api_key["description"]


def test_tmdb_provider_search_details_and_dimension_mapping(monkeypatch):
    monkeypatch.setattr(
        "media_importer.features.providers.tmdb_provider.TMDbClient",
        FakeTMDbClient,
    )
    provider = TMDbProvider({"api_key": "test-key"})

    search_result = provider.search("Inception", media_type="movie")
    assert search_result.total_results == 1
    assert search_result.items[0].item_id == "101"
    assert search_result.items[0].year == 2010

    details = provider.get_details("101", "movie")
    assert details.title == "Inception"
    assert details.genres[0].id == "878"
    assert provider.get_alternative_titles("101", "movie") == [
        "As Far as My Feet Will Carry Me"
    ]

    mappings = provider.map_dimensions(
        [
            {
                "name": "restricted_level",
                "value_list": [],
                "provider_mappings": {
                    "tmdb": {"match_type": "certification"}
                },
            }
        ],
        details,
    )

    assert mappings == [
        DimensionMapping(
            name="restricted_level",
            value="13-16",
            source_reliability=1.0,
            source="tmdb",
        )
    ]
