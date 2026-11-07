-- Retire old separate price/data-quality/backlog alerts before the API serves
-- the new two-event policy. Preserve their source evidence and audit history.
UPDATE alerts SET status='resolved'
WHERE calculation_version <> 'detectors_v2' AND status <> 'resolved';
