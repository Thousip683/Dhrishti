import pytest
from carbon_coach.activity_tracker import add_activity, list_activities, get_summary_data
from carbon_coach.carbon_engine import calculate_electricity_emissions, calculate_food_emissions
from types import SimpleNamespace

@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv('CARBON_DB_PATH', str(tmp_path / 'test.sqlite3'))

def context(session_id):
    return SimpleNamespace(session=SimpleNamespace(id=session_id))

def test_save_and_retrieve():
    a = add_activity('alice', calculate_electricity_emissions(5))
    assert a['saved'] is True
    assert len(list_activities('alice')) == 1
    assert list_activities('bob') == []

def test_summary():
    add_activity('alice', calculate_electricity_emissions(5))
    add_activity('alice', calculate_electricity_emissions(2))
    summary = get_summary_data('alice', 'week')
    assert summary['activity_count'] == 2
    assert summary['totals'][0]['emissions_kg'] == pytest.approx(4.97)

def test_keep_incompatible_units_separate():
    add_activity('alice', calculate_electricity_emissions(5))
    add_activity('alice', calculate_food_emissions('rice', 0.2))
    assert len(get_summary_data('alice')['totals']) == 2

def test_idempotency():
    c = calculate_electricity_emissions(5)
    assert add_activity('alice', c, 'event1')['saved']
    assert add_activity('alice', c, 'event1')['duplicate']
    assert len(list_activities('alice')) == 1
    with pytest.raises(ValueError):
        add_activity('alice', calculate_electricity_emissions(7), 'event1')

def test_invalid_period():
    # 'month' is now a valid period; 'year' is not supported
    with pytest.raises(ValueError):
        get_summary_data('alice', 'year')

def test_tool_context_isolation():
    pytest.importorskip('google.adk.tools')
    from carbon_coach.tracker_tools import log_electricity, get_summary
    assert log_electricity(5, context('alice'))['saved']
    assert get_summary('week', context('alice'))['activity_count'] == 1
    assert get_summary('week', context('bob'))['activity_count'] == 0

def test_negative_input_never_stored():
    pytest.importorskip('google.adk.tools')
    from carbon_coach.tracker_tools import log_electricity
    assert 'error' in log_electricity(-2, context('alice'))
    assert list_activities('alice') == []

def test_food_savings_from_tools():
    pytest.importorskip('google.adk.tools')
    from carbon_coach.coach_tools import compare_food_options
    r = compare_food_options('poultry', 'peas', 0.2)
    assert r['saving_kg'] == pytest.approx(1.778)
    assert 'caveat' in r

def test_bad_food_comparison():
    pytest.importorskip('google.adk.tools')
    from carbon_coach.coach_tools import compare_food_options
    assert 'error' in compare_food_options('unknown', 'peas', 0.2)
