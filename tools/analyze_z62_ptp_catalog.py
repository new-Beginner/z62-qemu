"""Pinned, bounded offline PTP catalog. No transport, emulation or firmware writes.

Only explicitly referenced tables are parsed; integer hits are never capabilities.
Run with python -B tools/analyze_z62_ptp_catalog.py.
"""
import hashlib
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x10020000
FIRMWARE = ROOT / 'artifacts/z62-reference-1.70/master.bin'
DEVICE_INFO = ROOT / 'analysis/camera-usb/device-info-rw-20261028-162139.json'
OUTPUT = ROOT / 'analysis/z62-ptp-catalog'
FIRMWARE_SHA256 = 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4'
DEVICE_SHA256 = '88f4618b7c2b1a07c7542de724c488f7d3aa733df6d02dbdbafd855af05c0f83'
# Independent table bases recovered from the literal pools of actual consumers.
TABLES = (
    ('standard', 0x119F1D90, 19, 0x1047B8F4),
    ('vendor', 0x119F1FC0, 70, 0x1047B8F8),
    ('vendor_95xx', 0x119F2D88, 12, 0x1047B904),
    ('anchor_private', 0x119F496C, 175, 0x104C9608),
)
ANCHORS = (
    (0xC051, 0x10779167, 0x10779227),
    (0xC052, 0x10779259, 0x10779319),
    (0xC101, 0x10779363, 0x10779423),
    (0xC102, 0x10779455, 0x10779519),
)
# Half-open, manually grounded code windows; selector's inline TBB data excluded.
WINDOWS = (
    ('operation_lookup', 0x104666A4, 0x1046679C),
    ('operation_pre_dispatch', 0x104667C2, 0x104668BC),
    ('operation_handler_dispatch', 0x104668BC, 0x104668D0),
    ('table_initializers_partial', 0x1047B6F6, 0x1047B7E8),
    ('table_selector_head', 0x1047B7E8, 0x1047B7F4),
    ('table_selector_cases_and_dispatch', 0x1047B7FE, 0x1047B8DE),
    ('private_table_accessors', 0x104C9580, 0x104C95F2),
    ('private_handler_dispatch', 0x104C96F4, 0x104C970A),
    ('private_lookup', 0x104C981C, 0x104C983A),
    ('get_device_info_pre', 0x10466D02, 0x10466D2A),
    ('get_device_info_handler_prefix_only', 0x10466D2A, 0x10466D6C),
    ('property_trampolines', 0x10504350, 0x10504358),
    ('property_init_pre_and_handler', 0x10504358, 0x10504432),
)
NAMES = {0x1001: 'GetDeviceInfo', 0x1002: 'OpenSession', 0x1003: 'CloseSession',
         0x1004: 'GetStorageIDs', 0x1005: 'GetStorageInfo', 0x1006: 'GetNumObjects',
         0x1007: 'GetObjectHandles', 0x1008: 'GetObjectInfo', 0x1009: 'GetObject',
         0x100A: 'GetThumb', 0x100B: 'DeleteObject', 0x100C: 'SendObjectInfo',
         0x100D: 'SendObject', 0x100E: 'InitiateCapture', 0x100F: 'FormatStore',
         0x1014: 'GetDevicePropDesc', 0x1015: 'GetDevicePropValue',
         0x1016: 'SetDevicePropValue', 0x101B: 'GetPartialObject'}


def hx(value):
    return f'0x{value:08X}'


def code(value):
    return f'0x{value:04X}'


def pinned_read(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f'Input SHA256 mismatch: {path.name}')
    return data


def words(data, address, count=1):
    offset = address - BASE
    if offset < 0 or offset + count * 4 > len(data):
        raise ValueError('Address outside pinned image')
    return struct.unpack_from('<' + 'I' * count, data, offset)


def capabilities(document):
    result = {}
    for namespace, key in (('operations', 'operations_supported'),
                           ('events', 'events_supported'),
                           ('properties', 'device_properties_supported')):
        values = [int(x, 16) for x in document['device_info'][key]]
        if len(set(values)) != len(values) or any(not 0 <= x <= 0xFFFF for x in values):
            raise ValueError('Invalid capability list: ' + namespace)
        result[namespace] = [code(x) for x in values]
    return result


