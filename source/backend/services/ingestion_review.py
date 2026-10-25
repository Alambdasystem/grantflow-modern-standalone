"""Review revisions and evidence freshness, independent of source polling."""
from datetime import date, timedelta
import hashlib
import json


def revision(item):
    return hashlib.sha256(json.dumps(item.extracted or {},sort_keys=True,ensure_ascii=True).encode()).hexdigest()


def freshness(item):
    from services.document_ingestion import now
    as_of=item.evidence_date or item.created_at.date()
    due=item.review_due or as_of+timedelta(days=30)
    return {'as_of':as_of.isoformat(),'review_due':due.isoformat(),'date_confirmed':bool(item.evidence_date),
            'stale':item.current and item.status!='deleted' and due<now().date(),
            'basis':'Reviewer-supplied evidence date' if item.evidence_date else 'Upload date; document period not confirmed'}
