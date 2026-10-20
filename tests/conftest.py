"""
Shared pytest fixtures for Garmin MCP testing
"""
import pytest
from datetime import datetime, timedelta


@pytest.fixture
def today_str():
    """Return today's date as YYYY-MM-DD string"""
    return datetime.now().strftime("%Y-%m-%d")


@pytest.fixture
def yesterday_str():
    """Return yesterday's date as YYYY-MM-DD string"""
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


@pytest.fixture
def date_range():
    """Return a tuple of (start_date, end_date) as strings"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    return (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
