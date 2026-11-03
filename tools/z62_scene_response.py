"""Pixel evidence for the explicit C-level scene -> RAW -> NV12 -> factory LCD.

This is a separate observation, not a replacement for r49 mode recovery.
"""
import math

from PIL import Image, ImageStat

VERSION = '2026.11.03-scene-response-r54'


def measure(gray, raw_expected, raw_patches, nv12_patches, image):
    if type(gray) is not int or not 0 <= gray <= 255 or len(raw_expected) != 48:
        raise ValueError('Require a gray challenge and its 48-byte RAW reference')
    if not isinstance(image, Image.Image) or image.width < 128 or image.height < 128:
        raise ValueError('Require the actual LCD image')
    medians = []
    rgb = image.convert('RGB')
    for x, y in ((.25, .3), (.75, .3), (.25, .7), (.75, .7)):
        cx, cy = round(rgb.width*x), round(rgb.height*y)
        medians.append(ImageStat.Stat(rgb.crop((cx-24, cy-24, cx+24, cy+24))).median)
    # Independent BT.601 limited-range integer expectation for uniform gray.
    y = ((220*gray+128) >> 8)+16
    raw_matches = len(raw_patches) == 4 and all(p == raw_expected for p in raw_patches)
    nv12_matches = len(nv12_patches) == 12 and all(
        len(p['y']) == len(p['uv']) == 32 and
        all(abs(v-y) <= 1 for v in p['y']) and all(v == 128 for v in p['uv'])
        for p in nv12_patches)
    lcd_matches = all(max(abs(v-gray) for v in p) <= 20 and max(p)-min(p) <= 8 for p in medians)
    return {'raw_matches': raw_matches, 'nv12_matches': nv12_matches,
            'lcd_matches': lcd_matches, 'expected_y': y,
            'raw_patch_count': len(raw_patches), 'nv12_patch_count': len(nv12_patches),
            'lcd_patch_medians': medians,
            'lcd_tolerance': 20, 'lcd_chroma_tolerance': 8,
            'patches_are_full_frame_checks': False}


def assess(challenges, return_time):
    def finite(value):
        return type(value) in (int, float) and math.isfinite(value)

    passed, reasons = [], []
    for row in challenges:
        failures = []
        published, observed = row.get('published_virtual_seconds'), row.get('observed_virtual_seconds')
        if not (finite(return_time) and finite(published) and finite(observed) and
                published >= return_time+6 and observed >= published+2):
            failures.append('not-settled-after-return')
        source = row.get('source', {})
        for prop, field in (('scene-used-publish-id', 'publish_id'), ('scene-used-epoch', 'epoch'),
                            ('scene-used-frame-id', 'frame_id'), ('scene-used-time-ns', 'virtual_time_ns')):
            if type(row.get(field)) is not int or source.get(prop) != row[field]:
                failures.append(prop+'-mismatch')
        for field in ('raw_delta', 'preview_delta', 'source_uses_delta'):
            if type(row.get(field)) is not int or row[field] <= 0:
                failures.append(field+'-not-positive')
        if not (row.get('index') == 3 and row.get('display_enabled') is True and
                row.get('ready_join') == 3 and row.get('input_inhibit') == 0):
            failures.append('factory-readiness-unavailable')
        for field in ('raw_matches', 'nv12_matches', 'lcd_matches'):
            if row.get('measurement', {}).get(field) is not True:
                failures.append(field+'-unverified')
        passed.append(not failures)
        reasons.append({'publish_id': row.get('publish_id'), 'failures': failures})
    distinct = (len(challenges) == 2 and
                all(type(r.get('gray')) is int for r in challenges) and
                abs(challenges[0]['gray']-challenges[1]['gray']) >= 100 and
                type(challenges[0].get('publish_id')) is int and
                type(challenges[1].get('publish_id')) is int and
                challenges[1]['publish_id'] > challenges[0]['publish_id'] and
                finite(challenges[0].get('observed_virtual_seconds')) and
                finite(challenges[1].get('published_virtual_seconds')) and
                challenges[1]['published_virtual_seconds'] > challenges[0]['observed_virtual_seconds'])
    return {'new_scene_response_verified': bool(distinct and all(passed)),
            'two_distinct_ordered_challenges': distinct, 'challenges': reasons,
            'is_full_mode_recovery_assessment': False}
