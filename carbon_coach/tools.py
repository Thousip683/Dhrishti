"""ADK adapters sharing the deterministic domain service with REST."""
from copy import deepcopy
from decimal import Decimal
from google.adk.tools import ToolContext
from . import domain

def _call(context, operation, *args, **kwargs):
    state = deepcopy(context.state.get('ledger', {'timezone': 'Asia/Kolkata'}))
    try:
        result = operation(state, *args, **kwargs)
        reply = _receipt(operation.__name__, result, context.state.get('response_language','en'))
        response = {'status': 'success', 'result': result, 'assistant_text': reply}
    except domain.DomainError as exc:
        response = {'status': 'error', 'code': exc.code, 'assistant_text': exc.message}
    context.state['ledger'] = state
    receipts = list(context.state.get('turn_receipts', []))
    receipts.append(response['assistant_text'])
    context.state['turn_receipts'] = receipts
    return response

def _receipt(name, result, language='en'):
    if language in ('hi','te'):
        labels = {
            'hi': {'estimate':'अनुमान','unsaved':'अभी सहेजा नहीं गया','source':'स्रोत','saved':'गतिविधि सहेजी गई','total':'दर्ज उत्सर्जन','unknown':'बिना लॉग वाले दिनों का वास्तविक उत्सर्जन अज्ञात है।','saving':'इस दर्ज गतिविधि के लिए अनुमानित बचत','hypothetical':'यह एक काल्पनिक विकल्प है; दर्ज कुल नहीं बदला।','empty':'अभी कोई समर्थित कम उत्सर्जन वाला विकल्प नहीं मिला।','deleted':'गतिविधि दर्ज कुल से हटा दी गई।'},
            'te': {'estimate':'అంచనా','unsaved':'ఇంకా సేవ్ చేయలేదు','source':'మూలం','saved':'కార్యకలాపం సేవ్ అయింది','total':'నమోదైన ఉద్గారాలు','unknown':'నమోదులు లేని రోజుల నిజమైన ఉద్గారాలు తెలియవు.','saving':'ఈ నమోదైన కార్యకలాపానికి అంచనా ఆదా','hypothetical':'ఇది ఊహాత్మక ప్రత్యామ్నాయం; నమోదైన మొత్తం మారలేదు.','empty':'ప్రస్తుతం మద్దతు ఉన్న తక్కువ ఉద్గారాల ప్రత్యామ్నాయం లేదు.','deleted':'నమోదైన మొత్తం నుండి కార్యకలాపం తొలగించబడింది.'},
        }[language]
        if name=='calculate':
            sources='; '.join(f"{f['source_publisher']} ({f['version']}), {f['geography']}" for f in result['factor_snapshots'])
            return f"{labels['estimate']}: {result['display_kg_co2e']} kg CO2e. {labels['unsaved']}. {labels['source']}: {sources}. " + ' '.join(result['assumptions']+result['warnings'])
        if name=='log':
            return f"{labels['saved']}: {result['category']} · {result['activity_date']} · {domain.fixed(result['kg_co2e'],2)} kg CO2e."
        if name=='summary':
            return f"{labels['total']}: {result['display_total_kg_co2e']} kg CO2e ({result['start_date']} — {result['end_date']}, end exclusive). {labels['unknown']}"
        if name=='reductions':
            return '\n'.join(f"{s['action']} {labels['saving']}: {domain.fixed(s['saving_kg_co2e'],2)} kg CO2e. {labels['hypothetical']}" for s in result['suggestions']) or labels['empty']
        return labels['deleted']
    if name == 'calculate':
        sources = '; '.join(f"{f['source_publisher']} ({f['version']}), {f['geography']}" for f in result['factor_snapshots'])
        return f"Estimated {result['display_kg_co2e']} kg CO2e. Not yet logged. Source: {sources}. " + ' '.join(result['assumptions'] + result['warnings'])
    if name == 'log':
        return f"Saved {result['category']} for {result['activity_date']}: {domain.fixed(result['kg_co2e'], 2)} kg CO2e."
    if name == 'summary':
        return f"Your logged emissions from {result['start_date']} to {result['end_date']} (exclusive): {result['display_total_kg_co2e']} kg CO2e across {result['activity_count']} activities. " + result['coverage_note']
    if name == 'reductions':
        return '\n'.join(f"{s['action']} Estimated saving for the logged activity: {domain.fixed(s['saving_kg_co2e'], 2)} kg CO2e. Hypothetical only." for s in result['suggestions']) or 'No eligible logged activity has a supported lower-emission alternative yet.'
    return 'Activity removed from your logged totals.'

