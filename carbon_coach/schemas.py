"""Application contract shared by OpenAPI, fixtures and frontend type generation."""
from datetime import date, datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal['travel', 'electricity', 'food', 'waste']
DecimalText = Annotated[str, Field(pattern=r'^\d+(?:\.\d{1,6})?$')]
Amount = Annotated[str, Field(pattern=r'^\d+\.\d{6}$')]
DisplayAmount = Annotated[str, Field(pattern=r'^\d+\.\d{2}$')]

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class SessionInput(Strict):
    timezone: str = 'Asia/Kolkata'
    locale: Literal['en'] = 'en'
    region: str = Field(default='UK', min_length=1, max_length=32)

class Travel(Strict):
    mode: Literal['bus', 'car_petrol', 'car_diesel']
    distance_km: DecimalText
    occupancy: int | None = Field(default=None, strict=True, ge=1, le=100)

class Electricity(Strict):
    kwh: DecimalText
    grid_region: Literal['UK']
    conversion_id: str | None = None

class Food(Strict):
    meal_type: Literal['pea_rice_bowl', 'chicken_rice_bowl']
    servings: DecimalText

class Waste(Strict):
    material: Literal['food', 'paper']
    mass_kg: DecimalText
    disposal_route: Literal['landfill', 'compost', 'recycling']

class FactorSelection(Strict):
    factor_id: str | None = None
    factor_version: str | None = None

    @model_validator(mode='after')
    def complete_factor_reference(self):
        if (self.factor_id is None) != (self.factor_version is None):
            raise ValueError('factor_id and factor_version must be supplied together')
        return self

class TravelCalc(FactorSelection):
    category: Literal['travel']
    input: Travel

class ElectricityCalc(FactorSelection):
    category: Literal['electricity']
    input: Electricity

class FoodCalc(FactorSelection):
    category: Literal['food']
    input: Food

class WasteCalc(FactorSelection):
    category: Literal['waste']
    input: Waste

CalculationInput = Annotated[TravelCalc | ElectricityCalc | FoodCalc | WasteCalc, Field(discriminator='category')]

class ActivityInput(Strict):
    calculation_id: str
    activity_date: date
    note: str = Field(default='', max_length=500)

class ActivityPatch(Strict):
    calculation_id: str | None = None
    activity_date: date | None = None
    note: str | None = Field(default=None, max_length=500)

class MessageInput(Strict):
    text: str = Field(min_length=1, max_length=4000, pattern=r'\S')
    language: Literal['en','hi','te'] = 'en'

class ReductionInput(Strict):
    period: Literal['today', 'week'] = 'week'

class Envelope(Strict):
    request_id: str
    status: Literal['success'] = 'success'

class FieldError(Strict):
    field: str
    reason: str

class ErrorDetail(Strict):
    code: str
    message: str
    retryable: bool
    field_errors: list[FieldError] = Field(default_factory=list)

class ErrorResponse(Strict):
    request_id: str
    status: Literal['error'] = 'error'
    error: ErrorDetail

class HealthResponse(Strict):
    status: Literal['ok']
    storage_mode: Literal['memory', 'database']
    chat_configured: bool

class ReadyResponse(Strict):
    status: Literal['ready']
    factor_count: int

class SessionResponse(Envelope):
    session_id: str
    session_token: str
    expires_at: datetime
    storage_mode: Literal['memory', 'database']
    timezone: str
    locale: Literal['en']
    region: str

class FactorRef(Strict):
    id: str
    version: str

class Factor(FactorRef):
    category: Literal['travel', 'electricity', 'waste', 'ingredient']
    # Registry precision must retain the published factor after unit conversion.
    # User activity inputs have a separate six-decimal limit.
    value: Annotated[str, Field(pattern=r'^\d+(?:\.\d+)?$')]
    denominator_unit: str
    gas_basis: Literal['CO2e']
    boundary: str
    geography: str
    reference_year: int
    source_publisher: str
    source_url: str
    source_locator: str
    source_value: str | None = None
    source_unit: str | None = None
    approved: bool
    fixture_only: bool
    limitations: str

class FactorListResponse(Envelope):
    items: list[Factor]
    recipes: dict[str, dict[str, DecimalText]]

class FactorResponse(Envelope):
    factor: Factor

class Calculation(Strict):
    id: str
    category: Category
    input: Travel | Electricity | Food | Waste
    normalized_quantity: Amount
    kg_co2e: Amount
    display_kg_co2e: DisplayAmount
    factor_refs: list[FactorRef]
    factor_snapshots: list[Factor]
    assumptions: list[str]
    warnings: list[str]
    claim_ids: list[str]
    created_at: datetime
    normalized_unit: str | None = None
    formula: str | None = None
    recipe_version: str | None = None
    energy_conversion: 'EnergyConversion | None' = None

