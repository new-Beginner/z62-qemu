# r5 transaction-linked RAW completion contract

Version: `2026.10.28-r5`. This is a **transaction-linked functional hypothesis**,
not a silicon timing model, not evidence of the cause/fix of application state
0x35, and not a validated display/save pipeline. No firmware or hardware run is
part of this device acceptance test. Do not copy a Z72 diagram's IRQ94 number:
the existing Z62 status table maps offset 0x1508/mask 0x150c to sensor output3,
which the existing board connects to GIC IRQ92.

## Activation and wiring

On the new independent EXE only:

```
-global nikon-z72-input-config.functional-raw=on
-global nikon-z62-sensor-config.functional-raw-completion=on
```

Both settings default off. The board connects each engine's input-config
`raw-complete` output to that engine's sensor `raw-dma-complete` input. r4 emits
this pulse only after all four descriptor slots have passed preflight and all
four actual RAM writes succeed. r5 does not change r4 input-config or RAW data.
There is no clock/submit/config-write-generated transaction success, no event8
injection, no patch of guest state, return values, code or application errors.

On the new input's rising edge:

1. Increment `raw-source-events` (including disabled or ignored edges).
2. If functional-raw-completion is off: increment `raw-ignored`, reason disabled.
3. Require existing `sensor_mode2_configured`: `(20065400 & 0x11)==0x11` and
   `(20065504 & 0xc000)==0x8000`. Otherwise ignored/mode-mismatch.
4. Require `(2006550C & 2)!=0`: this is consumer armed for this transaction,
   NOT the distinct mode2 sync handshake GPIO arm. Otherwise ignored/unarmed-mask.
5. If `(20065508 & 2)!=0`, increment `raw-coalesced`, preserve pending IRQ level,
   and do not call the IRQ update to manufacture another edge.
6. Otherwise latch `20065508 bit1`, increment `raw-completions`, then call the
   existing `sensor_update_irqs`. W1C remains unchanged and lowers the IRQ when
   no other unmasked status remains. A subsequent DMA can raise it again.

Repeated high input is not another source event. An ignored edge is never
replayed by later arming/configuration. `source-events = completions + ignored +
coalesced` until uint64 wrap/reset. `completions` counts fresh status latches,
not every DMA and not necessarily every IRQ edge if another status already holds
the shared IRQ high.

The old initialization one-shot, mode handshakes, and frame-end code are retained.
Setting both functional-raw-completion and laboratory-frame-completion is a
realize error; r5 never silently enables a laboratory periodic source. Existing
init-completion remains independently configured; it is not removed or rearmed.

## Diagnostics and migration

`/machine/master-sensor` and `/machine/slave-sensor` expose read-only uint64:
`raw-source-events`, `raw-completions`, `raw-ignored`, `raw-coalesced`, plus
read-only string `raw-completion-last-reason`:
`reset`, `disabled`, `mode-mismatch`, `unarmed-mask`, `latched`, `coalesced`.
Invalid migrated reason values return `unknown`; missing QOM properties/errors
must not be converted to numeric zero by a host client.

Reset clears counters, reason, input edge and the original status/mask state.
Base sensor VMState v6 is unchanged; functional-raw-completion enabled uses
`nikon-z62-sensor-config/raw-transaction` subsection v1. Matching migration peer
settings are required. Loading an enabled subsection into a disabled/conflicting
peer is rejected. Default-off diagnostics are intentionally not migrated.
**Live migration has not been accepted/tested.** Z72 has no Z62 sensor device
and no new connection; its default behavior remains untouched.

## Build identity

The independent builder claims only `.build/z62-transaction-2026.10.28-r5` and
refuses existing workspaces. It applies unchanged donor preparation, r1 reference
updates, unchanged r4 functional adapter, then the r5 hash-guarded replace_once
adapter. r4 prepared hashes are checked against the existing r4 manifest before
r5 is applied. No r4 source, old runtime, donor, launcher or shared probe is edited.

All three manifests use schema 1 and refer to the **new r5 binary**:

- `reference-build-manifest.json`: old reference identity fields unchanged,
  plus `functional_device` (original r4 identity), `transaction_device` (r5
  identity), binary/DLL/source hashes and normal build/smoke metadata. This
  satisfies the unchanged verifier used by `stage(updates=True)`; it is not a
  pure-r1 or pure-r4 binary.
- `functional-build-manifest.json`: `version=2026.10.28-r4` identifies the base
  adapter; explicit `transaction_device` identifies the extension. The original
  r4 source identity remains unchanged in `functional_device`.
  `base_generated_functional_sha256` records hashes **before** r5;
  `generated_functional_sha256` records the final generated tree (board changed,
  input-config/header unchanged). No old manifest is rewritten.
- `transaction-build-manifest.json`: `version=2026.10.28-r5`, same base identities,
  plus `generated_transaction_sha256` for final board, sensor and new header.
  `transaction_device` itself includes schema/version, fixed input hashes,
  adapter/header hashes, original base_functional_device and hypothesis flags.

In the preserved r4 identity, `sensor_completion_source=false` describes the
r4 adapter alone. It must not be interpreted as the capability of the composite
r5 build: inspect `transaction_device` and the runtime opt-in property.

## Reproduction

```
python -B tools/build_z62_transaction.py --jobs 12
python -B tools/probe_z62_transaction.py --qemu .build/z62-transaction-2026.10.28-r5/runtime/qemu-system-arm.exe --output analysis/z62-transaction-device/qtest.json
python -B -m unittest discover -s tests -p test_z62_transaction.py -v
```

The device probe uses native `-S` and qtest TCP, not `-accel qtest`; CPUs never
execute firmware. It intercepts sensor `sysbus-irq` outputs: observed index3 is
the existing IRQ92 wire. Full four-slot pattern/guard readback accompanies real
DMA success tests. Explicit raw-dma-complete GPIO injection is isolated in a
labelled edge-deduplication unit test and is NOT counted as DMA validation.
Slave RAW descriptors use paused GDB CPU2 MMIO only because native qtest has no
CPU selector. The slave has no processing pool and must reject without any
sensor source event. The unchanged r4 probe checks run against r5 with a local
context-manager substitution solely to enforce QMP-quit cleanup. No shared
probe file is changed. Only owned child QEMUs are shut down, using QMP quit.
