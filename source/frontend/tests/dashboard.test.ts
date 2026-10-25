import assert from "node:assert/strict";
import test from "node:test";
import {
  formatAwardedAmount,
  formatSuccessRate,
  parseDashboardStats,
} from "../lib/dashboard.ts";

test("dashboard stats parser hydrates every KPI card value from the API payload", () => {
  const stats = parseDashboardStats({
    total_grants: "31",
    active_grants: 29,
    total_applications: "24",
    submitted_applications: 4,
    approved_applications: "3",
    pending_renewals: "2",
    automation_jobs_running: 1,
    total_awarded: "125000",
    success_rate: "75.5",
  });

  assert.deepEqual(stats, {
    total_grants: 31,
    active_grants: 29,
    total_applications: 24,
    submitted_applications: 4,
    approved_applications: 3,
    pending_renewals: 2,
    automation_jobs_running: 1,
    total_awarded: 125000,
    success_rate: 75.5,
  });

  assert.equal(formatAwardedAmount(stats.total_awarded), "$125k");
  assert.equal(formatSuccessRate(stats.success_rate), "75.5%");
});

test("dashboard stats parser preserves missing success rate as N/A instead of a misleading zero", () => {
  const stats = parseDashboardStats({
    total_grants: 0,
    active_grants: 0,
    total_applications: 0,
    submitted_applications: 0,
    approved_applications: 0,
    pending_renewals: 0,
    automation_jobs_running: 0,
    total_awarded: 0,
    success_rate: null,
  });

  assert.equal(stats.success_rate, null);
  assert.equal(formatSuccessRate(stats.success_rate), "N/A");
});

test("dashboard stats parser rejects malformed API responses instead of leaving KPI cards loading forever", () => {
  assert.throws(
    () => parseDashboardStats(null),
    /Dashboard summary API returned an invalid response\./
  );
  assert.throws(
    () => parseDashboardStats([]),
    /Dashboard summary API returned an invalid response\./
  );
});
