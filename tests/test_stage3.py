from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from carbon_coach.api import app
from carbon_coach import domain as d, schemas

def session(c):
    meta=c.post('/api/v1/sessions',json={}).json()
    return '/api/v1/sessions/'+meta['session_id'], {'Authorization':'Bearer '+meta['session_token']}

def key(h):
    return {**h,'Idempotency-Key':str(uuid4())}

def test_capabilities_only_offer_supported_pairs_and_current_local_date():
    with TestClient(app) as c:
        base,h=session(c)
        result=c.get(base+'/capabilities',headers=h)
        assert result.status_code==200
        data=schemas.CapabilitiesResponse.model_validate(result.json())
        assert [grid.value for grid in data.grids]==['UK']
        assert data.local_today==d.today({'timezone':'Asia/Kolkata'})
        paper=next(material for material in data.waste if material.value=='paper')
        assert [route.value for route in paper.routes]==['landfill','recycling']
        assert next(choice for choice in data.travel if choice.value=='bus').requires_occupancy is False
        assert next(choice for choice in data.travel if choice.value=='car_petrol').requires_occupancy is True

def test_conversion_preview_source_linking_and_tamper_rejection():
    with TestClient(app) as c:
        base,h=session(c)
        op=key(h)
        body={'power_kw':'1.5','hours':'4','power_basis':'average'}
        conversion=c.post(base+'/energy-conversions',headers=op,json=body)
        assert conversion.status_code==201
        assert c.post(base+'/energy-conversions',headers=op,json=body).json()==conversion.json()
        evidence=conversion.json()['conversion']
        assert evidence['kwh']=='6.000000'
        inp={'kwh':evidence['kwh'],'grid_region':'UK','conversion_id':evidence['id']}
        preview=c.post(base+'/calculations',headers=key(h),json={'category':'electricity','input':inp})
        assert preview.status_code==201
        assert preview.json()['calculation']['energy_conversion']==evidence
        assert preview.json()['calculation']['kg_co2e']=='1.062000'
        assert c.get(base+'/activities',headers=h).json()['items']==[]
        assert c.post(base+'/calculations',headers=key(h),json={'category':'electricity','input':{**inp,'kwh':'7'}}).status_code==422
        other,other_h=session(c)
        assert c.post(other+'/calculations',headers=key(other_h),json={'category':'electricity','input':inp}).status_code==404

@pytest.mark.parametrize('body',[
    {'power_kw':'1.5','hours':'4','power_basis':'rated'},
    {'power_kw':'1.5','hours':'4','power_basis':'average','duty_cycle':'0.5'},
    {'power_kw':'1.5','hours':'25','power_basis':'average'},
    {'power_kw':'1.5','hours':'4','power_basis':'rated','duty_cycle':'0'},
    {'power_kw':'1.5','hours':'4','power_basis':'rated','duty_cycle':'1.1'},
    {'power_kw':'NaN','hours':'4','power_basis':'average'},
])
def test_invalid_appliance_inputs_are_not_guessed(body):
    with TestClient(app) as c:
        base,h=session(c)
        assert c.post(base+'/energy-conversions',headers=key(h),json=body).status_code==422
        assert c.get(base+'/activities',headers=h).json()['items']==[]

def test_explicit_factor_versions_and_four_category_saves():
    inputs=[('travel',{'mode':'bus','distance_km':'12'},'1.246200'),
        ('electricity',{'kwh':'6','grid_region':'UK'},'1.062000'),
        ('food',{'meal_type':'pea_rice_bowl','servings':'1'},None),
        ('waste',{'material':'food','mass_kg':'1','disposal_route':'landfill'},'0.700309')]
    with TestClient(app) as c:
        base,h=session(c)
        total=Decimal(0)
        date=c.get(base+'/capabilities',headers=h).json()['local_today']
        for category,inp,expected in inputs:
            preview=c.post(base+'/calculations',headers=key(h),json={'category':category,'input':inp})
            calc=preview.json()['calculation']
            assert calc['formula']
            if expected:
                assert calc['kg_co2e']==expected
            total+=Decimal(calc['kg_co2e'])
            op=key(h)
            payload={'calculation_id':calc['id'],'activity_date':date,'note':'Test activity'}
            saved=c.post(base+'/activities',headers=op,json=payload)
            assert saved.status_code==201
            assert c.post(base+'/activities',headers=op,json=payload).json()==saved.json()
        summary=c.get(base+'/summary?period=today',headers=h).json()['summary']
        assert summary['activity_count']==4
        assert Decimal(summary['total_kg_co2e'])==total
        assert c.post(base+'/calculations',headers=key(h),json={'category':'travel','input':inputs[0][1],'factor_id':'bus','factor_version':'not-current'}).status_code==422
        assert c.post(base+'/calculations',headers=key(h),json={'category':'travel','input':inputs[0][1],'factor_id':'bus'}).status_code==422

def test_rated_appliance_uses_explicit_duty_cycle():
    result=d.convert_energy({}, {'power_kw':'1.5','hours':'4','power_basis':'rated','duty_cycle':'0.5'})
    assert result['kwh']=='3.000000'
    assert 'duty cycle' in ' '.join(result['assumptions'])
