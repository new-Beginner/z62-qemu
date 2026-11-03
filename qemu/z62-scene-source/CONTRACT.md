# External scene input r23a

Implementation level **C**. This is a host-facing experiment, not recovered Nikon sensor protocol. Default is off. Frozen parent is r21; the failed r23 build and successful r23a build are separate directories.

## Fixed envelope

All integers are little-endian. The packet is exactly **2,285,720 bytes**: an 88-byte header followed by 2,285,632 bytes of experimental RGGB packed12 input.

| Offset | Type | Meaning |
|---:|---|---|
| 0 | 4 bytes | `Z62S` |
| 4 | u32 | Version 1 |
| 8 | u64 | External clock epoch |
| 16 | u64 | Positive publication sequence, at most INT64_MAX; strictly greater than the active sequence |
| 24 | u64 | `floor(time_ns * 30 / 1e9)` frame number |
| 32 | u64 | Virtual acquisition nanoseconds, at most INT64_MAX |
| 40/44/48/52 | four u32 | Width1514 / height1006 / stride2272 / payload bytes2285632 |
| 56 | 32 bytes | Payload SHA256 |
| 88 | payload | Packed pixels, including zero row padding |

For samples a,b, packing is `a[7:0]`, `a[11:8] | b[3:0]<<4`, `b[11:4]`. There are757 pairs and one zero padding byte per row. This is the inherited experimental packing, not a claim of CSI-2 or Nikon silicon equivalence. Black64, white4095 and the RGGB/sRGB mapping follow the existing approximate preview model, not factory calibration. These are ordinary scene pixels, **not internal PDAF statistics**.

## Publication and consumption

Enable with `nikon-z72-input-config.scene-source=on` together with Z62 functional RAW. `scene-packet` accepts a canonical base64 envelope. `scene-initial-file` optionally preloads an ordinary ASCII-staged packet before guest execution. Runtime bulk base64 proved too slow for continuous operation on the current Windows monitor; use the [r24 file transport](../z62-scene-file/CONTRACT.md).

The entire packet, geometry, sequence, SHA and padding are validated before active pixels/tags change. Bad packets preserve the prior source. Publication never emits RAW completion and never writes guest software readiness/error state.

The old RAW submit gate and all four destination preflights still apply. When enabled without a valid source, submit rejects as `scene-missing`, with no slot writes or completion. Each valid batch copies one source frame into all four slots. Only after all writes succeed are `scene-used-*` tags and use counters updated, immediately before the inherited completion signal. A rejected descriptor cannot acknowledge a source frame.

Read-only QOM diagnostics include `scene-valid`, `scene-publications`, current epoch/publish-id/frame-id/time-ns, used equivalents, uses and repeat-uses. Reusing an unchanged frame is counted explicitly; a RAW batch count is not a count of distinct input frames.

## Reset and snapshots

Device reset preserves the external frame and publication identity, clears consumption counters and used tags, and leaves descriptor reset behavior intact. New VM processes get fresh state. The optional external-scene VMState subsection stores pixels, digest, tags and counters and validates restored data. **Whole-VM plus Python-model snapshot/restore has not been accepted**; defining this subsection is not that acceptance.

## Evidence

Native r23a checks（本地证据，未分发：`../../analysis/z62-camera-r23/native-scene-ascii-final/report.json`） cover all four byte-for-byte slot readbacks, ten rejected packets, no acknowledgement on failed DMA, repeated input, read-only diagnostics, reset, initial preload and the disabled legacy pattern. CPUs remained stopped and no firmware was loaded for those device tests. Actual firmware flow is separately verified by the r24 host.
