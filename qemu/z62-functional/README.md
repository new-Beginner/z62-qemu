# Z62 functional RAW — 2026.10.28-r4

This is an **explicit, default-off experiment**, not a recovered sensor/ISP model.
It does not patch firmware, application indices, diagnostic RAM, code, or error lists.
It writes only the known physical processing pool, via the submitting engine's
own root MemoryRegion/AddressSpace. Z72 has no raw-submit connection.

Enable only on the independent build:

```
-global nikon-z72-input-config.functional-raw=on
```

QOM `/machine/master-input` and `/machine/slave-input` expose read-only
`raw-accepted`, `raw-rejected`, `raw-bytes`, `raw-last-reason`. Accepted counts
successful four-slot submissions, bytes counts all four slots. A disabled submit
counts as rejected. Reset clears counters, reason and descriptors.

## Bounded contract

- Only the existing explicit write `20068104=1` triggers an attempt. A separate
  `raw-submit` boot-config output preserves the original `sensor-submit` wire.
  No timer or unconditional periodic DMA exists.
- Existing input control `20069514` must equal **6**; width `20069518=05EA0000`
  and height `2006951C=03EE0000` must match exactly, including both zero low halves.
  Channel 2 stride `20069A08` must equal **2272**.
- `20069A3C bit0` selects bank 0 (`20069A50..5C`) or bank 1 (`20069A60..6C`).
  This bank interpretation is functional/inferred, not established hardware fact.
  Invalid selected banks never fall back.
- All four addresses must be nonzero, four-byte aligned, pairwise disjoint and
  wholly within `[82C00000, 8AEBC400)`. All must resolve to writable RAM with
  sufficient contiguous backing before any write. Readonly aliases and MMIO are
  rejected. DMA uses address_space_write, not global physical-memory helpers.
- Each slot receives 1514 x 1006 pixels, stride 2272, **2,285,632 bytes**.
  Pixel `(x,y) = (3*x + 5*y + 0x100) & 0xfff`; pairs `(a,b)` serialize as
  `a&255`, `(a>>8)|((b&15)<<4)`, `b>>4`. The final row byte is zero.
  This **experimental packed12** ordering is NOT verified silicon bit order.
- All four writes must succeed before counters advance and `raw-complete` pulses.
  That new output is deliberately not connected to sensor completion / IRQ92.
  No `functional-raw-completion` option is implemented in this revision.

The existing input-config VMState stays v2; enabled Z62 adds a named
`nikon-z72-input-config/functional-raw` v1 subsection for counters/reason/edge.
Use the same functional-raw setting on migration peers. Default-off diagnostics
are intentionally not in the subsection; Z72/default-off base layout is unchanged.
Migration wire compatibility is defined here but live migration is not tested.

## Provenance

Pinned donor `third_party/z62-qemu@4f4389944fc339d107f22f5f7ca3f90cc34b78de`,
then unchanged `tools/reference_updates.py` r1, then hash-guarded
`tools/z62_functional_device.py` replacements on generated source only.
The original input-config stores registers only (donor lines 165–178);
known processing RAM is in `nikon-z62-profile.h:25`. Z6's separate RAW flow
(`third_party/z6-qemu/qemu/nikon-z6.c:1384–1426`) informed preflight/slot handling,
not Z62 register addresses or packing. The slave profile has no such pool.

## Build and checks

```
python -B tools/build_z62_functional.py --jobs 12
python -B tools/probe_z62_functional_raw.py --qemu .build/z62-functional-2026.10.28-r4/runtime/qemu-system-arm.exe --output analysis/z62-functional-device/qtest.json
python -B -m unittest discover -s tests -p test_z62_functional_raw.py -v
```

Native Windows Python + cached QEMU 10.2.4 + UCRT64 are required. Default toolchain
path comes from the old r1 manifest. Workspaces are exclusively claimed and never
resumed/overwritten by the builder. The old launcher is untouched and cannot
implicitly select this EXE. `reference-build-manifest.json` retains r1 identity
for stage(updates=True) compatibility but explicitly adds `functional_device`;
it must NOT be described as an unmodified r1 binary. A separate
`functional-build-manifest.json` identifies adapter/header/generated source and
binary SHA256. Tests use `-S` plus native qtest sockets, not `-accel qtest` and
never load firmware or execute guest CPUs. Register writes in this harness are
not evidence of original firmware reaching or consuming the RAW input.

The dual-engine isolation test uses GDB thread 3 (paused CPU2) only to configure
and read back slave MMIO descriptors: qtest has no CPU selector and addresses
first_cpu only. It then uses qtest raw-submit GPIO injection and verifies the
slave rejects its unmapped processing pool while the master remains untouched.
No CPU/PC/register-state patch or guest execution is used. A first harness
attempt using command-line generic-loader was rejected by the test because the
board reset cleared those MMIO writes; this was a harness issue, not DMA failure.