def parse_table(data, name, start, count, literal):
    if words(data, literal)[0] != start:
        raise ValueError('Table literal changed: ' + name)
    rows = []
    for index in range(count):
        address = start + 28 * index
        row = words(data, address, 7)
        if not 0 < row[0] <= 0xFFFF or row[1] not in (0, 1):
            raise ValueError('Invalid operation record')
        # +8 is context, often RAM, NOT a code pointer or required zero.
        for pointer in row[3:]:
            if pointer and (not pointer & 1 or not BASE <= (pointer & ~1) < BASE + len(data)):
                raise ValueError('Invalid Thumb callback')
        rows.append({'record_address': hx(address), 'operation': code(row[0]),
                     'name': NAMES.get(row[0]), 'raw_words': [hx(x) for x in row],
                     'flag_04': row[1], 'context_08': hx(row[2]),
                     'callback_0c': hx(row[3]), 'precondition_10': hx(row[4]),
                     'handler_14': hx(row[5]), 'initializer_18': hx(row[6]),
                     'handler_code_address': hx(row[5] & ~1) if row[5] else None})
    end = start + count * 28
    if words(data, end, 7) != (0,) * 7:
        raise ValueError('Missing full zero sentinel: ' + name)
    if len({r['operation'] for r in rows}) != count:
        raise ValueError('Duplicate operation within table')
    return {'id': name, 'base': hx(start), 'sentinel': hx(end), 'stride': 28,
            'record_count': count, 'base_literal': hx(literal), 'records': rows}


def disassembly(data):
    cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    cs.detail = True
    windows, edges, literals, indirect = [], [], [], []
    for name, start, end in WINDOWS:
        instructions = []
        cursor = start
        for ins in cs.disasm(data[start - BASE:end - BASE], start):
            cursor = ins.address + ins.size
            item = {'address': hx(ins.address), 'bytes': ins.bytes.hex(),
                    'mnemonic': ins.mnemonic, 'operands': ins.op_str}
            instructions.append(item)
            if ins.mnemonic in ('bl', 'blx', 'b.w') and ins.operands[0].type == ARM_OP_IMM:
                edges.append({'site': hx(ins.address), 'target': hx(ins.operands[0].imm),
                              'kind': ins.mnemonic, 'window': name})
            elif ins.mnemonic in ('bx', 'blx') and ins.op_str != 'lr':
                indirect.append({'site': hx(ins.address), 'register': ins.op_str,
                                 'window': name, 'runtime_target_verified': False})
            if ins.mnemonic.startswith('ldr') and len(ins.operands) > 1:
                operand = ins.operands[1]
                if operand.type == ARM_OP_MEM and operand.mem.base == ARM_REG_PC:
                    pool = ((ins.address + 4) & ~3) + operand.mem.disp
                    literals.append({'site': hx(ins.address), 'pool': hx(pool),
                                     'value': hx(words(data, pool)[0]), 'window': name})
        if cursor != end:
            raise ValueError('Incomplete bounded disassembly: ' + name)
        windows.append({'name': name, 'start': hx(start), 'end_exclusive': hx(end),
                        'instructions': instructions})
    return {'windows': windows, 'direct_edges_in_windows': edges,
            'pc_relative_literals': literals, 'indirect_call_sites': indirect}


