"""ForeignAPIRepo: local wiki resolves prod-hosted files it has never imported."""
import pytest
import requests

LOCAL_API = "http://localhost:8080/api.php"
# A file that exists on prod but is NOT uploaded locally.
PROD_ONLY_FILE = "File:Maccabipedia logo.png"


def test_prod_file_resolves_via_foreign_repo():
    try:
        response = requests.get(
            LOCAL_API,
            params={
                "action": "query",
                "titles": PROD_ONLY_FILE,
                "prop": "imageinfo",
                "iiprop": "url",
                "format": "json",
            },
            timeout=60,
        )
    except requests.ConnectionError:
        pytest.skip("local wiki stack is not running")
    response.raise_for_status()
    page = next(iter(response.json()["query"]["pages"].values()))
    assert "imageinfo" in page, f"foreign repo did not resolve {PROD_ONLY_FILE}: {page}"
