import { expectArray, expectRecord, parseNumericValue } from "./parse-utils.js";

export interface EmailDecisionSummary {
  success: boolean;
  evaluated_at: string;
  sample_size: number;
  domains: Record<string, number>;
  intents: Record<string, number>;
  send_allowed: {
    YES: number;
    NO: number;
  };
  blocked_count: number;
  needs_review_count: number;
  automation_owner_count: number;
  manual_owner_count: number;
  domain_intent_mismatches_blocked: number;
  reply_all_attempts_blocked: number;
  unknown_domain_sends_blocked: number;
  transport_revalidation_blocks: number;
  manual_thread_automation_blocks: number;
  legacy_recruiting_false_positives_caught_by_new_gate: number;
  current_domain_gated_false_positive_recruiting: number;
  current_domain_gated_false_negative_recruiting: number;
  shadow_report: {
    candidate_counts: Record<string, number>;
    active_roles_with_documented_sponsorship_requirements: number;
    active_roles_unknown_auth_requirements: number;
    strong_technical_matches_needing_clarification: number;
    genuine_documented_placement_conflicts: number;
  };
}

export interface EmailDecisionWhy {
  domain_evidence: string[];
  message_origin: string;
  conversation_owner: string;
  transport_validation: string;
  block_reason: string;
}

export interface EmailDecisionProvenance {
  graph_message_id: string;
  conversation_id: string;
  internet_message_id: string;
  automation_ledger_match: string;
  previous_automation_message_id: string;
}

export interface EmailDecisionAttachment {
  count: number;
  files: string[];
}

export interface EmailDecisionTimelineItem {
  step: string;
  at: string;
}

export interface EmailDecisionRow {
  time: string;
  message_id: string;
  thread_id: string;
  sender: string;
  subject: string;
  domain: string;
  intent: string;
  owner: string;
  message_origin: string;
  automation_permission: string;
  reply_required: boolean | null;
  send_allowed: boolean | null;
  recipient_policy: string;
  transport_validation: string;
  final_action: string;
  block_reason: string;
  why: EmailDecisionWhy;
  provenance: EmailDecisionProvenance;
  thread_context: string;
  body_preview: string;
  classification: Record<string, unknown>;
  business_state: Record<string, unknown>;
  domain_confidence: string;
  domain_evidence_text: string;
  domain_alternatives: string[];
  transport: {
    validation: string;
    blocked: boolean;
    blocked_reason: string;
    would_call_graph: boolean;
  };
  timeline: EmailDecisionTimelineItem[];
  response_preview: string;
  attachments: EmailDecisionAttachment;
}

export interface EmailDecisionReplayControl {
  id: string | number;
  title: string;
  source: string;
  expected: {
    domain: string;
    intent: string;
    final_action: string;
  };
  actual: {
    domain: string;
    intent: string;
    classification_status: string;
    reply_required: boolean | null;
    send_allowed: boolean | null;
    final_action: string;
    reason: string;
  };
  pass: boolean;
  input: Record<string, unknown>;
}

export interface EmailDecisionControlsResponse {
  success: boolean;
  controls: EmailDecisionReplayControl[];
}

function parseStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item ?? "")).filter(Boolean);
}

function parseRecordCounts(value: unknown): Record<string, number> {
  const record = value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
  return Object.fromEntries(
    Object.entries(record).map(([key, item]) => [key, parseNumericValue(item)])
  );
}

