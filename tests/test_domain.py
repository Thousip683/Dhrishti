from copy import deepcopy
from decimal import Decimal
import pytest
from carbon_coach import domain as d

def state():
    return {'timezone': 'Asia/Kolkata', 'activities': [], 'calculations': {}}

def test_official_bus_and_no_implicit_log():
    s = state()
    c = d.calculate(s, 'travel', {'mode': 'bus', 'distance_km': '12'})
    assert c['kg_co2e'] == '1.246200'
    assert c['factor_snapshots'][0]['source_locator'].endswith('25_314_3145_11_1')
    assert s['activities'] == []

def test_car_allocation_and_no_double_bus_division():
    s = state()
    c = d.calculate(s, 'travel', {'mode': 'car_petrol', 'distance_km': '12', 'occupancy': 2})
    assert c['kg_co2e'] == '0.976320'
    with pytest.raises(d.DomainError):
        d.calculate(s, 'travel', {'mode': 'bus', 'distance_km': '12', 'occupancy': 2})
    with pytest.raises(d.DomainError, match='How many'):
        d.calculate(s, 'travel', {'mode': 'car_petrol', 'distance_km': '12'})

@pytest.mark.parametrize('invalid', ['-1','NaN','Infinity','1e2','1.1234567',None,True,'10001'])
def test_invalid_quantities(invalid):
    with pytest.raises(d.DomainError):
        d.calculate(state(), 'travel', {'mode':'bus', 'distance_km':invalid})

def test_energy_conversion_and_grid_validation():
    assert d.appliance_energy('1.5', '4')['kwh'] == '6.000000'
    assert d.appliance_energy('1.5', '4', '0.5')['kwh'] == '3.000000'
    assert d.calculate(state(), 'electricity', {'kwh':'6', 'grid_region':'UK'})['kg_co2e'] == '1.062000'
    with pytest.raises(d.DomainError):
        d.calculate(state(), 'electricity', {'kwh':'6', 'grid_region':'IN'})

def test_food_and_waste_source_units():
    food = d.calculate(state(), 'food', {'meal_type':'pea_rice_bowl', 'servings':'1'})
    assert Decimal(food['kg_co2e']) == Decimal(d.FACTORS['rice']['value']) * Decimal('.1') + Decimal(d.FACTORS['peas']['value']) * Decimal('.15')
    assert d.calculate(state(), 'waste', {'material':'food','mass_kg':'1','disposal_route':'landfill'})['kg_co2e'] == '0.700309'
    with pytest.raises(d.DomainError):
        d.calculate(state(), 'waste', {'material':'paper','mass_kg':'1','disposal_route':'compost'})

def test_log_retry_summary_and_delete():
    s = state()
    c = d.calculate(s, 'travel', {'mode':'bus','distance_km':'12'})
    a = d.log(s, c['id'])
    assert d.log(s, c['id'])['id'] == a['id']
    assert d.summary(s, 'today')['activity_count'] == 1
    assert d.summary(s, 'today')['total_kg_co2e'] == '1.246200'
    d.remove_activity(s, a['id'], 1)
    assert d.summary(s, 'today')['activity_count'] == 0
    new_calculation = d.calculate(s,'travel',{'mode':'bus','distance_km':'1'})
    with pytest.raises(d.DomainError):
        d.log(s, new_calculation['id'], '2999-01-01')

def test_summary_rounds_after_aggregation_and_custom_window():
    s = state()
    for _ in range(3):
        d.log(s, d.calculate(s,'travel',{'mode':'bus','distance_km':'0.04'})['id'], '2026-10-01')
    result = d.summary(s, 'custom', '2026-10-01', '2026-10-02')
    assert result['display_total_kg_co2e'] == '0.01'
    assert result['logged_day_count'] == 1
    with pytest.raises(d.DomainError):
        d.summary(s,'custom','2026-10-01','2026-10-01')

def test_savings_are_personal_and_do_not_mutate_ledger():
    s = state()
    d.log(s, d.calculate(s,'travel',{'mode':'car_petrol','distance_km':'12','occupancy':1})['id'])
    before = deepcopy(s)
    result = d.reductions(s, 'today')['suggestions'][0]
    assert result['saving_kg_co2e'] == '0.706440'
    assert s == before
    shared = state()
    d.log(shared,d.calculate(shared,'travel',{'mode':'car_petrol','distance_km':'12','occupancy':4})['id'])
    assert d.reductions(shared,'today')['suggestions'] == []

def test_receipts_immutable_and_sessions_isolated():
    a,b=state(),state()
    c=d.calculate(a,'travel',{'mode':'bus','distance_km':'12'})
    c['kg_co2e']='999'
    assert a['calculations'][c['id']]['kg_co2e']=='1.246200'
    with pytest.raises(d.DomainError):
        d.log(b,c['id'])