def calculate_travel_emissions(mode: str, km: str, tool_context: ToolContext, occupancy: int | None = None) -> dict:
    """Estimate travel without logging. Modes: bus, car_petrol, car_diesel. Ask car occupancy; never guess it. km is decimal text. UK reference factors only."""
    inp = {'mode': mode, 'distance_km': km}
    if occupancy is not None:
        inp['occupancy'] = occupancy
    return _call(tool_context, domain.calculate, 'travel', inp)

def calculate_electricity_emissions(kwh: str, grid_region: str, tool_context: ToolContext) -> dict:
    """Estimate measured electricity without logging. Only UK grid is configured. Ask region; never silently use UK for India."""
    return _call(tool_context, domain.calculate, 'electricity', {'kwh': kwh, 'grid_region': grid_region})

def calculate_food_emissions(meal_type: str, servings: str, tool_context: ToolContext) -> dict:
    """Estimate a defined recipe: pea_rice_bowl or chicken_rice_bowl. Each uses 0.1kg raw rice and 0.15kg peas or poultry per serving; ask if this matches. Cooking excluded."""
    return _call(tool_context, domain.calculate, 'food', {'meal_type': meal_type, 'servings': servings})

def calculate_waste_emissions(material: str, mass_kg: str, disposal_route: str, tool_context: ToolContext) -> dict:
    """Estimate treatment of food (landfill/compost) or paper (landfill/recycling). Require mass and route. UK reference."""
    return _call(tool_context, domain.calculate, 'waste', {'material': material, 'mass_kg': mass_kg, 'disposal_route': disposal_route})

def convert_appliance_energy(power_kw: str, hours: str, tool_context: ToolContext, duty_cycle: str = '1') -> dict:
    """Convert average electrical input power and hours to kWh. Use default duty cycle only when supplied power is average input. Never infer AC power from hours."""
    try:
        result = domain.appliance_energy(power_kw, hours, duty_cycle)
        reply = f"Energy estimate: {result['kwh']} kWh. " + ' '.join(result['assumptions'])
        response = {'status': 'success', 'result': result, 'assistant_text': reply}
    except domain.DomainError as exc:
        response = {'status': 'error', 'code': exc.code, 'assistant_text': exc.message}
    tool_context.state['turn_receipts'] = list(tool_context.state.get('turn_receipts', [])) + [response['assistant_text']]
    return response

def log_activity(calculation_id: str, tool_context: ToolContext, activity_date: str | None = None, note: str = '') -> dict:
    """Save a tool calculation when user states an actual activity or asks to log it. Never log hypothetical requests. Date defaults to session-local today."""
    return _call(tool_context, domain.log, calculation_id, activity_date, note)

def get_summary(tool_context: ToolContext, period: str = 'week', start_date: str | None = None, end_date: str | None = None) -> dict:
    """Return logged totals and daily trends. period: today, week, custom. Custom end is exclusive. Never call unlogged days zero real emissions."""
    return _call(tool_context, domain.summary, period, start_date, end_date)

def suggest_reductions(tool_context: ToolContext, period: str = 'week') -> dict:
    """Compute personal alternatives from actual logs, without modifying totals. Period today or week."""
    return _call(tool_context, domain.reductions, period)

