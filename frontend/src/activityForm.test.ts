import { describe, expect, it } from 'vitest';
import fixture from './fixtures/application.json';
import { calculationBody, freshDraft, restoreDraft, validate } from './activityForm';
import type { CapabilitiesResponse } from './api/schema';
const caps = fixture.capabilities as CapabilitiesResponse;
const valid = () => ({ ...freshDraft(caps.local_today).fields, mode: 'bus', distance: '12' });

describe('activity form boundaries', () => {
  it('requires car occupancy and omits stale occupancy for passenger bus factors', () => {
    const fields = { ...valid(), mode: 'car_petrol' };
    expect(validate(fields, caps).occupancy).toBeDefined();
    fields.occupancy = '2';
    expect(validate(fields, caps)).toEqual({});
    fields.mode = 'bus';
    expect(calculationBody(fields, caps).input).not.toHaveProperty('occupancy');
  });
  it('does not infer appliance power or duty cycle from hours', () => {
    const fields = { ...valid(), category: 'electricity' as const, energyMethod: 'appliance' as const, grid: 'UK', hours: '4', powerBasis: 'rated' };
    expect(validate(fields, caps)).toMatchObject({ power: expect.any(String), duty: expect.any(String) });
    fields.power = '1.5';
    fields.duty = '0.5';
    expect(validate(fields, caps)).toEqual({});
    fields.grid = 'IN';
    expect(validate(fields, caps).grid).toBeDefined();
  });
  it('requires recipe agreement and rejects unsupported waste combinations', () => {
    const food = { ...valid(), category: 'food' as const, recipe: caps.recipes[0].value };
    expect(validate(food, caps).recipeAccepted).toBeDefined();
    expect(validate({ ...food, recipeAccepted: true }, caps)).toEqual({});
    expect(validate({ ...valid(), category: 'waste', material: 'paper', route: 'compost', mass: '1' }, caps).route).toBeDefined();
  });
  it('rejects nonfinite values, excess precision, invalid dates and future actual logs', () => {
    for (const distance of ['-1', 'NaN', 'Infinity', '1.1234567', '10001']) expect(validate({ ...valid(), distance }, caps).distance).toBeDefined();
    expect(validate({ ...valid(), date: '2026-02-30' }, caps).date).toBeDefined();
    expect(validate({ ...valid(), date: '2999-01-01' }, caps).date).toBeDefined();
    expect(validate({ ...valid(), distance: '0' }, caps)).toEqual({});
  });
  it('retains the frozen save request and its retry key across form restoration', () => {
    const draft = freshDraft(caps.local_today);
    draft.saveRequest = { calculation_id: 'owned-calculation', activity_date: caps.local_today, note: 'commute' };
    expect(restoreDraft(JSON.stringify(draft))).toEqual(draft);
    expect(restoreDraft('not json').saveRequest).toBeUndefined();
  });
});
