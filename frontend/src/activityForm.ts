import type { ActivityInput, Calculation, CapabilitiesResponse, ElectricityCalc, FoodCalc, TravelCalc, WasteCalc } from './api/schema';
export type Category = Calculation['category'];

export type Fields = {
  category: Category; mode: string; distance: string; occupancy: string;
  energyMethod: 'measured' | 'appliance'; grid: string; kwh: string;
  power: string; hours: string; powerBasis: string; duty: string;
  recipe: string; servings: string; recipeAccepted: boolean;
  material: string; route: string; mass: string; date: string; note: string;
};
export type Draft = {
  fields: Fields; previewKey: string; conversionKey: string; saveKey: string;
  previewId?: string; previewFor?: string; saveRequest?: ActivityInput; savedId?: string;
};
export type Errors = Partial<Record<keyof Fields, string>>;
export type CalculationBody = TravelCalc | ElectricityCalc | FoodCalc | WasteCalc;

export function freshDraft(date = '', category: Category = 'travel'): Draft {
  return { fields: { category, mode: '', distance: '', occupancy: '', energyMethod: 'measured', grid: '', kwh: '', power: '', hours: '', powerBasis: '', duty: '', recipe: '', servings: '1', recipeAccepted: false, material: '', route: '', mass: '', date, note: '' }, previewKey: crypto.randomUUID(), conversionKey: crypto.randomUUID(), saveKey: crypto.randomUUID() };
}
export function restoreDraft(raw: string): Draft {
  try {
    const value = JSON.parse(raw) as Draft;
    const defaults = freshDraft();
    if (!value?.fields || !['travel', 'electricity', 'food', 'waste'].includes(value.fields.category)) return defaults;
    for (const [key, expected] of Object.entries(defaults.fields)) if (typeof value.fields[key as keyof Fields] !== typeof expected) return defaults;
    if (![value.previewKey, value.conversionKey, value.saveKey].every(key => typeof key === 'string' && key.length > 0)) return defaults;
    if (value.saveRequest && (typeof value.saveRequest.calculation_id !== 'string' || typeof value.saveRequest.activity_date !== 'string' || typeof value.saveRequest.note !== 'string')) return defaults;
    return value;
  } catch { return freshDraft(); }
}
export const fingerprint = (fields: Fields) => JSON.stringify(fields);

export function validate(fields: Fields, caps: CapabilitiesResponse): Errors {
  const errors: Errors = {};
  const decimal = (field: keyof Fields, label: string, max: string, positive = false) => {
    const value = fields[field];
    if (typeof value !== 'string' || !/^\d+(?:\.\d{1,6})?$/.test(value)) errors[field] = `Enter ${label} as a nonnegative decimal with up to ${caps.limits.decimal_places} decimal places.`;
    else if (Number(value) > Number(max) || (positive && Number(value) <= 0)) errors[field] = `${label} must be ${positive ? 'greater than zero and ' : ''}at most ${max}.`;
  };
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fields.date) || !Number.isFinite(Date.parse(fields.date + 'T00:00:00Z')) || new Date(fields.date + 'T00:00:00Z').toISOString().slice(0, 10) !== fields.date) errors.date = 'Choose a valid activity date.';
  else if (fields.date > caps.local_today) errors.date = 'Actual activities cannot be saved in the future.';
  if (fields.note.length > caps.limits.note_max_length) errors.note = `Keep the note within ${caps.limits.note_max_length} characters.`;
  if (fields.category === 'travel') {
    const mode = caps.travel.find(item => item.value === fields.mode);
    if (!mode) errors.mode = 'Choose a supported travel mode.';
    decimal('distance', 'distance in km', caps.limits.distance_km_max);
    if (mode?.requires_occupancy && (!/^[1-9]\d*$/.test(fields.occupancy) || Number(fields.occupancy) > caps.limits.occupancy_max)) errors.occupancy = `Enter the number of people including the driver, from 1 to ${caps.limits.occupancy_max}.`;
  } else if (fields.category === 'electricity') {
    if (!caps.grids.some(item => item.value === fields.grid)) errors.grid = 'Select a supported reference grid explicitly.';
    if (fields.energyMethod === 'measured') decimal('kwh', 'energy in kWh', caps.limits.kwh_max);
    else {
      decimal('power', 'electrical input power in kW', caps.limits.power_kw_max);
      decimal('hours', 'usage hours', caps.limits.hours_max);
      if (!['average', 'rated'].includes(fields.powerBasis)) errors.powerBasis = 'Choose average or rated electrical input power.';
      if (fields.powerBasis === 'rated') decimal('duty', 'duty cycle', '1', true);
    }
  } else if (fields.category === 'food') {
    if (!caps.recipes.some(item => item.value === fields.recipe)) errors.recipe = 'Choose a defined recipe.';
    decimal('servings', 'servings', caps.limits.servings_max, true);
    if (!fields.recipeAccepted) errors.recipeAccepted = 'Confirm that the displayed recipe assumptions match this entry.';
  } else {
    const material = caps.waste.find(item => item.value === fields.material);
    if (!material) errors.material = 'Choose a supported material.';
    if (!material?.routes.some(item => item.value === fields.route)) errors.route = 'Choose a supported treatment for this material.';
    decimal('mass', 'mass in kg', caps.limits.mass_kg_max);
  }
  return errors;
}

export function calculationBody(fields: Fields, caps: CapabilitiesResponse, energy?: { id: string; kwh: string }): CalculationBody {
  if (fields.category === 'travel') {
    const choice = caps.travel.find(item => item.value === fields.mode)!;
    return { category: 'travel', factor_id: choice.factor_ref.id, factor_version: choice.factor_ref.version,
      input: { mode: fields.mode as 'bus' | 'car_petrol' | 'car_diesel', distance_km: fields.distance, ...(choice.requires_occupancy ? { occupancy: Number(fields.occupancy) } : {}) } };
  }
  if (fields.category === 'electricity') {
    const grid = caps.grids.find(item => item.value === fields.grid)!;
    return { category: 'electricity', factor_id: grid.factor_ref.id, factor_version: grid.factor_ref.version,
      input: { grid_region: fields.grid as 'UK', kwh: energy?.kwh ?? fields.kwh, ...(energy ? { conversion_id: energy.id } : {}) } };
  }
  if (fields.category === 'food') return { category: 'food', input: { meal_type: fields.recipe as 'pea_rice_bowl' | 'chicken_rice_bowl', servings: fields.servings } };
  const route = caps.waste.find(item => item.value === fields.material)!.routes.find(item => item.value === fields.route)!;
  return { category: 'waste', factor_id: route.factor_ref.id, factor_version: route.factor_ref.version,
    input: { material: fields.material as 'food' | 'paper', mass_kg: fields.mass, disposal_route: fields.route as 'landfill' | 'compost' | 'recycling' } };
}
