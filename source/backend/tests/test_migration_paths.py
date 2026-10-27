"""Cross-platform migration path identity, including repeated Windows separators."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,'/ops')
from import_existing import canonical_asset


def test_repeated_windows_separator_and_case_variants():
    files={'screenshots/job.png':{'source':r'C:\Source\backend\automation_screenshots\job.png'}}
    expected='/var/data/screenshots/job.png'
    for value in [r'automation_screenshots\job.png',r'automation_screenshots\\job.png',
                  'automation_screenshots/job.png',r'c:\SOURCE\backend\automation_screenshots\job.png',
                  r'C:\Source\automation\agents\..\..\backend\automation_screenshots\job.png',expected]:
        assert canonical_asset(value,files)==expected


@pytest.mark.parametrize('reference',['job.png',r'..\automation_screenshots\job.png',r'automation_screenshots\missing.png','/var/data/screenshots/missing.png'])
def test_missing_or_unscoped_asset_is_not_substituted(reference):
    with pytest.raises(ValueError):canonical_asset(reference,{'screenshots/job.png':{'source':r'C:\Source\automation_screenshots\job.png'}})


def test_ambiguous_suffix_fails_closed():
    files={'screenshots/a.png':{'source':r'C:\A\screenshots\job.png'},'screenshots/b.png':{'source':r'C:\B\screenshots\job.png'}}
    with pytest.raises(ValueError):canonical_asset(r'screenshots\job.png',files)
