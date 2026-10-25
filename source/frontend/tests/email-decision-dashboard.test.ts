import assert from "node:assert/strict";
import test from "node:test";
import {
  parseEmailDecisionControls,
  parseEmailDecisionRecent,
  parseEmailDecisionSummary,
} from "../lib/email-decision-dashboard.ts";

test("email decision dashboard parsers hydrate summary, recent rows, and control replays", () => {
  const summary = parseEmailDecisionSummary({
    success: true,
    evaluated_at: "2026-08-27T18:00:00+00:00",
    sample_size: "2",
    domains: { RECRUITING: "1", PROJECT_COLLABORATION: 1 },
    intents: { recruiter_job: "1", general_business: 1 },
    send_allowed: { YES: "1", NO: "1" },
    blocked_count: "1",
    needs_review_count: "0",
    automation_owner_count: "1",
    manual_owner_count: "1",
    domain_intent_mismatches_blocked: "1",
    reply_all_attempts_blocked: 0,
    unknown_domain_sends_blocked: "0",
    transport_revalidation_blocks: "1",
    manual_thread_automation_blocks: "0",
    legacy_recruiting_false_positives_caught_by_new_gate: "4",
    current_domain_gated_false_positive_recruiting: "1",
    current_domain_gated_false_negative_recruiting: "0",
    shadow_report: {
      candidate_counts: { known: "12", unknown: 8 },
      active_roles_with_documented_sponsorship_requirements: "2",
      active_roles_unknown_auth_requirements: "3",
      strong_technical_matches_needing_clarification: "1",
      genuine_documented_placement_conflicts: "0",
    },
  });

  assert.equal(summary.sample_size, 2);
  assert.equal(summary.domains.RECRUITING, 1);
  assert.equal(summary.intents.recruiter_job, 1);
  assert.equal(summary.send_allowed.YES, 1);
  assert.equal(summary.shadow_report.candidate_counts.known, 12);
  assert.equal(summary.shadow_report.active_roles_with_documented_sponsorship_requirements, 2);

  const rows = parseEmailDecisionRecent({
    success: true,
    items: [
      {
        time: "2026-08-27T15:00:00+00:00",
        message_id: "msg-1",
        thread_id: "msg-1",
        sender: "Recruiter <jobs@example.com>",
        subject: "Senior Engineer role",
        domain: "RECRUITING",
        intent: "recruiter_job",
        owner: "SHARED",
        message_origin: "LIVE_INBOUND",
        automation_permission: "auto_reply_allowed",
        reply_required: true,
        send_allowed: false,
        recipient_policy: "reply_sender_only",
        transport_validation: "BLOCKED",
        final_action: "BLOCKED",
        block_reason: "auto-send-blocked:recruiter_job",
        why: {
          domain_evidence: ["Recruiter asked for candidates."],
          message_origin: "LIVE_INBOUND",
          conversation_owner: "SHARED",
          transport_validation: "BLOCKED",
          block_reason: "auto-send-blocked:recruiter_job",
        },
        provenance: {
          graph_message_id: "graph-1",
          conversation_id: "thread-1",
          internet_message_id: "internet-1",
          automation_ledger_match: "run-99",
          previous_automation_message_id: "prev-88",
        },
        thread_context: "Prior thread context",
        body_preview: "Please send candidates.",
        classification: { primary_intent: "recruiter_job" },
        business_state: { business_domain: "recruiting" },
        domain_confidence: "high",
        domain_evidence_text: "Recruiter asked for candidates.",
        domain_alternatives: ["candidate_resume"],
        transport: { validation: "BLOCKED", blocked: true, blocked_reason: "auto-send-blocked:recruiter_job", would_call_graph: false },
        timeline: [{ step: "Received", at: "2026-08-27T15:00:00+00:00" }],
        response_preview: "NO RESPONSE",
        attachments: { count: 0, files: [] },
      },
    ],
  });

  assert.equal(rows[0].intent, "recruiter_job");
  assert.equal(rows[0].transport.blocked, true);
  assert.equal(rows[0].provenance.automation_ledger_match, "run-99");

  const controls = parseEmailDecisionControls({
    success: true,
    controls: [
      {
        id: "vernon_technical_cofounder",
        title: "Vernon/Ahsan technical co-founder",
        source: "live_replay",
        expected: { domain: "PROJECT_COLLABORATION", intent: "general_business", final_action: "NO_REPLY" },
        actual: { domain: "PROJECT_COLLABORATION", intent: "general_business", classification_status: "success", reply_required: false, send_allowed: false, final_action: "NO_REPLY", reason: "Project collaboration thread." },
        pass: true,
        input: {},
      },
    ],
  });

  assert.equal(controls.success, true);
  assert.equal(controls.controls[0].title, "Vernon/Ahsan technical co-founder");
  assert.equal(controls.controls[0].actual.final_action, "NO_REPLY");
});
