"""Read-only cloud folder adapters. Credentials stay in operator-owned files.

Never accept arbitrary endpoints, forward credentials to download redirects, or
interpret document content as commands. No provider permissions are requested here.
"""
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, quote
import httpx
from services.document_extract import MAX_BYTES, EXTENSIONS


class CloudSourceError(ValueError):
    pass


def checked_url(url, provider, download=False):
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    allowed = {'graph': {'graph.microsoft.com'}, 'google_drive': {'www.googleapis.com'}}
    valid = host in allowed.get(provider, set())
    if download:
        suffixes = ('.sharepoint.com', '.1drv.com') if provider == 'graph' else ('.googleusercontent.com',)
        valid = valid or any(host.endswith(s) for s in suffixes)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443) or not valid:
        raise CloudSourceError('Cloud response contained an untrusted URL; pickup stopped.')
    return url


def identifier(value):
    value = str(value or '')
    if not re.fullmatch(r'[A-Za-z0-9_!.:-]{1,250}', value):
        raise CloudSourceError('Configure a valid cloud drive and folder ID.')
    return quote(value, safe='')


async def token(client, cfg):
    try:
        credential = json.loads(Path(cfg['credential_file']).read_text(encoding='utf-8-sig'))
        if cfg['provider'] == 'sharepoint':
            tenant = identifier(credential['tenant_id'])
            endpoint = f'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token'
            data = {'grant_type': 'client_credentials', 'client_id': credential['app_id'],
                    'client_secret': credential['client_secret']['password'],
                    'scope': 'https://graph.microsoft.com/.default'}
        else:
            endpoint = 'https://oauth2.googleapis.com/token'
            data = {'grant_type': 'refresh_token', 'client_id': credential['client_id'],
                    'client_secret': credential['client_secret'], 'refresh_token': credential['refresh_token']}
        response = await client.post(endpoint, data=data)
        response.raise_for_status()
        return response.json()['access_token']
    except Exception:
        raise CloudSourceError('Cloud authorization unavailable. Check the configured credential file and existing read permissions.') from None


async def request(client, url, provider, bearer, *, params=None, binary=False):
    """Bounded GET; bearer only goes to the provider API, never signed redirects."""
    for redirect in range(4):
        checked_url(url, provider, download=binary)
        api_host = 'graph.microsoft.com' if provider == 'graph' else 'www.googleapis.com'
        headers = {'Authorization': f'Bearer {bearer}'} if urlsplit(url).hostname == api_host else {}
        for attempt in range(3):
            try:
                async with client.stream('GET', url, headers=headers, params=params) as response:
                    if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                        delay = response.headers.get('retry-after', '1')
                        await asyncio.sleep(min(5, max(0, int(delay))) if delay.isdigit() else 1)
                        continue
                    if response.status_code in (301, 302, 303, 307, 308) and binary:
                        url = response.headers.get('location', '')
                        params = None
                        break
                    if response.status_code in (401, 403):
                        raise CloudSourceError('Cloud read access denied. Restore authorized folder and document permissions.')
                    if response.status_code != 200:
                        raise CloudSourceError('Cloud provider unavailable or object missing; pickup will retry on its schedule.')
                    chunks, size = [], 0
                    limit = MAX_BYTES if binary else 2 * 1024 * 1024
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > limit:
                            raise CloudSourceError('Cloud response exceeds safe processing limits.')
                        chunks.append(chunk)
                    raw = b''.join(chunks)
                    return raw if binary else json.loads(raw)
            except (httpx.HTTPError, json.JSONDecodeError):
                raise CloudSourceError('Cloud provider request failed; pickup will retry on its schedule.') from None
        else:
            raise CloudSourceError('Cloud provider retry limit reached.')
    raise CloudSourceError('Cloud download redirect limit reached.')


async def documents(cfg, client=None):
    """Yield (stable object ID, display filename, bytes); max 1000 folder entries.

    Partial failures keep prior versions intact. Remote deletions are intentionally
    not inferred from a listing: permission changes can hide existing objects.
    """
    if client is None:
        async with httpx.AsyncClient(timeout=45, follow_redirects=False) as owned:
            async for entry in documents(cfg, owned):
                yield entry
        return
    bearer = await token(client, cfg)
    provider = 'graph' if cfg['provider'] == 'sharepoint' else 'google_drive'
    folder = identifier(cfg.get('folder_id'))
    if provider == 'graph':
        drive = identifier(cfg.get('drive_id'))
        base = f'https://graph.microsoft.com/v1.0/drives/{drive}'
        url, params = f'{base}/items/{folder}/children', {'$top': 100}
    else:
        url = 'https://www.googleapis.com/drive/v3/files'
        params = {'q': f"'{cfg['folder_id']}' in parents and trashed = false", 'pageSize': 100,
                  'fields': 'nextPageToken,files(id,name,mimeType,size,capabilities/canDownload)',
                  'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true'}
    count, seen_pages = 0, set()
    while url:
        marker = (url, str(params))
        if marker in seen_pages:
            raise CloudSourceError('Cloud pagination repeated; pickup stopped.')
        seen_pages.add(marker)
        page = await request(client, url, provider, bearer, params=params)
        entries = page.get('value' if provider == 'graph' else 'files', [])
        count += len(entries)
        if count > 1000 or len(seen_pages) > 20:
            raise CloudSourceError('Cloud folder exceeds pickup limits; split into smaller authorized folders.')
        for entry in entries:
            if provider == 'graph' and 'file' not in entry:
                continue
            name, object_id = entry['name'], identifier(entry['id'])
            download_params = None
            if provider == 'graph':
                download_url = f'{base}/items/{object_id}/content'
            else:
                if entry.get('capabilities', {}).get('canDownload') is False:
                    raise CloudSourceError('A cloud document disallows download. Check source permissions.')
                exports = {'application/vnd.google-apps.document': ('.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
                           'application/vnd.google-apps.spreadsheet': ('.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                export = exports.get(entry.get('mimeType'))
                download_url = f'https://www.googleapis.com/drive/v3/files/{object_id}'
                if export:
                    name += export[0]
                    download_url += '/export'
                    download_params = {'mimeType': export[1]}
                else:
                    download_params = {'alt': 'media', 'supportsAllDrives': 'true'}
            if Path(name).suffix.lower() not in EXTENSIONS:
                continue
            if int(entry.get('size', 0)) > MAX_BYTES:
                raise CloudSourceError('A cloud document exceeds the 20 MB limit.')
            raw = await request(client, download_url, provider, bearer, params=download_params, binary=True)
            yield entry['id'], name, raw
        if provider == 'graph':
            url, params = page.get('@odata.nextLink'), None
        elif page.get('nextPageToken'):
            params = {**params, 'pageToken': page['nextPageToken']}
        else:
            url = None
