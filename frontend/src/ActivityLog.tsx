import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, BookOpen, Bus, Check, CheckCircle2, ChevronRight, CircleAlert, Leaf, LoaderCircle, PlugZap, RotateCcw, Sprout, Trash2 } from 'lucide-react';
import { api, ApiError, savedDraft, saveDraft } from './api/client';
import type { ActivityInput, ActivityResponse, Calculation, CalculationResponse, CapabilitiesResponse, EnergyConversionResponse } from './api/schema';
import { calculationBody, fingerprint, freshDraft, restoreDraft, validate, type Category, type Draft, type Errors, type Fields } from './activityForm';
import { SESSION_KEY, useSession } from './session';
import type { BrowserSessionResponse } from './api/schema';
import { ErrorNotice, Loading, PageHeading } from './components';

const categories: Array<{ value: Category; label: string; icon: typeof Bus }> = [
  { value: 'travel', label: 'Travel', icon: Bus }, { value: 'electricity', label: 'Electricity', icon: PlugZap },
  { value: 'food', label: 'Food', icon: Sprout }, { value: 'waste', label: 'Waste', icon: Trash2 },
];

export function ActivityLog() {
  const { session } = useSession();
  const caps = useQuery({ queryKey: ['capabilities', session!.session_id, session!.timezone],
    queryFn: ({ signal }) => api<CapabilitiesResponse>(`/api/v1/sessions/${session!.session_id}/capabilities`, { signal }) });
  return <><PageHeading eyebrow="SMALL THINGS, RECORDED" title="Log an everyday activity">Describe the details, check your estimate, then choose whether to save it.</PageHeading>
    {caps.isPending ? <Loading label="Loading supported activities…" /> : caps.error ? <ErrorNotice error={caps.error} retry={() => { void caps.refetch(); }} /> :
      <ActivityForm key={session!.session_id} caps={caps.data!} sessionId={session!.session_id} />}
  </>;
}