def delete_activity(activity_id: str, revision: int, tool_context: ToolContext) -> dict:
    """Remove a specific logged activity with its current revision. Ask which record if ambiguous."""
    return _call(tool_context, domain.remove_activity, activity_id, revision)

QUESTIONS = {
    'travel': 'Which travel mode, distance in km, and car occupancy should I use? Supported modes are bus, petrol car and diesel car.',
    'electricity': 'What was the measured electricity in kWh and grid region? For an appliance, provide average electrical input power and hours. Only a UK reference grid is configured.',
    'food': 'Which defined recipe and how many servings? Choose pea rice bowl or chicken rice bowl; I can explain the ingredient assumptions.',
    'waste': 'What material, mass in kg and disposal route? Food supports landfill or compost; paper supports landfill or recycling.',
    'general': 'Describe your travel, electricity, a defined meal or waste. I can calculate estimates, save activities, show logged totals and suggest alternatives. UK reference factors and global food averages are disclosed.',
    'date': 'What calendar date should I use for that activity?',
}

def ask_for_details(category: str, tool_context: ToolContext) -> dict:
    """Ask a safe clarification or greet user. category: travel, electricity, food, waste, date, general. Use when required information is absent; do not invent it."""
    reply = QUESTIONS.get(category, QUESTIONS['general'])
    localized = {
        'hi': {'travel':'यात्रा का साधन और किलोमीटर में दूरी बताइए। कार के लिए चालक सहित लोगों की संख्या भी बताइए। UK संदर्भ के बस, पेट्रोल कार और डीजल कार उपलब्ध हैं।', 'electricity':'बिजली का उपयोग kWh में और ग्रिड क्षेत्र बताइए। उपकरण के लिए औसत विद्युत इनपुट शक्ति और उपयोग के घंटे चाहिए। अभी केवल UK संदर्भ उपलब्ध है।', 'food':'मटर चावल या चिकन चावल की परिभाषित रेसिपी और सर्विंग की संख्या चुनिए। पहले सामग्री की धारणाएँ जाँचिए।', 'waste':'सामग्री, किलोग्राम में वजन और निपटान का तरीका बताइए।', 'date':'इस गतिविधि की कैलेंडर तारीख बताइए।', 'general':'मैं यात्रा, बिजली, परिभाषित भोजन और कचरे के दर्ज उत्सर्जन को समझने में मदद कर सकता हूँ। गणना Python टूल से आती है।'},
        'te': {'travel':'ప్రయాణ మార్గం మరియు కిలోమీటర్ల దూరం చెప్పండి. కారులో డ్రైవర్‌తో సహా ఎంతమంది ఉన్నారో చెప్పండి. UK సూచన బస్సు, పెట్రోల్ కారు, డీజిల్ కారు అందుబాటులో ఉన్నాయి.', 'electricity':'విద్యుత్ వినియోగాన్ని kWhలో మరియు గ్రిడ్ ప్రాంతాన్ని చెప్పండి. పరికరం అయితే సగటు విద్యుత్ ఇన్‌పుట్ శక్తి మరియు వాడిన గంటలు అవసరం. ప్రస్తుతం UK సూచన మాత్రమే ఉంది.', 'food':'నిర్వచించిన బఠానీ అన్నం లేదా చికెన్ అన్నం వంటకం మరియు సర్వింగుల సంఖ్య ఎంచుకోండి. ముందుగా పదార్థాల అంచనాలను నిర్ధారించండి.', 'waste':'పదార్థం, కిలోగ్రాముల బరువు మరియు వ్యర్థాల నిర్వహణ పద్ధతిని చెప్పండి.', 'date':'ఈ కార్యకలాపం జరిగిన తేదీ చెప్పండి.', 'general':'ప్రయాణం, విద్యుత్, నిర్వచించిన ఆహారం మరియు వ్యర్థాల నమోదైన ఉద్గారాలకు సహాయం చేస్తాను. లెక్కలు Python సాధనాల నుండి వస్తాయి.'},
    }
    language=tool_context.state.get('response_language','en')
    if language in localized:
        reply=localized[language].get(category,localized[language]['general'])
    tool_context.state['turn_receipts'] = list(tool_context.state.get('turn_receipts', [])) + [reply]
    tool_context.state['needs_clarification'] = category != 'general'
    return {'status': 'needs_clarification', 'assistant_text': reply}

