"""Unit tests for PII hashing and masking."""

from app.services.pii import hash_pii, mask_email, mask_name


class TestHashPii:
    def test_deterministic(self):
        assert hash_pii("test@example.com") == hash_pii("test@example.com")

    def test_case_insensitive(self):
        assert hash_pii("Test@Example.COM") == hash_pii("test@example.com")

    def test_strips_whitespace(self):
        assert hash_pii("  test@example.com  ") == hash_pii("test@example.com")

    def test_different_values_different_hashes(self):
        assert hash_pii("alice@example.com") != hash_pii("bob@example.com")

    def test_returns_hex_string(self):
        result = hash_pii("test@example.com")
        assert len(result) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in result)


class TestMaskEmail:
    def test_standard_email(self):
        assert mask_email("john.doe@example.com") == "j******e@e*****e.com"

    def test_short_local(self):
        assert mask_email("ab@example.com") == "a*@e*****e.com"

    def test_single_char_local(self):
        assert mask_email("a@example.com") == "a*@e*****e.com"

    def test_short_domain(self):
        assert mask_email("test@ab.com") == "t**t@a*.com"

    def test_preserves_tld(self):
        assert mask_email("user@domain.co.uk") == "u**r@d****n.co.uk"


class TestMaskName:
    def test_two_parts(self):
        assert mask_name("John Doe") == "J*** D**"

    def test_single_name(self):
        assert mask_name("Madonna") == "M******"

    def test_three_parts(self):
        assert mask_name("Mary Jane Watson") == "M*** J*** W*****"

    def test_single_char_name(self):
        assert mask_name("J Doe") == "J D**"
