"""Catalog identity and source checks; never rewrite historical ownership."""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qsl, urlencode


def normalized(text):
    return ' '.join(re.findall(r'\w+', (text or '').casefold()))


def source_key(url):
    parts = urlsplit(url or '')
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith('utm_') and k.lower() not in {'fbclid', 'gclid'}]
    return (parts.hostname or '').lower(), parts.path.rstrip('/'), urlencode(sorted(query))


def opportunity_id(url):
    parts = urlsplit(url or '')
    if not (parts.hostname or '').lower().endswith('.grants.gov') and parts.hostname != 'grants.gov':
        return None
    for key, value in parse_qsl(parts.query):
        if key.casefold() == 'oppid' and value.isdigit():
            return value
    match = re.search(r'/(?:search-)?results-detail/(\d+)', parts.path)
    return match.group(1) if match else None


def requirement_error(grant):
    detail = grant.requirements_detail or {}
    if not detail:
        return None
    expected_id = opportunity_id(grant.source_url)
    # Keyword search alone cannot establish a relationship to a local funder.
    if not expected_id or str(detail.get('opp_id') or '') != expected_id:
        return 'Requirements withheld: the saved package is not verified against this opportunity source. Open the funder source and request a verified package.'
    if detail.get('application_url') and opportunity_id(detail['application_url']) != expected_id:
        return 'Requirements withheld: the package application link refers to a different opportunity.'
    return None


def safe_requirements(grant):
    return {} if requirement_error(grant) else (grant.requirements_detail or {})


def catalog_state(grant):
    if grant.deadline:
        deadline = grant.deadline.replace(tzinfo=timezone.utc) if grant.deadline.tzinfo is None else grant.deadline
        if deadline < datetime.now(timezone.utc):
            return 'expired'
    path = urlsplit(grant.source_url or '').path.lower()
    if any(term in path for term in ('awardees', 'awards-announced', 'grant-recipients')):
        return 'historical_announcement'
    return 'deadline_unconfirmed' if not grant.deadline else 'current'


def deduplicate(grants):
    """Collapse exact opportunity identities in listings; keep every stored ID."""
    seen = set()
    result = []
    for grant in grants:
        key = (normalized(grant.title), normalized(grant.funding_agency), source_key(grant.source_url))
        # No source or agency means we cannot prove identity across records.
        if grant.source_url and grant.funding_agency:
            if key in seen:
                continue
            seen.add(key)
        result.append(grant)
    return result