def analyze(data, document):
    caps = capabilities(document)
    tables = [parse_table(data, *spec) for spec in TABLES]
    for index, (operation, pre, handler) in enumerate(ANCHORS):
        if words(data, 0x119F5C20 + index * 28, 7)[:6] != (operation, 0, 0, 0, pre, handler):
            raise ValueError('Known four-record anchor changed')
    mapping = []
    for operation in caps['operations']:
        matches = [{'table': table['id'], **row} for table in tables
                   for row in table['records'] if row['operation'] == operation]
        mapping.append({'operation': operation, 'matches': matches,
                        'status': 'static_table_match' if matches else 'unresolved'})
    xrefs = disassembly(data)
    return {'schema_version': 1, 'inputs': {
                'firmware': str(FIRMWARE.relative_to(ROOT)).replace('\\', '/'),
                'firmware_sha256': hashlib.sha256(data).hexdigest(),
                'firmware_size': len(data), 'base': hx(BASE),
                'device_info': str(DEVICE_INFO.relative_to(ROOT)).replace('\\', '/'),
                'device_info_sha256': DEVICE_SHA256},
            'scope': {'offline_only': True, 'camera_accessed': False, 'firmware_executed': False,
                      'hardware_validation': False, 'safety_certified': False,
                      'all_firmware_tables_exhausted': False},
            'capabilities': caps, 'tables': tables, 'advertised_operation_mapping': mapping,
            'counts': {'operations': len(caps['operations']), 'events': len(caps['events']),
                       'properties': len(caps['properties']), 'tables': len(tables),
                       'records': sum(t['record_count'] for t in tables),
                       'matched_advertised_operations': sum(bool(x['matches']) for x in mapping)},
            'namespace_collisions': [
                {'code': x, 'event_advertised': True, 'operation_advertised': x in caps['operations'],
                 'private_operation_record': row['record_address']}
                for table in tables for row in table['records']
                if (x := row['operation']) in caps['events']],
            'read_candidates': [
                {'operation': '0x1001', 'name': 'GetDeviceInfo', 'pre': hx(0x10466D02),
                 'handler': hx(0x10466D2A), 'boundary':
                 '仅核验处理函数前缀；0x10466D50/56 向 r4 所指上下文写入，调用多个未深入函数；不是纯函数或持久状态无写入证明。'},
                {'operation': '0x1014', 'name': 'GetDevicePropDesc', 'pre': hx(0x1050436E),
                 'handler': hx(0x105043BE), 'callback_trampoline': hx(0x10504354),
                 'callback_target_static': hx(0x104CAD78), 'boundary':
                 '初始化将 ROM 回调写入 RAM context；处理函数在 0x105043E0 写入属性选择值，0x105043E8 blx r5。静态初始化候选，不保证运行时 RAM 未被改写；未深入属性后端。'},
                {'operation': '0x1015', 'name': 'GetDevicePropValue', 'pre': hx(0x10504396),
                 'handler': hx(0x105043BE), 'callback_trampoline': hx(0x10504350),
                 'callback_target_static': hx(0x104CAD92), 'boundary':
                 '与 0x1014 共用处理函数但 context 不同；响应发送/缓存/锁/持久状态副作用未完整分析，不能由 Get 名称推断安全。'}],
            'xref_evidence': xrefs,
            'other_layout_candidate': {'address': hx(0x119EAE00), 'words':
                [hx(x) for x in words(data, 0x119EAE00, 9)],
                'interpretation': '疑似 code+两指针的 12 字节表；未恢复消费者，不计入已证实分发表。'},
            'limitations': ['没有执行任何固件函数或 opcode；本次无实机验证。',
                '分发表静态存在不等于当前会话可达/已授权/无副作用。',
                '只分析四张有消费者交叉引用的表及列出的代码窗口；未穷举其他表或全部调用者。',
                '事件/属性仅依据固定历史 DeviceInfo 清单，不宣称恢复了其固件分发表。',
                '+4 的精确方向语义及 +0x0C 回调完整语义未确认；保留原值。',
                '历史 WPD DeviceInfo 不证明所有厂商能力均被公布，未公布项不是可执行建议。']}


