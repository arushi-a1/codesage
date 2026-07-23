import pytest

from app.services.github_service import GitHubError, parse_repo_full_name


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/openai/gpt-4", "openai/gpt-4"),
        ("https://github.com/openai/gpt-4.git", "openai/gpt-4"),
        ("git@github.com:openai/gpt-4.git", "openai/gpt-4"),
        ("https://github.com/openai/gpt-4/", "openai/gpt-4"),
    ],
)
def test_parse_repo_full_name_valid(url, expected):
    assert parse_repo_full_name(url) == expected


def test_parse_repo_full_name_invalid_url_raises():
    with pytest.raises(GitHubError):
        parse_repo_full_name("https://gitlab.com/foo/bar")
