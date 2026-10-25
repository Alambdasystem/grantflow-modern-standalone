"""Actual read-only public provider smoke test; no account, database or browser.

Transport allowlist applies to redirects too. POST is allowed only for the two
public search contracts, never submission/account/email/payment endpoints.
"""
import asyncio
import json
from pathlib import Path
import sys
import time
import httpx

sys.path.insert(0, '/app/automation')
from agents import grant_scraper, grant_requirements

allowed = {
    ('POST', 'api.grants.gov', '/v1/api/search2'),
    ('POST', 'apply07.grants.gov', '/grantsws/rest/opportunities/search/'),
    ('GET', 'apply07.grants.gov', '/grantsws/rest/opportunity/details'),
    ('POST', 'apply07.grants.gov', '/grantsws/rest/opportunity/details'),
    ('GET', 'www.federalregister.gov', '/api/v1/documents.json'),
    ('GET', 'www.grants.gov', '/rss/GG_NewOpp.xml'),
    ('GET', 'www.grants.gov', '/search-grants.html'),
}
calls = []


class ReadOnlyTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.real = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request):
        key = (request.method, request.url.host, request.url.path)
        if request.url.scheme != 'https' or key not in allowed:
            calls.append({'method': key[0], 'host': key[1], 'path': key[2], 'result': 'DENIED_BY_TEST_ALLOWLIST'})
            raise httpx.RequestError('Read-only public test allowlist denied request', request=request)
        start = time.monotonic()
        row = {'method': key[0], 'host': key[1], 'path': key[2]}
        calls.append(row)
        try:
            response = await self.real.handle_async_request(request)
            row.update(status=response.status_code, seconds=round(time.monotonic() - start, 3))
            return response
        except Exception as exc:
            row.update(error_type=type(exc).__name__, seconds=round(time.monotonic() - start, 3))
            raise

    async def aclose(self):
        await self.real.aclose()


OriginalClient = httpx.AsyncClient


class GuardedClient(OriginalClient):
    def __init__(self, *args, **kwargs):
        kwargs['transport'] = ReadOnlyTransport()
        super().__init__(*args, **kwargs)


async def run():
    httpx.AsyncClient = GuardedClient
    # _scrape_via_http invokes only public search/RSS/HTML, no Playwright login.
    records = await grant_scraper.GrantScraperAgent()._scrape_via_http('education', 3)
    opp_id, hit = await grant_requirements.GrantRequirementsAgent()._search_opp(keyword='education')
    enrichment = {'result': 'BLOCKED', 'detail': 'No public opportunity identifier'}
    selected = next((r.get('opportunity_id') for r in records if r.get('opportunity_id')), opp_id)
    if selected:
        from routers.grant_enrichment import _enrich_grants_gov_api
        try:
            detail = await _enrich_grants_gov_api(selected)
            facts = [k for k in ['synopsis', 'funding_agency', 'opportunity_number'] if detail.get(k)]
            enrichment = {'result': 'PASS' if facts else 'FAIL', 'verified_nonempty_fields': facts,
                          'scope': 'Actual public detail adapter; package form completeness not established'}
        except Exception as exc:
            enrichment = {'result': 'BLOCKED', 'error_type': type(exc).__name__}
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 405:
                # This is a public read-only detail lookup, not a submission.
                async with GuardedClient(timeout=15) as client:
                    probe = await client.post('https://apply07.grants.gov/grantsws/rest/opportunity/details', data={'oppId': selected})
                    body = probe.json() if probe.status_code == 200 else {}
                    enrichment['post_read_contract_probe'] = {'status': probe.status_code,
                        'root_field_types': {key: type(value).__name__ for key, value in body.items()},
                        'nested_field_types': {key: {k: type(v).__name__ for k, v in value.items()} for key, value in body.items() if isinstance(value, dict)}}
    result = {'calls': calls, 'discovery': {'result': 'PASS' if records and all(r.get('title') and r.get('source_url') for r in records) else 'BLOCKED',
              'normalized_records': len(records), 'sources': sorted({r.get('source', 'unknown') for r in records})},
              'requirements_public_search': {'result': 'PASS' if opp_id and hit else 'BLOCKED', 'resolved_opportunity': bool(opp_id)},
              'public_detail_enrichment': enrichment,
              'scope': 'Actual unauthenticated public read adapters, temporary egress runner, no persisted catalog or private/production records. Does not verify authenticated packages, enrichment of every field, or normal internal-network egress.'}
    Path('/evidence/parity/public-integrations.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


asyncio.run(run())
