"""Deterministic arithmetic and session ledger; no LLM or network required."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

FACTORS = {f['id']: f for f in json.loads((Path(__file__).parent / 'data/factors.json').read_text())}
RECIPES = {
    'pea_rice_bowl': {'rice': '0.1', 'peas': '0.15'},
    'chicken_rice_bowl': {'rice': '0.1', 'poultry_meat': '0.15'},
}
CATEGORIES = ('travel', 'electricity', 'food', 'waste')

class DomainError(ValueError):
    def __init__(self, code, message, http=422):
        self.code, self.message, self.http = code, message, http
        super().__init__(message)

def number(value, maximum='10000', positive=False):
    if isinstance(value, bool) or not re.fullmatch(r'\d+(?:\.\d{1,6})?', str(value)):
        raise DomainError('INVALID_QUANTITY', 'Use a nonnegative decimal with at most six decimal places.')
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise DomainError('INVALID_QUANTITY', 'Invalid decimal.')
    if not result.is_finite() or result > Decimal(maximum) or (positive and result <= 0):
        raise DomainError('INVALID_QUANTITY', f'Quantity must be within the supported range up to {maximum}.')
    return result

def fixed(value, places=6):
    return str(Decimal(value).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP))

def today(state):
    return datetime.now(ZoneInfo(state.get('timezone', 'Asia/Kolkata'))).date()

def factor(key):
    if key not in FACTORS or not FACTORS[key].get('approved') or FACTORS[key].get('fixture_only'):
        raise DomainError('FACTOR_NOT_AVAILABLE', f'No approved factor for {key}. Ask for a supported choice.')
    if FACTORS[key].get('gas_basis') != 'CO2e':
        raise DomainError('INCOMPATIBLE_GAS_BASIS','A CO2-only factor cannot be used as an all-gas CO2e factor.')
    return deepcopy(FACTORS[key])

def calculate(state, category, inputs, requested_factor_ref=None):
    """Create immutable calculation evidence without adding an activity."""
    if category not in CATEGORIES:
        raise DomainError('UNSUPPORTED_ACTIVITY', 'Choose travel, electricity, food or waste.')
    assumptions, refs = [], []
    conversion = None
    if category == 'travel':
        mode = inputs.get('mode')
        f = factor(mode)
        if f['category'] != category:
            raise DomainError('UNSUPPORTED_ACTIVITY', 'Choose bus, car_petrol or car_diesel.')
        qty = number(inputs.get('distance_km'))
        occupancy = inputs.get('occupancy')
        if f['denominator_unit'] == 'vehicle_km':
            if occupancy is None:
                raise DomainError('MISSING_INPUT', 'How many people were in the car, including the driver?')
            if isinstance(occupancy, bool) or not isinstance(occupancy, int) or not 1 <= occupancy <= 100:
                raise DomainError('INVALID_QUANTITY', 'Occupancy must be an integer between 1 and 100.')
            qty /= occupancy
            assumptions.append(f'Vehicle emissions allocated equally across {occupancy} occupants.')
        elif occupancy is not None:
            raise DomainError('INVALID_QUANTITY', 'Bus factors are already per passenger; omit occupancy.')
        total = qty * Decimal(f['value'])
        formula = f"{inputs['distance_km']} * {f['value']}" + (f' / {occupancy}' if occupancy is not None else '')
        unit = f['denominator_unit']
        refs = [f]
    elif category == 'electricity':
        if inputs.get('grid_region') != 'UK':
            raise DomainError('FACTOR_NOT_AVAILABLE', 'Only a UK grid reference is configured. Do not use it as an India grid factor.')
        qty = number(inputs.get('kwh'))
        if inputs.get('conversion_id'):
            conversion = state.get('energy_conversions', {}).get(inputs['conversion_id'])
            if conversion is None:
                raise DomainError('NOT_FOUND', 'Energy conversion not found in this session.', 404)
            if qty != Decimal(conversion['kwh']):
                raise DomainError('INVALID_QUANTITY', 'Electricity kWh must match the linked conversion.')
        f = factor('UK')
        refs = [f]
        total = qty * Decimal(f['value'])
        formula, unit = f"{qty} * {f['value']}", 'kwh'
    elif category == 'food':
        recipe = inputs.get('meal_type')
        if recipe not in RECIPES:
            raise DomainError('UNSUPPORTED_ACTIVITY', 'Choose pea_rice_bowl or chicken_rice_bowl; both have explicit uncooked ingredient masses.')
        qty = number(inputs.get('servings'), '100', positive=True)
        total = Decimal(0)
        terms = []
        for ingredient, mass in RECIPES[recipe].items():
            f = factor(ingredient)
            total += qty * Decimal(mass) * Decimal(f['value'])
            refs.append(f)
            terms.append(f"({qty} * {mass} * {f['value']})")
        formula, unit = ' + '.join(terms), 'serving'
        assumptions.append(f'Example recipe per serving in kg raw product: {RECIPES[recipe]}. Cooking, oil and seasonings excluded.')
    else:
        qty = number(inputs.get('mass_kg'), '1000')
        f = factor(f"{inputs.get('material')}:{inputs.get('disposal_route')}")
        if f['category'] != 'waste':
            raise DomainError('UNSUPPORTED_ACTIVITY', 'Unsupported waste treatment.')
        refs = [f]
        total = qty * Decimal(f['value'])
        formula, unit = f"{qty} * {f['value']}", 'kg'
        assumptions.append('Treatment emissions only; food production is not counted again.')
    if requested_factor_ref is not None:
        if len(refs) != 1 or requested_factor_ref != (refs[0]['id'], refs[0]['version']):
            raise DomainError('FACTOR_NOT_AVAILABLE', 'The selected factor version is unavailable or incompatible. Refresh the supported choices and preview again.')
    identifier = str(uuid4())
    record = dict(id=identifier, category=category, input=deepcopy(inputs),
        normalized_quantity=fixed(qty), kg_co2e=fixed(total), display_kg_co2e=fixed(total, 2),
        factor_refs=[{'id': f['id'], 'version': f['version']} for f in refs], factor_snapshots=refs,
        assumptions=assumptions, warnings=list(dict.fromkeys(f['limitations'] for f in refs)),
        claim_ids=[f'{identifier}:emissions'], created_at=datetime.now(timezone.utc).isoformat(),
        normalized_unit=unit, formula=formula,
        recipe_version='carbon-recipes-v1' if category == 'food' else None,
        energy_conversion=deepcopy(conversion))
    state.setdefault('calculations', {})[identifier] = record
    state.setdefault('calculation_states', {})[identifier] = 'uncommitted'
    return deepcopy(record)

def appliance_energy(power_kw, hours, duty_cycle='1'):
    power, duration, duty = number(power_kw, '100'), number(hours, '24'), number(duty_cycle, '1', positive=True)
    return {'kwh': fixed(power * duration * duty), 'formula': f'{power} * {duration} * {duty}',
            'assumptions': ['Power is electrical input, not cooling capacity. Duty cycle 1 means supplied power is the average input.']}

def convert_energy(state, inputs):
    """Create session-owned conversion evidence; never log an activity."""
    basis = inputs.get('power_basis')
    duty = inputs.get('duty_cycle')
    if basis == 'rated':
        if duty is None:
            raise DomainError('MISSING_INPUT', 'Rated input power needs an explicit duty cycle, or provide measured kWh.')
        number(duty, '1', positive=True)
    elif basis == 'average':
        if duty is not None and number(duty, '1', positive=True) != 1:
            raise DomainError('INVALID_QUANTITY', 'Average input power is already time-averaged. Omit duty cycle or use 1.')
    else:
        raise DomainError('MISSING_INPUT', 'Choose average electrical input power or rated electrical input power.')
    result = appliance_energy(inputs.get('power_kw'), inputs.get('hours'), duty or '1')
    result['assumptions'] = ['Electrical input power, not cooling capacity.',
        'Average input power over the stated duration.' if basis == 'average' else 'Rated electrical input multiplied by the explicitly supplied duty cycle.']
    result.update(id=str(uuid4()), input=deepcopy(inputs), created_at=datetime.now(timezone.utc).isoformat())
    state.setdefault('energy_conversions', {})[result['id']] = result
    return deepcopy(result)

def capabilities(state):
    def ref(key):
        f = factor(key)
        return {'id': f['id'], 'version': f['version']}
    travel = [dict(value=key, label=label, factor_ref=ref(key), requires_occupancy=FACTORS[key]['denominator_unit'] == 'vehicle_km')
        for key,label in [('bus','Bus'),('car_petrol','Petrol car'),('car_diesel','Diesel car')]
        if key in FACTORS and FACTORS[key]['approved'] and not FACTORS[key]['fixture_only']]
    recipes = [dict(value=key, label=key.replace('_',' ').capitalize(), version='carbon-recipes-v1',
        ingredients=[dict(label=ingredient.replace('_',' '),mass_kg=mass,factor_ref=ref(ingredient)) for ingredient,mass in values.items()],
        exclusions=['Cooking energy', 'Oil', 'Seasonings']) for key,values in RECIPES.items()]
    waste = []
    for material in ('food','paper'):
        routes = [dict(value=route,label=route.capitalize(),factor_ref=ref(f'{material}:{route}'))
            for route in ('landfill','compost','recycling') if f'{material}:{route}' in FACTORS]
        waste.append(dict(value=material,label=material.capitalize(),routes=routes))
    return dict(local_today=today(state).isoformat(),timezone=state.get('timezone','Asia/Kolkata'),travel=travel,
        grids=[dict(value='UK',label='United Kingdom reference',factor_ref=ref('UK'))],recipes=recipes,waste=waste,
        limits=dict(decimal_places=6,distance_km_max='10000',occupancy_max=100,kwh_max='10000',power_kw_max='100',hours_max='24',servings_max='100',mass_kg_max='1000',note_max_length=500),
        regional_notice='UK reference factors and global food averages only. India-specific grid factors are not configured. Estimates cover the stated boundaries, not a complete lifecycle footprint.')

def log(state, calculation_id, activity_date=None, note=''):
    calculations = state.get('calculations', {})
    if calculation_id not in calculations:
        raise DomainError('NOT_FOUND', 'Calculation not found in this session.', 404)
    if state.get('calculation_states', {}).get(calculation_id) in ('superseded', 'deleted'):
        raise DomainError('CALCULATION_ALREADY_LOGGED', 'This calculation was superseded or deleted and cannot be logged again.', 409)
    for item in state.get('activities', []):
        if item['calculation_id'] == calculation_id:
            return deepcopy(item)  # Safe for model retries, including after deletion.
    try:
        day = date.fromisoformat(activity_date) if activity_date else today(state)
    except ValueError:
        raise DomainError('INVALID_DATE', 'Use an ISO date YYYY-MM-DD.')
    if day > today(state):
        raise DomainError('INVALID_DATE', 'Actual activities cannot be logged in the future.')
    if len(note) > 500:
        raise DomainError('INVALID_REQUEST', 'Notes are limited to 500 characters.')
    calc = calculations[calculation_id]
    item = dict(id=str(uuid4()), calculation_id=calculation_id, category=calc['category'],
                activity_date=day.isoformat(), kg_co2e=calc['kg_co2e'], note=note, revision=1,
                deleted=False, created_at=datetime.now(timezone.utc).isoformat())
    state.setdefault('activities', []).append(item)
    state.setdefault('calculation_states', {})[calculation_id] = 'active'
    return deepcopy(item)

def window(state, period='week', start_date=None, end_date=None):
    current = today(state)
    if period == 'today':
        start, end = current, current + timedelta(days=1)
    elif period == 'week':
        start = current - timedelta(days=current.weekday())
        end = start + timedelta(days=7)
    elif period == 'custom':
        try:
            start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        except (ValueError, TypeError):
            raise DomainError('INVALID_DATE', 'Custom period requires valid start_date and end_date.')
    else:
        raise DomainError('INVALID_DATE', 'Period must be today, week or custom.')
    if end <= start or (end-start).days > 366:
        raise DomainError('INVALID_DATE', 'Use a positive window no longer than 366 days.')
    return start, end

def summary(state, period='week', start_date=None, end_date=None):
    start, end = window(state, period, start_date, end_date)
    entries = [a for a in state.get('activities', []) if not a['deleted'] and start.isoformat() <= a['activity_date'] < end.isoformat()]
    total = sum((Decimal(a['kg_co2e']) for a in entries), Decimal(0))
    daily = []
    for n in range((end-start).days):
        day = (start + timedelta(days=n)).isoformat()
        matching = [a for a in entries if a['activity_date'] == day]
        daily.append({'date': day, 'recorded_kg_co2e': fixed(sum((Decimal(a['kg_co2e']) for a in matching), Decimal(0))), 'has_records': bool(matching), 'activity_count': len(matching)})
    return dict(start_date=start.isoformat(), end_date=end.isoformat(), timezone=state.get('timezone', 'Asia/Kolkata'),
        total_kg_co2e=fixed(total), display_total_kg_co2e=fixed(total, 2), activity_count=len(entries),
        by_category={c: fixed(sum((Decimal(a['kg_co2e']) for a in entries if a['category'] == c), Decimal(0))) for c in CATEGORIES},
        daily=daily, logged_day_count=sum(d['has_records'] for d in daily),
        coverage_note='Recorded activities only. Days without logs are unknown, not zero real emissions.',
        warnings=['Totals combine the disclosed category boundaries; this is not a full lifecycle inventory.'],
        claim_ids=['summary:total'])

def reductions(state, period='week'):
    start, end = window(state, period)
    suggestions = []
    for a in state.get('activities', []):
        if a['deleted'] or not start.isoformat() <= a['activity_date'] < end.isoformat():
            continue
        calc = state['calculations'][a['calculation_id']]
        inp = deepcopy(calc['input'])
        action = None
        if calc['category'] == 'travel' and inp['mode'].startswith('car_'):
            inp.pop('occupancy', None)
            inp['mode'] = 'bus'
            action = 'Use a bus for this journey if the route is practical.'
        elif calc['category'] == 'food' and inp['meal_type'] == 'chicken_rice_bowl':
            inp['meal_type'] = 'pea_rice_bowl'
            action = 'Try the defined pea rice bowl instead; portions are recipe assumptions, not nutrition equivalents.'
        elif calc['category'] == 'waste' and inp['disposal_route'] == 'landfill':
            inp['disposal_route'] = 'compost' if inp['material'] == 'food' else 'recycling'
            action = 'Use the alternative treatment only where your local collection accepts this material.'
        if not action:
            continue
        # Scenarios use the shared engine without persisting speculative calculations.
        alternative = calculate({'calculations': {}}, calc['category'], inp)
        saving = Decimal(a['kg_co2e']) - Decimal(alternative['kg_co2e'])
        if saving > 0:
            suggestions.append(dict(id=str(uuid4()), baseline_activity_ids=[a['id']], action=action,
                baseline_kg_co2e=a['kg_co2e'], alternative_kg_co2e=alternative['kg_co2e'],
                saving_kg_co2e=fixed(saving), alternative=alternative, overlap_group=a['id'],
                assumptions=['Same logged quantity; hypothetical saving only.'], claim_ids=[f"{a['id']}:saving"]))
    suggestions.sort(key=lambda s: Decimal(s['saving_kg_co2e']), reverse=True)
    return {'suggestions': suggestions[:3], 'unavailable_reason': None if suggestions else 'NO_ELIGIBLE_ACTIVITIES'}

def remove_activity(state, activity_id, revision):
    for item in state.get('activities', []):
        if item['id'] == activity_id:
            if item['revision'] != revision:
                raise DomainError('REVISION_MISMATCH', 'Reload the record before editing.', 412)
            item['deleted'] = True
            state.setdefault('calculation_states', {})[item['calculation_id']] = 'deleted'
            item['revision'] += 1
            return {'deleted': activity_id}
    raise DomainError('NOT_FOUND', 'Activity not found.', 404)
