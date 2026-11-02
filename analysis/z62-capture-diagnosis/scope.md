# Z62 Error / MENU / capture diagnosis scope

- Target: original Z6II C1.70 master complete member, 38,750,138 bytes, SHA-256 bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4; mapped code base 0x10020000.
- Emulator: local 2026.10.27-r1 native reference, donor Z62 4f4389944fc339d107f22f5f7ca3f90cc34b78de. Synthetic parameter groups are explicit, not recovered calibration.
- Authorized local analysis only. No physical camera, flashing, patched ROM, forced guest return values, application-state writes or synthetic success messages. Normal key pins and debugger execution breakpoints/read-only observations are permitted. Debugger pauses can affect timing; distinguish observed paths from unobserved assumptions.
- E-imports equivalent: raw ARM/Thumb embedded firmware (file identifies master as data), no PE/ELF loader/import/export tables. Use original direct calls, literal pools, notification dispatch tables and known MMIO accesses as analysis anchors. Controller member independently identified as Cortex-M firmware. This is not evidence of absence of firmware functionality.
- Tools: native Python 3.12 and Capstone 5.0.7 verified. IDA skill start.ps1 returned ERR:IDADIR not set and IDA Pro not found; use Capstone + QEMU GDB/QMP instead. Skill sibling tool-index.md and field-journal/precedent-reverse.md absent locally. No dependency installation performed.
- Separate diagnostic console: localhost:8664. Existing user changes and pinned submodules preserved. Reports distinguish this run, prior local A/B, upstream claims and unknowns.
