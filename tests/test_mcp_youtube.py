"""Tests for mcp_servers/youtube_server.py helper functions."""

import pytest
import yaml

from mcp_servers.youtube_server import _resolve_channel

FAKE_CONFIG = {
    "channels": [
        {"id": "UCPk8m_r6fkUSYmvgCBwq-sw", "name": "Andrej Karpathy"},
        {"id": "UC_RovKmk0OCbuZjA8f08opw", "name": "Hard Fork"},
    ]
}


@pytest.fixture()
def config_root(tmp_path, monkeypatch):
    """Write a fake config.yaml into a temp dir and point _ROOT at it."""
    (tmp_path / "config.yaml").write_text(yaml.dump(FAKE_CONFIG))
    import mcp_servers.youtube_server as server

    monkeypatch.setattr(server, "_ROOT", tmp_path)
    return tmp_path


class TestResolveChannel:
    def test_channel_id_alone(self):
        """channel_id alone is returned directly; name defaults to empty string."""
        cid, cname = _resolve_channel(None, "UCPk8m_r6fkUSYmvgCBwq-sw")
        assert cid == "UCPk8m_r6fkUSYmvgCBwq-sw"
        assert cname == ""

    def test_channel_id_with_name(self):
        """When both are supplied, channel_id wins and name is passed through."""
        cid, cname = _resolve_channel("Andrej Karpathy", "UCPk8m_r6fkUSYmvgCBwq-sw")
        assert cid == "UCPk8m_r6fkUSYmvgCBwq-sw"
        assert cname == "Andrej Karpathy"

    def test_channel_name_found(self, config_root):
        """channel_name present in config → returns matching id and canonical name."""
        cid, cname = _resolve_channel("Andrej Karpathy", None)
        assert cid == "UCPk8m_r6fkUSYmvgCBwq-sw"
        assert cname == "Andrej Karpathy"

    def test_channel_name_case_insensitive(self, config_root):
        """Name lookup ignores case."""
        cid, _ = _resolve_channel("andrej karpathy", None)
        assert cid == "UCPk8m_r6fkUSYmvgCBwq-sw"

    def test_channel_name_not_found(self, config_root):
        """channel_name absent from config raises ValueError."""
        with pytest.raises(ValueError, match="not found in config.yaml"):
            _resolve_channel("Unknown Channel", None)

    def test_neither_provided(self):
        """Neither argument raises ValueError."""
        with pytest.raises(ValueError, match="Provide either"):
            _resolve_channel(None, None)
