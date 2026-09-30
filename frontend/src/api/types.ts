export interface Finding {
  rule_id: string;
  name: string;
  severity: "blocker" | "major" | "minor" | "info";
  status: "pass" | "fail" | "skipped";
  manual_review: boolean;
  weight: number;
  scope: string;
  details: string | null;
  pp_reference: string | null;
}

export interface Judge {
  skipped: boolean;
  error: string | null;
  clarity: number | null;
  scope_discipline: number | null;
  persona_defined: boolean | null;
  orchestrator_pattern_detected: boolean | null;
  child_pattern_detected: boolean | null;
  output_format_guidance: boolean | null;
  top_strengths: string[] | null;
  top_weaknesses: string[] | null;
  recommended_changes: string[] | null;
  summary: string | null;
}

export interface Telemetry {
  window_days: number;
  run_count: number | null;
  error_count: number | null;
  p95_latency_ms: number | null;
  source: string | null;
}

export interface EnvironmentCard {
  environment_id: number | null;
  name: string;
  latest_scan_id: number;
  agent_count: number;
  avg_score: number | null;
  grade: string | null;
  scanned_at: string | null;
}

export interface AgentListItem {
  bot_id: string | null;
  agent_name: string;
  solution_name: string | null;
  publish_state: string | null;
  score: number | null;
  grade: string | null;
  scan_id: number;
  environment_id: number | null;
  environment_name?: string | null;
}

