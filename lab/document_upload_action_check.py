"""Upload discoverability regression. Local mode uses UI fixtures; live mode uses
only existing disposable beta accounts from a protected manifest, without uploads.
"""
import json
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

base = sys.argv[1].rstrip('/')
assert base in {'http://127.0.0.1:5213', 'https://grantflow-modern-staging.onrender.com'}
live = base.startswith('https:')
manifest = json.loads(Path(sys.argv[2]).read_text()) if live else None
if manifest:
    assert manifest['prefix'].startswith('beta_verify_')

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, channel=os.getenv('GFM_TEST_BROWSER_CHANNEL') or None)
    for role in ('grant_writer', 'viewer'):
        context = browser.new_context()
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        if live:
            account = manifest['accounts'][role]
            assert account['username'].startswith(manifest['prefix'] + '_')
            page.goto(base + '/auth/login')
            page.get_by_label('Username', exact=True).fill(account['username'])
            page.get_by_label('Password', exact=True).fill(account['password'])
            page.get_by_role('button', name='Sign in', exact=True).click()
            page.get_by_role('heading', name='Mission Control Dashboard').wait_for(timeout=30000)
        else:
            context.add_init_script("localStorage.setItem('gfm_session_hint', '1')")
            def fixture(route):
                path = route.request.url.split('/api/', 1)[-1].split('?')[0]
                data = []
                if path == 'auth/me':
                    data = {'id': 1, 'username': 'synthetic', 'role': role}
                elif path == 'ingestion/sources':
                    data = {'sources': [], 'notice': 'Synthetic fixture'}
                elif path == 'ingestion/monitor':
                    data = {'counts': {}, 'oldest_pending_seconds': 0, 'stale_documents': 0,
                            'coordinator_status': 'idle', 'local_extraction_enabled': True,
                            'alerts': [], 'workers': [], 'failures': [], 'freshness_items': []}
                route.fulfill(status=200, json=data)
            page.route('**/api/**', fixture)
        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 900})
            page.goto(base + '/gfm-app/documents')
            page.wait_for_load_state('networkidle')
            action = page.get_by_role('button', name='Upload document', exact=True)
            if role == 'viewer':
                assert action.count() == 0
                assert page.locator('input[type=file]').count() == 0
                page.get_by_text('Your viewer role can read documents.', exact=False).wait_for()
            else:
                assert action.is_visible()
                assert action.locator('svg').count() == 1
                bounds = action.bounding_box()
                assert 56 <= bounds['y'] < 500 if width == 390 else 0 <= bounds['y'] < 300
                action.click()
                assert page.locator('input[type=file]').evaluate('(el) => el === document.activeElement')
                page.locator('input[type=file]').set_input_files({
                    'name': 'QA TEST - DO NOT SUBMIT.txt', 'mimeType': 'text/plain',
                    'buffer': b'Synthetic upload action regression. Not submitted.'})
                assert page.get_by_role('button', name='Upload and process', exact=True).is_enabled()
                assert page.locator('#document-upload').evaluate(
                    '(el) => el.querySelector("h2") === document.querySelector("h2")')
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth + 2')
            assert not errors, errors
            print(json.dumps({'mode': 'live' if live else 'UI fixture', 'role': role,
                              'width': width, 'upload_visibility_and_action': 'PASS'}))
        context.close()
    browser.close()