function parseText(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

function parseBooleanMaybe(value: unknown): boolean | null {
  if (typeof value === "boolean") {
    return value;
  }
  return null;
}

function parseWhy(value: unknown): EmailDecisionWhy {
  const record = value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
  return {
    domain_evidence: parseStringList(record.domain_evidence),
    message_origin: parseText(record.message_origin),
    conversation_owner: parseText(record.conversation_owner),
    transport_validation: parseText(record.transport_validation),
    block_reason: parseText(record.block_reason),
  };
}

function parseProvenance(value: unknown): EmailDecisionProvenance {
  const record = expectRecord(value, "Email decision provenance payload was invalid.");
  return {
    graph_message_id: parseText(record.graph_message_id),
    conversation_id: parseText(record.conversation_id),
    internet_message_id: parseText(record.internet_message_id),
    automation_ledger_match: parseText(record.automation_ledger_match),
    previous_automation_message_id: parseText(record.previous_automation_message_id),
  };
}

function parseAttachment(value: unknown): EmailDecisionAttachment {
  const record = value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
  return {
    count: parseNumericValue(record.count),
    files: parseStringList(record.files),
  };
}

function parseTimeline(value: unknown): EmailDecisionTimelineItem[] {
  return expectArray(value, "Email decision timeline payload was invalid.")
    .map((item) => {
      const record = item && typeof item === "object" && !Array.isArray(item) ? (item as Record<string, unknown>) : {};
      return {
        step: parseText(record.step),
        at: parseText(record.at),
      };
    })
    .filter((item) => Boolean(item.step));
}

function parseRow(value: unknown): EmailDecisionRow {
  const record = expectRecord(value, "Email decision row payload was invalid.");
  const transport = record.transport && typeof record.transport === "object" && !Array.isArray(record.transport)
    ? (record.transport as Record<string, unknown>)
    : {};
  return {
    time: parseText(record.time),
    message_id: parseText(record.message_id),
    thread_id: parseText(record.thread_id),
    sender: parseText(record.sender),
    subject: parseText(record.subject),
    domain: parseText(record.domain),
    intent: parseText(record.intent),
    owner: parseText(record.owner),
    message_origin: parseText(record.message_origin),
    automation_permission: parseText(record.automation_permission),
    reply_required: parseBooleanMaybe(record.reply_required),
    send_allowed: parseBooleanMaybe(record.send_allowed),
    recipient_policy: parseText(record.recipient_policy),
    transport_validation: parseText(record.transport_validation),
    final_action: parseText(record.final_action),
    block_reason: parseText(record.block_reason),
    why: parseWhy(record.why),
    provenance: parseProvenance(record.provenance),
    thread_context: parseText(record.thread_context),
    body_preview: parseText(record.body_preview),
    classification: expectRecord(record.classification, "Email decision classification payload was invalid."),
    business_state: expectRecord(record.business_state, "Email decision business-state payload was invalid."),
    domain_confidence: parseText(record.domain_confidence),
    domain_evidence_text: parseText(record.domain_evidence_text),
    domain_alternatives: parseStringList(record.domain_alternatives),
    transport: {
      validation: parseText(transport.validation),
      blocked: Boolean(transport.blocked),
      blocked_reason: parseText(transport.blocked_reason),
      would_call_graph: Boolean(transport.would_call_graph),
    },
    timeline: parseTimeline(record.timeline),
    response_preview: parseText(record.response_preview),
    attachments: parseAttachment(record.attachments),
  };
}

function parseReplayControl(value: unknown): EmailDecisionReplayControl {
  const record = expectRecord(value, "Email decision control replay payload was invalid.");
  const expected = record.expected && typeof record.expected === "object" && !Array.isArray(record.expected)
    ? (record.expected as Record<string, unknown>)
    : {};
  const actual = record.actual && typeof record.actual === "object" && !Array.isArray(record.actual)
    ? (record.actual as Record<string, unknown>)
    : {};
  const input = record.input && typeof record.input === "object" && !Array.isArray(record.input)
    ? (record.input as Record<string, unknown>)
    : {};
  return {
    id: record.id as string | number,
    title: parseText(record.title),
    source: parseText(record.source),
    expected: {
      domain: parseText(expected.domain),
      intent: parseText(expected.intent),
      final_action: parseText(expected.final_action),
    },
    actual: {
      domain: parseText(actual.domain),
      intent: parseText(actual.intent),
      classification_status: parseText(actual.classification_status),
      reply_required: parseBooleanMaybe(actual.reply_required),
      send_allowed: parseBooleanMaybe(actual.send_allowed),
      final_action: parseText(actual.final_action),
      reason: parseText(actual.reason),
    },
    pass: Boolean(record.pass),
    input,
  };
}

export function parseEmailDecisionSummary(payload: unknown): EmailDecisionSummary {
  const record = expectRecord(
    payload,
    "Email decision summary API returned an invalid response."
  );
  const shadow = record.shadow_report && typeof record.shadow_report === "object" && !Array.isArray(record.shadow_report)
    ? (record.shadow_report as Record<string, unknown>)
    : {};
  const sendAllowed = record.send_allowed && typeof record.send_allowed === "object" && !Array.isArray(record.send_allowed)
    ? (record.send_allowed as Record<string, unknown>)
    : {};

  return {
    success: Boolean(record.success),
    evaluated_at: parseText(record.evaluated_at),
    sample_size: parseNumericValue(record.sample_size),
    domains: parseRecordCounts(record.domains),
    intents: parseRecordCounts(record.intents),
    send_allowed: {
      YES: parseNumericValue(sendAllowed.YES),
      NO: parseNumericValue(sendAllowed.NO),
    },
    blocked_count: parseNumericValue(record.blocked_count),
    needs_review_count: parseNumericValue(record.needs_review_count),
    automation_owner_count: parseNumericValue(record.automation_owner_count),
    manual_owner_count: parseNumericValue(record.manual_owner_count),
    domain_intent_mismatches_blocked: parseNumericValue(record.domain_intent_mismatches_blocked),
    reply_all_attempts_blocked: parseNumericValue(record.reply_all_attempts_blocked),
    unknown_domain_sends_blocked: parseNumericValue(record.unknown_domain_sends_blocked),
    transport_revalidation_blocks: parseNumericValue(record.transport_revalidation_blocks),
    manual_thread_automation_blocks: parseNumericValue(record.manual_thread_automation_blocks),
    legacy_recruiting_false_positives_caught_by_new_gate: parseNumericValue(record.legacy_recruiting_false_positives_caught_by_new_gate),
    current_domain_gated_false_positive_recruiting: parseNumericValue(record.current_domain_gated_false_positive_recruiting),
    current_domain_gated_false_negative_recruiting: parseNumericValue(record.current_domain_gated_false_negative_recruiting),
    shadow_report: {
      candidate_counts: parseRecordCounts(shadow.candidate_counts),
      active_roles_with_documented_sponsorship_requirements: parseNumericValue(shadow.active_roles_with_documented_sponsorship_requirements),
      active_roles_unknown_auth_requirements: parseNumericValue(shadow.active_roles_unknown_auth_requirements),
      strong_technical_matches_needing_clarification: parseNumericValue(shadow.strong_technical_matches_needing_clarification),
      genuine_documented_placement_conflicts: parseNumericValue(shadow.genuine_documented_placement_conflicts),
    },
  };
}

export function parseEmailDecisionRecent(payload: unknown): EmailDecisionRow[] {
  const record = expectRecord(payload, "Email decision recent API returned an invalid response.");
  const rows = expectArray(record.items, "Email decision recent API returned an invalid items list.");
  return rows.map((row) => parseRow(row));
}

export function parseEmailDecisionControls(payload: unknown): EmailDecisionControlsResponse {
  const record = expectRecord(payload, "Email decision control replay API returned an invalid response.");
  const rows = expectArray(record.controls, "Email decision control replay API returned an invalid controls list.");
  return {
    success: Boolean(record.success),
    controls: rows.map((row) => parseReplayControl(row)),
  };
}