def list_activities(tool_context: ToolContext) -> dict:
    """List record IDs and revisions to identify a record before deleting or correcting it."""
    records = [a for a in tool_context.state.get('ledger', {}).get('activities', []) if not a['deleted']]
    reply = '\n'.join(f"{a['id']} revision {a['revision']}: {a['category']} on {a['activity_date']}, {a['kg_co2e']} kg CO2e" for a in records) or 'No activities logged yet.'
    tool_context.state['turn_receipts'] = list(tool_context.state.get('turn_receipts', [])) + [reply]
    return {'status': 'success', 'activities': records, 'assistant_text': reply}

def get_recent_calculations(tool_context: ToolContext) -> dict:
    """Retrieve recent owned previews and IDs for follow-ups such as 'save that'. Never invent an ID."""
    ledger = tool_context.state.get('ledger', {})
    records = sorted(ledger.get('calculations', {}).values(), key=lambda item: item['created_at'], reverse=True)[:5]
    reply = '\n'.join(f"{record['id']}: {record['category']}, {record['display_kg_co2e']} kg CO2e ({ledger.get('calculation_states',{}).get(record['id'],'uncommitted')})" for record in records) or 'No calculation previews are available in this session.'
    tool_context.state['turn_receipts'] = list(tool_context.state.get('turn_receipts', [])) + [reply]
    return {'status':'success','calculations':deepcopy(records),'assistant_text':reply}

def compare_food_options(original_food: str, alternative_food: str, kg: str, tool_context: ToolContext) -> dict:
    """Compare explicit equal kg of rice, poultry or peas using Dhrishti's comparison engine and the approved app factors. Does not log. Equal mass is not equal nutrition."""
    from .reference_agent.carbon_engine import calculate_reduction
    from .reference_agent.emission_factors import get_factor
    mapping = {'rice':'rice','poultry':'poultry_meat','peas':'peas'}
    try:
        quantity = domain.number(kg,'1000')
        refs = []
        for name in (original_food,alternative_food):
            if name not in mapping:
                raise domain.DomainError('UNSUPPORTED_ACTIVITY','For mass comparisons, choose rice, poultry or peas.')
            approved = domain.factor(mapping[name])
            original = get_factor('food',name)
            if Decimal(original['value']) != Decimal(approved['value']):
                raise domain.DomainError('FACTOR_NOT_AVAILABLE','The reference and approved factor versions disagree.')
            refs.append(approved)
        result = calculate_reduction('food',original_food,alternative_food,quantity)
        reply = f"For the same {kg} kg of food: {original_food} produces {domain.fixed(str(result['original']['emissions_kg']),2)} kg CO2e; {alternative_food} produces {domain.fixed(str(result['alternative']['emissions_kg']),2)} kg CO2e. Difference: {domain.fixed(str(result['saving_kg']),2)} kg CO2e (original minus alternative). Equal mass is not nutritional equivalence. Source: Poore and Nemecek, global food averages. This comparison was not logged."
        response = {'status':'success','result':result,'factor_snapshots':refs,'assistant_text':reply}
    except domain.DomainError as exc:
        response = {'status':'error','code':exc.code,'assistant_text':exc.message}
    tool_context.state['turn_receipts'] = list(tool_context.state.get('turn_receipts', [])) + [response['assistant_text']]
    return response