def render_report(result):
    lines = ['# Z6II C1.70 PTP 离线能力清单与分发证据', '',
             '## 范围与结果',
             '- 固定完整 master SHA256：`' + FIRMWARE_SHA256 + '`。',
             '- 固定历史 DeviceInfo SHA256：`' + DEVICE_SHA256 + '`。',
             '- 97 操作、27 事件、21 属性分离保存；97/97 操作各有唯一静态表记录。',
             '- 四张表共 276 条非零记录，不包含四个全零终止记录；不等于 276 项可用能力。',
             '- 本次无 USB/WPD/相机访问、固件执行、RAW 解锁、密钥保存、固件修改或实机验证。', '',
             '## 已恢复表（地址均为 BASE 0x10020000 下的固件地址）',
             '|表|起点|全零终止记录|条数|表基址 literal|', '|---|---|---|---:|---|']
    for t in result['tables']:
        lines.append(f"|{t['id']}|{t['base']}|{t['sentinel']}|{t['record_count']}|{t['base_literal']}|")
    lines += ['', '三张公布操作表匹配数分别为 17、68、12；前两表另有未公布的 100C/100D、942B/944B。',
              'anchor_private 的 175 项均不在公布操作列表。C101/C102 同时是历史列表中的事件代码；不得合并命名空间。', '',
              '## 可复核分发交叉引用',
              '- `0x104666A4` 操作查找函数按类别调用 `0x1047B7E8` 表选择器，再调用 `0x1047B822`；例如 BL 位于 `0x104666BE/C4`、`0x10466768/6E`。',
              '- 选择器 `0x1047B7FE` / `0x1047B802` / `0x1047B814` 的 LDR 分别加载三张公布操作表的 literal。',
              '- `0x1047B822` 以 LDRH 比较操作码、`0x1047B82E` 加 `0x1C`，零码结束；这是步长证据，不是按相同整数猜表。',
              '- `0x104667C2` 前置分发在 `0x104668A4` 调用 `0x1047B868`；后者 `0x1047B876` 加载记录 +0x10、`0x1047B87E` BLX r2。',
              '- `0x104668BC` 查找后在 `0x104668CC` B.W 到 `0x1047B8D6`；该函数取 +8 context、+0x14 handler，在 `0x1047B8DC` BX r3。',
              '- 私有表：`0x104C981C` → `0x104C95A4` 返回基址 → `0x104C95A8` 按 0x1C 查找；调用点 `0x104C982C/32`。',
              '- 私有处理入口 `0x104C96F4` → `0x104C981C`，`0x104C9706` B.W `0x104C95EA`，最终 `0x104C95F0` BX r3；+0x10 前置调用在 `0x104C95E0`。',
              '- `0x104C9580` 遍历 +0x18 并 BLX，支持其初始化回调角色；普通表亦有同模式初始化遍历。',
              '- `<7I>` 字段：操作、未完全命名标志、context（可为 RAM）、+0x0C 回调、前置回调、处理回调、初始化回调。代码指针保留 Thumb 位，另存清位地址。',
              '- 四个锚点记录 `0x119F5C20/3C/58/74` 的前六字段逐字核验；C101/C102 handler 为 `0x10779422` / `0x10779518`，未执行。', '',
              '## 少量读取候选（并非安全白名单）']
    for item in result['read_candidates']:
        lines.append(f"- {item['operation']} {item['name']}: pre `{item['pre']}`，handler `{item['handler']}`。{item['boundary']}")
    lines += ['', '属性回调初始化静态指向 `0x10504354 → 0x104CAD78`（描述）、`0x10504350 → 0x104CAD92`（值）。实际运行经 RAM 间接 BLX，目标及后端副作用未实机确认。', '',
              '## 未决点与下一步',
              '- `0x119EAE00` 还有疑似 12 字节布局（9520 后接两指针），未确认消费者，不按 28 字节套用，不计入结果。',
              '- 其他选择器表、间接调用运行时目标、权限/会话条件、属性后端及持久写入边界仍未知。',
              '- 下一步仅离线展开 `0x104CAD78/92` 与 DeviceInfo 完整处理函数，识别写入/缓存/同步边界；不建议发送未核验操作。',
              '- 完整逐操作映射、原始七字段、指令字节、literal 引用、直接分支与未确认间接调用见 `evidence.json`。', '',
              '## 复现', '```', 'python -B tools/analyze_z62_ptp_catalog.py',
              'python -B -m unittest discover -s tests -p test_z62_ptp_catalog.py -v', '```', '']
    return '\n'.join(lines)


def main():
    data = pinned_read(FIRMWARE, FIRMWARE_SHA256)
    document = json.loads(pinned_read(DEVICE_INFO, DEVICE_SHA256))
    result = analyze(data, document)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (OUTPUT / 'report.md').write_text(render_report(result), encoding='utf-8')
    print(json.dumps(result['counts'], ensure_ascii=False))


if __name__ == '__main__':
    main()
