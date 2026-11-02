"""r47b supports the two physically observed format values over frozen r47."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.11.02-r47b'
WORK = ROOT/'.build'/('z62-preview-results-format-'+VERSION)
NAME = 'nikon-z62-preview-results-profile.h'
INPUT_SHA = '91012ac870cd239f9f37c244a2b667a91316415c3a3f7766c3f66c6d6b2c246e'
HEADER = ROOT/'qemu/z62-preview-results-format'/NAME


def identity():
    return {'schema': 1, 'version': VERSION, 'input_profile_sha256': INPUT_SHA,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()),
            'header_sha256': reference.sha(HEADER.read_bytes()), 'default_enabled': False,
            'format_bit9_observed_units': [54, 55], 'software_metadata_used_for_success': False,
            'statistics_bank0_completed': False, 'guest_software_patched': False}


def apply_source(source):
    source = Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()):
        raise ValueError('Format extension requires its independent workspace')
    target = source/'hw/arm'/NAME
    if reference.sha(target.read_bytes()) != INPUT_SHA:
        raise ValueError('Format extension requires unchanged r47 profile')
    target.write_bytes(HEADER.read_bytes())
    return identity()