class CalculationResponse(Envelope):
    calculation: Calculation

class Activity(Strict):
    id: str
    calculation_id: str
    category: Category
    activity_date: date
    kg_co2e: Amount
    note: str
    revision: int = Field(ge=1)
    deleted: bool
    created_at: datetime

class ActivityResponse(Envelope):
    activity: Activity

class ActivityListResponse(Envelope):
    items: list[Activity]
    next_cursor: str | None

class DailyBucket(Strict):
    date: date
    recorded_kg_co2e: Amount
    has_records: bool
    activity_count: int = Field(ge=0)

class CategoryTotals(Strict):
    travel: Amount
    electricity: Amount
    food: Amount
    waste: Amount

class Summary(Strict):
    start_date: date
    end_date: date
    timezone: str
    total_kg_co2e: Amount
    display_total_kg_co2e: DisplayAmount
    activity_count: int = Field(ge=0)
    by_category: CategoryTotals
    daily: list[DailyBucket]
    logged_day_count: int = Field(ge=0)
    coverage_note: str
    warnings: list[str]
    claim_ids: list[str]

class SummaryResponse(Envelope):
    summary: Summary

class ReductionScenario(Strict):
    id: str
    baseline_activity_ids: list[str]
    action: str
    baseline_kg_co2e: Amount
    alternative_kg_co2e: Amount
    saving_kg_co2e: Amount
    alternative: Calculation
    overlap_group: str
    assumptions: list[str]
    claim_ids: list[str]

class ReductionResponse(Envelope):
    suggestions: list[ReductionScenario]
    unavailable_reason: str | None

class MessageResponse(Strict):
    request_id: str
    status: Literal['success', 'needs_clarification', 'partial_failure']
    reply: str
    message_id: str
    committed_activity_ids: list[str]
    warnings: list[str]
    tool_calls: list[str] = Field(default_factory=list)

class ChatMessage(Strict):
    id: str
    role: Literal['user','assistant']
    text: str
    created_at: datetime
    status: Literal['success','needs_clarification','partial_failure'] = 'success'
    tool_calls: list[str] = Field(default_factory=list)

class ChatHistoryResponse(Envelope):
    messages: list[ChatMessage]

class ActivityDetailResponse(Envelope):
    activity: Activity
    calculation: Calculation

class BrowserBootstrapResponse(Envelope):
    csrf_token: str

class SessionSettingsInput(Strict):
    timezone: str = Field(min_length=1, max_length=64)

class BrowserSessionResponse(Envelope):
    session_id: str
    expires_at: datetime
    storage_mode: Literal['memory', 'database']
    timezone: str
    locale: Literal['en']
    region: str
    csrf_token: str
    chat_mode: Literal['mock', 'configured', 'unavailable']

class ApplianceInput(Strict):
    power_kw: DecimalText
    hours: DecimalText
    power_basis: Literal['average', 'rated']
    duty_cycle: DecimalText | None = None

class EnergyConversion(Strict):
    id: str
    input: ApplianceInput
    kwh: Amount
    formula: str
    assumptions: list[str]
    created_at: datetime

class EnergyConversionResponse(Envelope):
    conversion: EnergyConversion

class TravelChoice(Strict):
    value: str
    label: str
    factor_ref: FactorRef
    requires_occupancy: bool

class GridChoice(Strict):
    value: str
    label: str
    factor_ref: FactorRef

class IngredientChoice(Strict):
    label: str
    mass_kg: DecimalText
    factor_ref: FactorRef

class RecipeChoice(Strict):
    value: str
    label: str
    version: str
    ingredients: list[IngredientChoice]
    exclusions: list[str]

class WasteRouteChoice(Strict):
    value: str
    label: str
    factor_ref: FactorRef

class WasteChoice(Strict):
    value: str
    label: str
    routes: list[WasteRouteChoice]

class InputLimits(Strict):
    decimal_places: int
    distance_km_max: DecimalText
    occupancy_max: int
    kwh_max: DecimalText
    power_kw_max: DecimalText
    hours_max: DecimalText
    servings_max: DecimalText
    mass_kg_max: DecimalText
    note_max_length: int

class CapabilitiesResponse(Envelope):
    local_today: date
    timezone: str
    travel: list[TravelChoice]
    grids: list[GridChoice]
    recipes: list[RecipeChoice]
    waste: list[WasteChoice]
    limits: InputLimits
    regional_notice: str

Calculation.model_rebuild()
