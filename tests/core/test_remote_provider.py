
from unittest.mock import MagicMock, patch

import pytest
import requests

from astra.core.remote_provider import RemoteTemplateProvider


@pytest.fixture
def mock_config_obj():
    config = MagicMock()
    config.skills_mp.api_key = "test_key"
    config.skills_mp.endpoint = "https://api.skillsmp.com"
    config.skills_mp.enabled = True
    config.skills_mp.cache_expiry_hours = 1
    return config

@pytest.fixture
def provider(mock_config_obj, tmp_path):
    with patch("astra.core.remote_provider.get_config", return_value=mock_config_obj):
        return RemoteTemplateProvider(cache_dir=tmp_path / "cache")


def test_init_creates_cache_dir(mock_config_obj, tmp_path):
    with patch("astra.core.remote_provider.get_config", return_value=mock_config_obj):
        cache_dir = tmp_path / "custom_cache"
        RemoteTemplateProvider(cache_dir=cache_dir)
        assert cache_dir.exists()
        assert (cache_dir / "index_cache.json").parent.exists()


def test_is_enabled(mock_config_obj, tmp_path):
    with patch("astra.core.remote_provider.get_config", return_value=mock_config_obj):
        # Case 1: All good
        provider = RemoteTemplateProvider(cache_dir=tmp_path)
        assert provider.is_enabled()

        # Case 2: Config disabled
        mock_config_obj.skills_mp.enabled = False
        provider = RemoteTemplateProvider(cache_dir=tmp_path)
        assert not provider.is_enabled()

        mock_config_obj.skills_mp.enabled = True

        # Case 3: API Key missing
        mock_config_obj.skills_mp.api_key = ""
        provider = RemoteTemplateProvider(cache_dir=tmp_path)
        assert not provider.is_enabled()


@patch("requests.get")
def test_search_success(mock_get, provider):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": {
            "skills": [
                {"name": "skill1"},
                {"name": "skill2"}
            ]
        }
    }
    mock_get.return_value = mock_response

    results = provider.search("python", limit=2)

    assert len(results) == 2
    assert results[0]["name"] == "skill1"

    # Check call arguments ensuring URL is correct
    # The code does f"{self._base_url}{endpoint}"
    # base="https://api.skillsmp.com", endpoint="/skills/search"
    # Result should be "https://api.skillsmp.com/skills/search"

    expected_url = "https://api.skillsmp.com/skills/search"
    args, kwargs = mock_get.call_args
    assert args[0] == expected_url
    assert kwargs["params"] == {"q": "python", "limit": 2}


def test_search_disabled(mock_config_obj, tmp_path):
    mock_config_obj.skills_mp.enabled = False
    with patch("astra.core.remote_provider.get_config", return_value=mock_config_obj):
        p = RemoteTemplateProvider(cache_dir=tmp_path)
        assert p.search("python") == []


@patch("requests.get")
def test_search_failure(mock_get, provider):
    mock_get.side_effect = requests.RequestException("Network error")
    results = provider.search("python")
    assert results == []


@patch("requests.get")
def test_search_use_ai(mock_get, provider):
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"skills": []}}
    mock_get.return_value = mock_response

    provider.search("python", use_ai=True)

    expected_url = "https://api.skillsmp.com/skills/ai-search"
    args, kwargs = mock_get.call_args
    assert args[0] == expected_url


def test_fetch_content_disabled(mock_config_obj, tmp_path):
    mock_config_obj.skills_mp.enabled = False
    with patch("astra.core.remote_provider.get_config", return_value=mock_config_obj):
        p = RemoteTemplateProvider(cache_dir=tmp_path)
        assert p.fetch_content("skill-1") is None


def test_fetch_content_cached_valid(provider, tmp_path):
    cache_file = provider._cache_dir / "skill-1.md"
    cache_file.write_text("Cached Content", encoding="utf-8")

    # Mocking time.time
    # Note: RemoteTemplateProvider imports time. Use patch("astra.core.remote_provider.time.time") if needed?
    # No, it imports `import time`. So `time.time()` is called.
    # patching `time.time` globally works.

    with patch("time.time", return_value=cache_file.stat().st_mtime + 10):
        content = provider.fetch_content("skill-1")
        assert content == "Cached Content"


def test_fetch_content_cached_stale(provider, tmp_path):
    cache_file = provider._cache_dir / "skill-1.md"
    cache_file.write_text("Old Content", encoding="utf-8")

    future_time = cache_file.stat().st_mtime + 3600 + 100

    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"content": "New Content"}}
        mock_get.return_value = mock_response

        with patch("time.time", return_value=future_time):
             content = provider.fetch_content("skill-1")

        assert content == "New Content"
        assert cache_file.read_text(encoding="utf-8") == "New Content"


@patch("requests.get")
def test_fetch_content_api_success(mock_get, provider):
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"content": "Remote Content"}}
    mock_get.return_value = mock_response

    content = provider.fetch_content("skill-new")
    assert content == "Remote Content"

    # Verify it was cached
    assert (provider._cache_dir / "skill-new.md").read_text(encoding="utf-8") == "Remote Content"


@patch("requests.get")
def test_fetch_content_api_failure(mock_get, provider):
    mock_get.side_effect = requests.RequestException("Error")

    assert provider.fetch_content("skill-fail") is None
