/**
 * Checkpoint 3 contracts mirrored from backend/marginguard/schemas.py.
 * Runtime authority: GET /openapi.json. Alerts/chat writes still return 501.
 * Decimal strings are unsigned fixed decimals with up to eight fractional digits.
 */
export type ApiVersion = '1.0.0';
export type DecimalString = string;
/** Signed metrics include modeled losses and changes; input amounts remain unsigned. */
export type SignedDecimalString = string;
export type ISODate = string;
export type ISODateTime = string;
export type Currency = 'USD';
export type DocumentType = 'invoice' | 'receipt';
export type DocumentStatus = 'detected' | 'processing' | 'completed' | 'needs_review' | 'failed';
export type CoverageStatus = 'complete' | 'partial' | 'unknown' | 'closed';
export type ChannelId = 'in_store' | 'delivery';
export type BaseUnit = 'lb' | 'oz' | 'each';
export type PurchaseUnit = BaseUnit | 'case';
export type ReceiptStatus = 'completed' | 'void' | 'refund';

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type ListResponse<T> = Page<T>;

export interface ErrorDetail {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface ErrorResponse {
  api_version: ApiVersion;
  error: ErrorDetail;
}

export interface Restaurant {
  id: string;
  name: string;
  currency: Currency;
  timezone: string;
  data_version: number;
  is_demo: boolean;
}

export interface Ingredient {
  id: string;
  name: string;
  base_unit: BaseUnit;
  aliases: string[];
}

export interface Channel {
  id: ChannelId;
  name: string;
  fee_rate: DecimalString;
  packaging_cost: DecimalString;
}

export interface MenuPrice {
  id: string;
  channel_id: ChannelId;
  price: DecimalString;
  effective_date: ISODate;
}

export interface RecipeItem {
  id: string;
  ingredient_id: string;
  quantity: DecimalString;
  unit: BaseUnit;
}

export interface RecipeVersion {
  id: string;
  effective_date: ISODate;
  items: RecipeItem[];
}

export interface Dish {
  id: string;
  name: string;
  prices: MenuPrice[];
  recipes: RecipeVersion[];
}

export interface CatalogResponse {
  source_data_version: number;
  is_demo: boolean;
  ingredients: Ingredient[];
  dishes: Dish[];
  channels: Channel[];
  vendors: { id: string; name: string; aliases: string[] }[];
}

export interface IngredientPrice {
  id: string;
  ingredient_id: string;
  invoice_line_id: string;
  effective_date: ISODate;
  unit_cost: DecimalString;
  base_unit: BaseUnit;
}

export interface Document {
  id: string;
  type: DocumentType;
  filename: string;
  sha256: string;
  media_type: string;
  status: DocumentStatus;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  is_demo: boolean;
  error_code: string | null;
  error_message: string | null;
}

/** The detail route includes persisted text; paginated document lists omit it. */
export interface DocumentDetail extends Document {
  source_text: string | null;
  page_count: number | null;
  evidence_mode: 'text' | 'visual' | 'unavailable';
  extraction_method: string | null;
  extraction: InvoiceExtraction | ReceiptExtraction | null;
  validation_issues: { code: string; message: string; item_index: number | null; existing_document_id?: string }[];
  reviewed_at: ISODateTime | null;
  review_note: string | null;
}

export interface InvoiceExtractionItem {
  description: string;
  ingredient_id: string | null;
  quantity: DecimalString;
  purchase_unit: PurchaseUnit;
  pack_size: DecimalString | null;
  pack_unit: BaseUnit | null;
  unit_price: DecimalString;
  line_total: DecimalString;
  source_page: number;
  source_text: string;
}

export interface InvoiceExtraction {
  vendor_id: string | null;
  vendor_name: string;
  invoice_number: string;
  invoice_date: ISODate;
  currency: Currency;
  subtotal: DecimalString;
  tax: DecimalString;
  freight: DecimalString;
  total: DecimalString;
  items: InvoiceExtractionItem[];
}

export type InvoiceItemInput = InvoiceExtractionItem;

export interface InvoiceItem extends InvoiceItemInput {
  id: string;
}

export interface Invoice extends Omit<InvoiceExtraction, 'vendor_id' | 'items'> {
  id: string;
  document_id: string;
  vendor_id: string;
  items: InvoiceItem[];
}

export interface ReceiptExtractionItem {
  description: string;
  dish_id: string | null;
  quantity: DecimalString;
  unit_price: DecimalString;
  gross_amount: DecimalString;
  discount_amount: DecimalString;
  net_amount: DecimalString;
  source_page: number;
  source_text: string;
}

export interface ReceiptExtraction {
  receipt_number: string;
  sold_at: ISODateTime;
  channel_id: ChannelId | null;
  status: ReceiptStatus;
  currency: Currency;
  subtotal: DecimalString;
  discount: DecimalString;
  tax: DecimalString;
  tip: DecimalString;
  total: DecimalString;
  items: ReceiptExtractionItem[];
}

export type ReceiptItemInput = ReceiptExtractionItem;

export interface ReceiptItem extends ReceiptItemInput {
  id: string;
}

export interface Receipt extends Omit<ReceiptExtraction, 'items'> {
  id: string;
  document_id: string;
  local_date: ISODate;
  items: ReceiptItem[];
}

export interface Coverage {
  date: ISODate;
  channel_id: ChannelId;
  status: CoverageStatus;
  updated_at: ISODateTime;
}

export interface EvidenceReference {
  kind: 'invoice_line' | 'receipt_item' | 'forecast_run' | 'document';
  record_id: string;
  document_id: string | null;
  source_page: number | null;
  quote: string | null;
}

export interface Alert {
  id: string;
  event_key: string;
  type: 'ingredient_price_spike' | 'projected_cost_increase' | 'unusual_sales' | 'data_quality';
  severity: 'info' | 'warning' | 'critical';
  status: 'new' | 'acknowledged' | 'resolved';
  title: string;
  message: string;
  evidence: EvidenceReference[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface Period {
  start: ISODate;
  end: ISODate;
}

export interface Metric {
  id: string;
  label: string;
  value: SignedDecimalString | null;
  unit: 'USD' | 'units' | 'orders' | 'percent' | 'lb' | 'oz' | 'each';
  kind: 'actual' | 'modeled' | 'projected';
  period: Period | null;
  as_of: ISODateTime;
  coverage: 'complete' | 'partial' | 'unknown' | 'insufficient_history';
  source_data_version: number;
  evidence: EvidenceReference[];
  assumptions: string[];
}

export interface ForecastResponse {
  id: string;
  status: 'pending' | 'ready' | 'insufficient_history' | 'failed';
  horizon: Period;
  method: string;
  source_data_version: number;
  created_at: ISODateTime;
  metrics: Metric[];
  assumptions: string[];
  as_of: ISODate | null;
  training_period: Period | null;
  training_coverage: CoverageSummary | null;
  series: ForecastSeries[];
  daily: ForecastDay[];
  ingredients: IngredientRequirement[];
  scenarios: ForecastScenario[];
  evaluation: ForecastEvaluation | null;
  limitations: string[];
}

export interface CoverageSummary {
  period: Period;
  complete: number;
  partial: number;
  unknown: number;
  closed: number;
  status: 'complete' | 'partial' | 'unknown';
  days: Coverage[];
}

export interface SalesGroup {
  date: ISODate | null;
  dish_id: string | null;
  channel_id: ChannelId | null;
  units: DecimalString;
  net_revenue: DecimalString;
  orders: number;
}

export interface SalesSummary {
  period: Period;
  as_of: ISODateTime;
  source_data_version: number;
  units: DecimalString;
  net_revenue: DecimalString;
  orders: number;
  average_order_revenue: DecimalString | null;
  coverage: CoverageSummary;
  by_day: SalesGroup[];
  by_dish: SalesGroup[];
  by_channel: SalesGroup[];
  evidence: EvidenceReference[];
  evidence_truncated: boolean;
  assumptions: string[];
}

export interface RecipeCostLine {
  ingredient_id: string;
  name: string;
  quantity: DecimalString;
  base_unit: BaseUnit;
  unit_cost: DecimalString | null;
  extended_cost: DecimalString | null;
  price_effective_date: ISODate | null;
  evidence: EvidenceReference | null;
}

export interface ChannelContribution {
  channel_id: ChannelId;
  menu_price: DecimalString | null;
  menu_price_id: string | null;
  fee_rate: DecimalString;
  packaging_cost: DecimalString;
  contribution: SignedDecimalString | null;
  contribution_margin_pct: SignedDecimalString | null;
}

export interface DishCost {
  dish_id: string;
  name: string;
  as_of: ISODate;
  source_data_version: number;
  recipe_version_id: string | null;
  ingredient_cost: DecimalString | null;
  ingredients: RecipeCostLine[];
  channels: ChannelContribution[];
  limitations: string[];
  assumptions: string[];
}

export interface ForecastRequest {
  as_of?: ISODate;
  history_weeks?: number;
  min_observations?: number;
  sensitivity_pct?: DecimalString;
}

export interface WeekdayEstimate {
  weekday: number;
  sample_dates: ISODate[];
  mean_units: DecimalString | null;
}

export interface ForecastSeries {
  dish_id: string;
  channel_id: ChannelId;
  status: 'ready' | 'insufficient_history' | 'missing_inputs';
  units: DecimalString | null;
  revenue: DecimalString | null;
  ingredient_cost: DecimalString | null;
  menu_price: DecimalString | null;
  recipe_version_id: string | null;
  weekday_estimates: WeekdayEstimate[];
  limitations: string[];
}

export interface ForecastDay {
  date: ISODate;
  dish_id: string;
  channel_id: ChannelId;
  is_open: boolean;
  units: DecimalString | null;
}

export interface IngredientRequirement {
  ingredient_id: string;
  quantity: DecimalString;
  base_unit: BaseUnit;
  unit_cost: DecimalString;
  cost: DecimalString;
  evidence: EvidenceReference;
}

export interface ForecastScenario {
  name: 'low' | 'base' | 'high';
  volume_multiplier: DecimalString;
  units: DecimalString;
  revenue: DecimalString;
  ingredient_cost: DecimalString;
}

export interface ForecastEvaluation {
  status: 'ready' | 'insufficient_history';
  holdout: Period;
  observations: number;
  weekday_average_mae: DecimalString | null;
  seasonal_naive_mae: DecimalString | null;
  assumptions: string[];
}

export interface DashboardResponse {
  api_version: ApiVersion;
  restaurant: Restaurant;
  as_of: ISODateTime;
  source_data_version: number;
  metrics: Metric[];
  forecast: ForecastResponse | null;
  alerts: Alert[];
  limitations: string[];
  sales: SalesSummary | null;
  dish_costs: DishCost[];
}

export interface ChatRequest {
  question: string;
}

export interface ChatResponse {
  answer: string;
  as_of: ISODateTime;
  metrics: Metric[];
  evidence: EvidenceReference[];
  limitations: string[];
}

export interface InvoiceReview {
  document_type: 'invoice';
  extraction: InvoiceExtraction;
  note?: string;
}

export interface ReceiptReview {
  document_type: 'receipt';
  extraction: ReceiptExtraction;
  note?: string;
}

export type ReviewRequest = InvoiceReview | ReceiptReview;

export interface CoverageRequest {
  date: ISODate;
  channel_id: ChannelId;
  status?: 'complete' | 'closed';
}

export interface Capability {
  name: string;
  available: boolean;
  checkpoint: number;
}

export interface CapabilitiesResponse {
  api_version: ApiVersion;
  checkpoint: 3;
  capabilities: Capability[];
}