export interface RuleItem {
  rule_id: string;
  name: string;
  severity: string;
  scope: string | null;
  pp_reference: string | null;
  enabled: boolean;
  weight: number;
  explanation: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface AgentDetail {
  bot_id: string;
  agent_name: string;
  solution_name: string | null;
  solution_id: string | null;
  solution_url: string | null;
  agent_url: string | null;
  publish_state: string | null;
  score: number | null;
  grade: string | null;
  scan_id: number;
  environment_id: number | null;
  environment_name: string | null;
  environment_guid: string | null;
  schema_name: string | null;
  model_hint: string | null;
  created_on: string | null;
  modified_on: string | null;
  created_by_name: string | null;
  created_by_upn: string | null;
  findings: Finding[];
  judge: Judge | null;
  telemetry: Telemetry | null;
}

/** One agent created by the signed-in person. The API derives "mine" from the
 *  token, so there is no user id anywhere in these calls. */
export interface MyAgentCard {
  bot_id: string | null;
  agent_name: string;
  solution_name: string | null;
  publish_state: string | null;
  score: number | null;
  grade: string | null;
  scan_id: number | null;
  environment_id: number | null;
  environment_name: string | null;
  open_findings: number;
  modified_on: string | null;
}

export interface MySummary {
  agents: number;
  scored_agents: number;
  avg_score: number | null;
  worst_grade: string | null;
  worst_grade_agents: number;
  open_findings: number;
  agents_with_findings: number;
  environments: number;
  has_data: boolean;
}

export interface HistoryPoint {
  scan_id: number;
  score: number | null;
  grade: string | null;
  captured_at: string | null;
}

export interface ScanRow {
  id: number;
  environment: string;
  source: string;
  trigger: string;
  agent_count: number;
  avg_score: number | null;
  grade: string | null;
  started_at: string | null;
}

export interface AppConfig {
  tenant_id: string | null;
  client_id: string | null;
  has_client_secret: boolean;
  aoai_base_url: string | null;
  aoai_model: string | null;
  has_aoai_key: boolean;
  report_access_group_id: string | null;
  org_view_group_id: string | null;
  admin_group_id: string | null;
  schedule_interval_hours: number;
  configured: boolean;
  judge_configured: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

export interface Environment {
  id: number;
  display_name: string;
  dataverse_url: string | null;
  app_insights_app_id: string | null;
  has_app_insights_key: boolean;
  enabled: boolean;
  created_at: string | null;
  last_scanned?: string | null;
  last_agent_count?: number | null;
}

export interface ScanProgress {
  scan_id: number;
  environment_id: number | null;
  source: string;
  agents_done: number;
  agent_count: number;
  started_at: string | null;
}

/** One period's worth of the executive briefing. Every figure is computed in
 *  SQL; the page turns them into sentences but never invents one. */
export interface BriefingPeriod {
  agents: number;
  avg_score: number | null;
  environments: number;
  grades: Record<string, number>;
  open_findings: number;
  findings_by_severity: Record<string, number>;
}

export interface BriefingRule {
  rule_id: string;
  name: string;
  severity: string;
  agents: number;
}

export interface BriefingAgent {
  bot_id: string | null;
  agent_name: string;
  score: number | null;
  grade: string | null;
  scan_id: number;
}

export interface Briefing {
  window_days: number;
  period_end: string | null;
  has_data: boolean;
  current: BriefingPeriod;
  previous: BriefingPeriod;
  trend: { date: string; avg_score: number | null }[];
  worst_agents: BriefingAgent[];
  top_rules: BriefingRule[];
}

/** One person who has created at least one agent. Built from the maker stamped
 *  on each agent — this app holds no directory data, so this is not, and is not
 *  presented as, a listing of everyone in the tenant. */
export interface AgentCreator {
  upn: string;
  display_name: string | null;
  /** Directory details, present once the creator lookup has resolved them.
   *  Null on an unresolved creator, who is still listed — by UPN. */
  department: string | null;
  job_title: string | null;
  manager_name: string | null;
  office_location: string | null;
  directory_resolved: boolean;
  agents: number;
  scored_agents: number;
  avg_score: number | null;
  grades: Record<string, number>;
  open_findings: number;
  environments: string[];
}

export function cleanPP(value: string | null | undefined): string {
  return (value || "").replace(/^\s*slide\s+\d+\s*[-–—:]\s*/i, "").trim();
}

/** You, your team and your organisation, on the two measures this app has.
 *
 *  `team` is null when it is withheld, and `team_omitted_reason` says which of
 *  the four reasons applies — they are not interchangeable, and the sentence
 *  shown must not imply a problem with the reader's directory record when the
 *  real reason is that they have never created an agent. */
export interface PeerSeries {
  agents: number;
  avg_score: number | null;
}

export type TeamOmittedReason =
  | "not_a_creator"
  | "directory_unresolved"
  | "unknown_team"
  | "too_small";

export interface PeerComparisonData {
  period_from: string | null;
  period_to: string | null;
  mine: PeerSeries;
  team: PeerSeries | null;
  team_label: string | null;
  team_size: number;
  team_omitted_reason: TeamOmittedReason | null;
  organisation: PeerSeries;
  organisation_size: number;
  percentile: { agents: number | null; avg_score: number | null };
}

/** One scan's worth of quality: the average, and the spread behind it. */
export interface QualityPoint {
  scan_id: number;
  captured_at: string | null;
  agents: number;
  avg_score: number;
  min_score: number;
  max_score: number;
}

export interface Mover {
  bot_id: string;
  agent_name: string;
  from_score: number;
  to_score: number;
  delta: number;
  direction: "up" | "down";
  from_grade: string;
  to_grade: string;
  captured_at: string | null;
}

export interface QualityTimeline {
  points: QualityPoint[];
  from_at: string | null;
  to_at: string | null;
  movers: Mover[];
}

export interface TimelineFilters {
  environments: { id: number; label: string }[];
  creators: { upn: string; label: string; department: string | null; agents: number }[];
  agents: { bot_id: string; label: string }[];
}

/** One row of the run log — a scan, or a directory sync. */
export interface RunLogRow {
  id: string;
  scan_id: number | null;
  kind: string;
  raw_kind: string;
  environment: string | null;
  state: string;
  raw_status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  agents_found: number | null;
  agents_scored: number | null;
  partial: boolean;
  score: number | null;
  grade: string | null;
  engine_version: string | null;
  error: string | null;
  wrote: Record<string, unknown>;
}

export interface CreatorDirectoryStatus {
  creators_on_agents: number;
  known: number;
  resolved: number;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_error: string | null;
}
