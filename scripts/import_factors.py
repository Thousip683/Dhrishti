"""Rebuild the curated registry from downloaded published source snapshots.

Run with a Python environment containing openpyxl. This is an offline build
step, not a runtime dependency. Original rows and unit conversions are retained.
"""
import csv
import json
from decimal import Decimal
from pathlib import Path
import openpyxl

ROOT = Path(__file__).resolve().parents[1] / 'carbon_coach' / 'data'
SOURCE = 'https://assets.publishing.service.gov.uk/media/6846b6ea57f3515d9611f0dd/ghg-conversion-factors-2025-flat-format.xlsx'
selected = {
    '25_314_3145_11_1': ('bus', 'travel', 'passenger_km', 'operational'),
    '4_301_3070_4_1': ('car_petrol', 'travel', 'vehicle_km', 'operational'),
    '4_301_3069_4_1': ('car_diesel', 'travel', 'vehicle_km', 'operational'),
    '7_400_4000_5_1': ('UK', 'electricity', 'kwh', 'generation_only'),
    '20_507_5292_15_1': ('food:landfill', 'waste', 'kg', 'waste_treatment'),
    '20_507_5291_15_1': ('food:compost', 'waste', 'kg', 'waste_treatment'),
    '20_506_5460_15_1': ('paper:landfill', 'waste', 'kg', 'waste_treatment'),
    '20_506_5457_15_1': ('paper:recycling', 'waste', 'kg', 'waste_treatment'),
}
factors = []
sheet = openpyxl.load_workbook(ROOT / 'source-2025.xlsx', read_only=True, data_only=True)['Factors by Category']
for rownum, row in enumerate(sheet.values, 1):
    if row[0] not in selected:
        continue
    key, category, unit, boundary = selected[row[0]]
    value = Decimal(str(row[9]))
    if row[7] == 'tonnes':
        value /= 1000
    factors.append(dict(id=key, category=category, value=str(value), denominator_unit=unit,
        version='DESNZ-2025-v1', gas_basis='CO2e', boundary=boundary, geography='UK',
        reference_year=2025, source_publisher='UK Department for Energy Security and Net Zero',
        source_url=SOURCE, source_locator=f'Factors by Category row {rownum}; ID {row[0]}',
        source_value=str(row[9]), source_unit=row[7], approved=True, fixture_only=False,
        limitations='UK reference estimate; not India-specific. Boundary excludes unlisted lifecycle stages.'))
assert len(factors) == len(selected)
with (ROOT / 'food-source.csv').open(encoding='utf-8-sig') as handle:
    for row in csv.DictReader(handle):
        if row['Entity'] in ('Rice', 'Peas', 'Poultry Meat'):
            factors.append(dict(id=row['Entity'].lower().replace(' ', '_'), category='ingredient',
                value=row['Greenhouse gas emissions per kilogram'], denominator_unit='kg',
                version='Poore-Nemecek-2018-OWID', gas_basis='CO2e', boundary='food_supply_chain',
                geography='Global mean', reference_year=int(row['Year']),
                source_publisher='Poore and Nemecek 2018, processed by Our World in Data',
                source_url='https://ourworldindata.org/grapher/ghg-per-kg-poore',
                source_locator=f"Entity {row['Entity']}; year {row['Year']}",
                approved=True, fixture_only=False,
                limitations='Global mean per kg product; example recipes omit cooking, oil and seasonings.'))
assert len(factors) == 11, 'Food source entities changed; review importer'
(ROOT / 'factors.json').write_text(json.dumps(factors, indent=2), encoding='utf-8')
print(f'Imported {len(factors)} verified factors')
