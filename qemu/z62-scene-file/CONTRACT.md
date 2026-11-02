# Bounded scene-file transport r24

Implementation level **C**. This independent descendant of frozen r23a adds one write-only QOM property, `scene-file`. It reuses the entire [88-byte scene-envelope validator](../z62-scene-source/CONTRACT.md) and changes no RAW completion/IRQ rules or frame-state layout.

The setter requires an absolute ordinary ASCII staging filename and an exact bounded file size. It reads at most one packet plus an EOF check, then validates header, sequence, geometry, SHA and padding before publishing pixels. A file load is not DMA consumption. The native sender does not choose guest RAM addresses; those still come from the validated original RAW descriptor path.

The Python exchange creates a new private mailbox under its owned ASCII VM run directory, with immutable, exclusively created packet filenames. QMP carries only the short filename. Confirmed calls remove their own hash-matching file; uncertain calls retain the file until current publication ID readback confirms acceptance. Control commands are never replayed. Files changed outside the exchange are preserved and reported rather than silently removed.

The bootstrap file remains available in the private source directory. Runtime mailbox files do not accumulate after successful publication. The last16 RGB source frames and last acknowledged frame are retained in memory for C display/JPEG binding. Photographs live in the separately owned directory card, not in these transient frame files.

The exchange observes used IDs before and after reading the associated tags; an inconsistent observation is a gap. A C photo requires an owned consumed frame with the current settings revision and a nonfuture acquisition time no more than one virtual second old. That one-second ceiling is an explicit experiment guard, not Nikon shutter latency or a calibrated hardware limit.

## Measured result

On the current machine, a valid ~3MB base64 QOM packet took13.765 seconds with guest CPUs paused. File QOM operations in the native validation took0–0.015 seconds, measured by a clock with approximately15ms resolution; zero means below that resolution, not literally instantaneous.

[Native r24 checks](../../analysis/z62-camera-r24/native-file-final/report.json) repeat the full four-slot, rejection, default-off, reset and preload cases through file transport. Legacy RAW（本地证据，未分发：`../../analysis/z62-camera-r24/legacy-raw.json`） and 24 ADC cases（本地证据，未分发：`../../analysis/z62-camera-r24/legacy-adc.json`） were also run against this binary. Root firmware execution, GUI behavior and C JPEG decoding use separate evidence.

The native file reader is not a security boundary for an untrusted QMP controller. Production callers use only their owned ordinary staging directory; the public camera HTTP API does not accept arbitrary frame filenames.
