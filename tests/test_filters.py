"""Tests for utils.filters — low-signal PR comment detection."""
import pytest

from utils.filters import is_bot_user, is_low_signal_body, is_low_signal_comment


class TestIsBotUser:
    def test_empty_user_is_not_bot(self):
        assert is_bot_user({}) is False
        assert is_bot_user(None) is False  # type: ignore[arg-type]

    def test_type_bot_is_bot(self):
        assert is_bot_user({"type": "Bot", "login": "anything"}) is True

    def test_known_bot_login(self):
        assert is_bot_user({"type": "User", "login": "dependabot"}) is True
        assert is_bot_user({"type": "User", "login": "renovate"}) is True
        assert is_bot_user({"type": "User", "login": "coderabbitai"}) is True

    def test_bracketed_bot_login(self):
        assert is_bot_user({"type": "User", "login": "anything[bot]"}) is True

    def test_login_case_insensitive(self):
        assert is_bot_user({"type": "User", "login": "DEPENDABOT"}) is True

    def test_human_user(self):
        assert is_bot_user({"type": "User", "login": "alice"}) is False


class TestIsLowSignalBody:
    @pytest.mark.parametrize("body", ["", "   ", "\n\t  \n"])
    def test_empty_or_whitespace(self, body):
        assert is_low_signal_body(body) is True

    @pytest.mark.parametrize("body", [":thumbsup:", ":+1:", ":rocket: :tada:"])
    def test_emoji_shortcodes(self, body):
        assert is_low_signal_body(body) is True

    @pytest.mark.parametrize("body", ["👍", "🎉🚀", "✨"])
    def test_unicode_emoji_only(self, body):
        assert is_low_signal_body(body) is True

    @pytest.mark.parametrize(
        "body",
        ["lgtm", "LGTM", "LGTM!", "looks good", "ship it", "+1", "approved", "thanks"],
    )
    def test_approval_phrases(self, body):
        assert is_low_signal_body(body) is True

    @pytest.mark.parametrize(
        "body",
        [
            "This variable name is unclear, please rename to something descriptive",
            "Consider extracting this into a helper function.",
            "Why isn't this wrapped in a try/except?",
        ],
    )
    def test_real_review_comments(self, body):
        assert is_low_signal_body(body) is False

    def test_approval_with_real_content_kept(self):
        body = "lgtm but please also rename `x` to `count`"
        assert is_low_signal_body(body) is False


class TestIsLowSignalComment:
    def test_bot_comment_filtered(self):
        comment = {
            "user": {"type": "Bot", "login": "dependabot"},
            "body": "This is a real review comment that would otherwise pass",
        }
        assert is_low_signal_comment(comment) is True

    def test_human_low_signal_filtered(self):
        comment = {"user": {"type": "User", "login": "alice"}, "body": "lgtm"}
        assert is_low_signal_comment(comment) is True

    def test_human_real_comment_kept(self):
        comment = {
            "user": {"type": "User", "login": "alice"},
            "body": "Please add a test for the error case here.",
        }
        assert is_low_signal_comment(comment) is False

    def test_missing_user_treated_as_human(self):
        comment = {"body": "Please clarify the docstring."}
        assert is_low_signal_comment(comment) is False