function ActivityForm({ caps, sessionId }: { caps: CapabilitiesResponse; sessionId: string }) {
  const cache = useQueryClient();
  const storageKey = `activity:${sessionId}`;
  const [draft, setDraft] = useState<Draft>(() => {
    const restored = restoreDraft(savedDraft(storageKey, ''));
    if (!restored.fields.date) restored.fields.date = caps.local_today;
    return restored;
  });
  const [errors, setErrors] = useState<Errors>({});
  const form = useRef<HTMLFormElement>(null);
  const busy = useRef(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const persist = (next: Draft) => { if (alive.current && cache.getQueryData<BrowserSessionResponse | null>(SESSION_KEY)?.session_id === sessionId) { saveDraft(storageKey, JSON.stringify(next)); setDraft(next); } };
  const fields = draft.fields;
  const compatible = draft.previewFor === fingerprint(fields);
  const evidence = useQuery({ queryKey: ['calculation', sessionId, draft.previewId],
    enabled: Boolean(draft.previewId && compatible), retry: false,
    queryFn: ({ signal }) => api<CalculationResponse>(`/api/v1/sessions/${sessionId}/calculations/${draft.previewId}`, { signal }) });
  const receipt = compatible ? evidence.data?.calculation : undefined;
  const preview = useMutation({ mutationFn: async (snapshot: Draft) => {
    let energy;
    if (snapshot.fields.category === 'electricity' && snapshot.fields.energyMethod === 'appliance') {
      const conversion = await api<EnergyConversionResponse>(`/api/v1/sessions/${sessionId}/energy-conversions`, { method: 'POST', mutationKey: snapshot.conversionKey,
        body: { power_kw: snapshot.fields.power, hours: snapshot.fields.hours, power_basis: snapshot.fields.powerBasis,
          ...(snapshot.fields.powerBasis === 'rated' ? { duty_cycle: snapshot.fields.duty } : {}) } });
      energy = conversion.conversion;
    }
    return api<CalculationResponse>(`/api/v1/sessions/${sessionId}/calculations`, { method: 'POST', mutationKey: snapshot.previewKey, body: calculationBody(snapshot.fields, caps, energy) });
  }, onSuccess: (result, snapshot) => {
    if (!alive.current) return;
    cache.setQueryData(['calculation', sessionId, result.calculation.id], result);
    persist({ ...snapshot, previewId: result.calculation.id, previewFor: fingerprint(snapshot.fields) });
  }, onSettled: () => { busy.current = false; } });
  const save = useMutation({ mutationFn: (operation: { request: ActivityInput; key: string }) => api<ActivityResponse>(`/api/v1/sessions/${sessionId}/activities`, { method: 'POST', mutationKey: operation.key, body: operation.request }),
    onSuccess: (response) => {
      void cache.invalidateQueries({ predicate: query => ['summary', 'activities', 'reductions'].includes(String(query.queryKey[0])) && query.queryKey.includes(sessionId) });
      if (!alive.current) return;
      persist({ ...draft, savedId: response.activity.id, saveRequest: undefined });
    }, onError: error => {
      if (!alive.current) return;
      // A network or server error may follow a successful commit. Keep the
      // frozen operation until the same request key confirms its outcome.
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) persist({ ...draft, saveRequest: undefined });
    }, onSettled: () => { busy.current = false; } });
  const unresolvedSave = Boolean(draft.saveRequest && !draft.savedId);
  const locked = preview.isPending || save.isPending || unresolvedSave || Boolean(draft.savedId);

  function change<K extends keyof Fields>(key: K, value: Fields[K]) {
    if (locked || busy.current) return;
    const updated = { ...fields, [key]: value };
    if (key === 'material') updated.route = '';
    if (key === 'recipe') updated.recipeAccepted = false;
    persist({ ...freshDraft(updated.date, updated.category), fields: updated });
    setErrors({}); preview.reset(); save.reset();
  }
  function switchCategory(category: Category) {
    if (busy.current || preview.isPending || save.isPending || unresolvedSave) return;
    if (category === fields.category && !draft.savedId) return;
    persist(freshDraft(caps.local_today, category)); setErrors({}); preview.reset(); save.reset();
  }
  function calculate(event: FormEvent) {
    event.preventDefault();
    if (busy.current || locked) return;
    const invalid = validate(fields, caps); setErrors(invalid);
    if (Object.keys(invalid).length) { setTimeout(() => form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus(), 0); return; }
    busy.current = true;
    saveDraft(storageKey, JSON.stringify(draft));
    preview.mutate(draft);
  }
  function commit() {
    if (busy.current || draft.savedId || !receipt || !compatible) return;
    const invalid = validate(fields, caps); setErrors(invalid);
    if (Object.keys(invalid).length) return;
    const request = draft.saveRequest ?? { calculation_id: receipt.id, activity_date: fields.date, note: fields.note };
    busy.current = true;
    persist({ ...draft, saveRequest: request });
    save.mutate({ request, key: draft.saveKey });
  }
  const input = (key: keyof Fields, label: string, placeholder = '', help?: string, type = 'text') => <Field label={label} id={`log-${key}`} error={errors[key]} help={help}>
    <input id={`log-${key}`} type={type} inputMode={type === 'text' ? 'decimal' : undefined} placeholder={placeholder} value={String(fields[key])} disabled={locked} onChange={event => change(key, event.target.value as never)} aria-invalid={Boolean(errors[key])} aria-describedby={`log-${key}-help`} {...(type === 'date' ? { max: caps.local_today } : {})} />
  </Field>;
  const select = (key: keyof Fields, label: string, options: Array<{ value: string; label: string }>, help?: string) => <Field label={label} id={`log-${key}`} error={errors[key]} help={help}>
    <select id={`log-${key}`} value={String(fields[key])} disabled={locked} onChange={event => change(key, event.target.value as never)} aria-invalid={Boolean(errors[key])} aria-describedby={`log-${key}-help`}><option value="">Choose an option</option>{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
  </Field>;
  const recipe = caps.recipes.find(item => item.value === fields.recipe);
  const material = caps.waste.find(item => item.value === fields.material);
  const selectedMode = caps.travel.find(item => item.value === fields.mode);

  return <>
    <div className="activity-categories" role="group" aria-label="Activity category">{categories.map(category => <button key={category.value} type="button" aria-pressed={fields.category === category.value} disabled={preview.isPending || save.isPending || unresolvedSave} onClick={() => switchCategory(category.value)}><category.icon size={21} strokeWidth={1.6} /><span>{category.label}</span>{fields.category === category.value && <Check size={15} />}</button>)}</div>
    <div className="activity-layout"><section className="panel entry-panel"><div className="panel-heading"><h2>{categories.find(item => item.value === fields.category)!.label} details</h2><span className="soft-tag">STEP 1 · DESCRIBE</span></div>
      <form ref={form} onSubmit={calculate} noValidate>
        {fields.category === 'travel' && <>{select('mode', 'Travel mode', caps.travel, 'UK operational reference factors. Bus is already allocated per passenger.')}{input('distance', 'Distance travelled (km)', 'e.g. 12')}{selectedMode?.requires_occupancy && input('occupancy', 'People in the car', 'Include the driver', 'Vehicle emissions are divided equally among the people you specify.')}</>}
        {fields.category === 'electricity' && <>
          {select('grid', 'Reference grid', caps.grids, 'Only a UK grid reference is available. An India grid factor is not configured.')}
          <fieldset className="energy-method" disabled={locked}><legend>How do you know the energy used?</legend><label><input type="radio" name="energyMethod" checked={fields.energyMethod === 'measured'} onChange={() => change('energyMethod', 'measured')} />Measured kWh</label><label><input type="radio" name="energyMethod" checked={fields.energyMethod === 'appliance'} onChange={() => change('energyMethod', 'appliance')} />Appliance power and time</label></fieldset>
          {fields.energyMethod === 'measured' ? input('kwh', 'Electricity used (kWh)', 'e.g. 6') : <>
            {select('powerBasis', 'Power measurement', [{ value: 'average', label: 'Average electrical input power' }, { value: 'rated', label: 'Rated electrical input power' }], 'Use electrical input from a meter or appliance specification, not cooling capacity.')}
            <div className="field-pair">{input('power', 'Electrical input power (kW)', 'e.g. 1.5')}{input('hours', 'Hours used', 'e.g. 4', `Maximum ${caps.limits.hours_max} hours per daily entry.`)}</div>
            {fields.powerBasis === 'rated' && input('duty', 'Duty cycle (fraction)', 'e.g. 0.5', 'Specify the fraction of time drawing rated input power. A fraction of 1 means the entire stated duration. Do not guess it.')}
          </>}
        </>}
        {fields.category === 'food' && <>{select('recipe', 'Defined meal recipe', caps.recipes)}{input('servings', 'Number of servings', 'e.g. 1')}{recipe && <div className="recipe-definition"><h3>Per serving, using raw product mass</h3><ul>{recipe.ingredients.map(ingredient => <li key={ingredient.factor_ref.id}><span>{ingredient.label.replaceAll('_', ' ')}</span><strong>{ingredient.mass_kg} kg</strong></li>)}</ul><small>Excluded: {recipe.exclusions.join(', ')}. Global supply-chain averages; portions are not nutritional equivalents.</small><label className="check-label"><input type="checkbox" checked={fields.recipeAccepted} disabled={locked} onChange={event => change('recipeAccepted', event.target.checked)} aria-invalid={Boolean(errors.recipeAccepted)} aria-describedby="recipe-error" />These recipe assumptions match the entry I want to estimate.</label>{errors.recipeAccepted && <small id="recipe-error" className="field-error">{errors.recipeAccepted}</small>}</div>}</>}
        {fields.category === 'waste' && <>{select('material', 'Waste material', caps.waste)}{select('route', 'Treatment route', material?.routes ?? [], 'Choose the treatment your collection actually uses. Unsupported combinations are not estimated.')}{input('mass', 'Waste mass (kg)', 'e.g. 1')}</>}
        <div className="entry-divider" />
        {input('date', 'Activity date', '', `Dates use ${caps.timezone}.`, 'date')}
        <Field label="Note (optional)" id="log-note" error={errors.note} help={`Up to ${caps.limits.note_max_length} characters. Avoid sensitive information.`}><textarea id="log-note" value={fields.note} rows={2} maxLength={caps.limits.note_max_length} disabled={locked} onChange={event => change('note', event.target.value)} aria-invalid={Boolean(errors.note)} aria-describedby="log-note-help" /></Field>
        {Object.keys(errors).length > 0 && <div className="validation-summary" role="alert"><CircleAlert size={17} />Check the highlighted fields before previewing or saving.</div>}
        {preview.error && <ErrorNotice error={preview.error} />}
        <button className="button button-primary preview-button" type="submit" disabled={locked}>{preview.isPending ? <><LoaderCircle className="spin" size={16} />Calculating…</> : <>Preview estimate<ArrowRight size={16} /></>}</button>
        <p className="entry-privacy">Previewing never adds an activity to your recorded totals.</p>
      </form>
    </section>
    <aside className="preview-column" aria-label="Calculation preview"><section className={`panel estimate-panel ${receipt ? 'has-estimate' : ''}`}><div className="panel-heading"><h2>Your estimate</h2><span className="soft-tag">STEP 2 · REVIEW</span></div>
      {evidence.isFetching && !receipt ? <Loading label="Restoring your estimate…" /> : evidence.error ? <ErrorNotice error={evidence.error} retry={() => { void evidence.refetch(); }} /> : receipt ? <>
        <p className="estimate-value">{receipt.display_kg_co2e}<span>kg CO₂e</span></p>
        <p className="estimate-scope">Estimated {receipt.category} emissions · {draft.savedId ? 'Saved to your record' : 'Not saved yet'}</p>
        {receipt.energy_conversion && <div className="conversion-receipt"><PlugZap size={17} /><div><strong>{receipt.energy_conversion.kwh} kWh</strong><small>Energy conversion: {receipt.energy_conversion.formula}</small></div></div>}
        <Evidence calculation={receipt} />
        {draft.savedId ? <div className="saved-receipt" role="status"><CheckCircle2 size={23} /><div><strong>Activity saved</strong><p>{fields.date}{fields.note ? ` · ${fields.note}` : ''}</p></div></div> : <>
          {unresolvedSave && !save.isPending && <div className="notice save-recovery" role="status"><CircleAlert size={18} /><span>The save is not confirmed. Retry the same request to find out whether it was saved. Details are locked to avoid duplicates.</span></div>}
          {save.error && <ErrorNotice error={save.error} />}
          <button className="button button-primary button-full save-button" onClick={commit} disabled={save.isPending || preview.isPending || !compatible}>{save.isPending ? 'Saving activity…' : unresolvedSave ? 'Retry save safely' : 'Save activity'}{!save.isPending && <Check size={17} />}</button>
          <p className="entry-privacy">Only this action adds the estimate to your logged totals.</p>
        </>}
        {draft.savedId && <div className="receipt-actions"><Link className="text-link" to="/activities">View activity history <ChevronRight size={15} /></Link><button className="button button-secondary" onClick={() => switchCategory(fields.category)}><RotateCcw size={15} />Log another activity</button></div>}
      </> : <div className="estimate-empty"><span className="empty-icon"><Leaf size={42} strokeWidth={1} /></span><h3>Details first.<br />A clear estimate next.</h3><p>Fill in the activity on the left and preview a calculation. Changing the details clears the old preview.</p><div className="preview-check"><Check size={15} />Calculated by Python tools</div><div className="preview-check"><Check size={15} />Source evidence included</div><div className="preview-check"><Check size={15} />You choose when to save</div></div>}
    </section><div className="regional-caption"><BookOpen size={16} /><p>{caps.regional_notice} <Link to="/sources">Explore sources</Link></p></div></aside>
    </div>
  </>;
}

function Field({ label, id, error, help, children }: { label: string; id: string; error?: string; help?: string; children: ReactNode }) {
  return <div className="activity-field"><label htmlFor={id}>{label}</label>{children}<small id={`${id}-help`} className={error ? 'field-error' : ''}>{error ?? help}</small></div>;
}

function Evidence({ calculation }: { calculation: Calculation }) {
  return <details className="estimate-evidence"><summary>Sources and assumptions<ChevronRight size={16} /></summary><div>
    {calculation.formula && <p className="calculation-formula">Calculation: {calculation.formula}</p>}
    {calculation.recipe_version && <p>Recipe: {calculation.recipe_version}</p>}
    {calculation.energy_conversion?.assumptions.map(item => <p key={item}>{item}</p>)}
    {calculation.assumptions.map(item => <p key={item}>{item}</p>)}
    {calculation.factor_snapshots.map(source => <article key={source.id}><strong>{source.id.replaceAll('_', ' ')} · {source.geography}</strong><p>{source.value} kg CO₂e / {source.denominator_unit}</p><p>{source.source_publisher} · {source.version}</p><small>{source.source_locator}</small>{source.source_url.startsWith('https://') && <a target="_blank" rel="noreferrer" href={source.source_url}>Read original source <ArrowRight size={12} /></a>}</article>)}
    {calculation.warnings.map(item => <p key={item}>{item}</p>)}
  </div></details>;
}
