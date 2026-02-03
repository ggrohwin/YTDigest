"""Tests for main.py utilities."""

import pytest
from src.main import format_duration


class TestFormatDuration:
    """Tests for the format_duration function."""

    def test_minutes_and_seconds(self):
        assert format_duration("PT15M33S") == "15:33"

    def test_only_minutes(self):
        assert format_duration("PT5M") == "5:00"

    def test_only_seconds(self):
        assert format_duration("PT45S") == "0:45"

    def test_hours_minutes_seconds(self):
        assert format_duration("PT1H30M15S") == "1:30:15"

    def test_hours_only(self):
        assert format_duration("PT2H") == "2:00:00"

    def test_hours_and_minutes(self):
        assert format_duration("PT1H5M") == "1:05:00"

    def test_hours_and_seconds(self):
        assert format_duration("PT1H30S") == "1:00:30"

    def test_none_input(self):
        assert format_duration(None) == ""

    def test_empty_string(self):
        assert format_duration("") == ""

    def test_invalid_format(self):
        assert format_duration("invalid") == ""

    def test_zero_duration(self):
        assert format_duration("PT0S") == "0:00"

    def test_pads_seconds(self):
        """Seconds should be zero-padded to 2 digits."""
        assert format_duration("PT5M5S") == "5:05"

    def test_pads_minutes_with_hours(self):
        """Minutes should be zero-padded when hours are present."""
        assert format_duration("PT2H5M30S") == "2:05:30"
