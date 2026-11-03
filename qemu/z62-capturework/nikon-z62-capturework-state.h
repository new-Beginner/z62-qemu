/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/timer.h"
#include "nikon-z62-main-source.h"
#include "nikon-z62-capturework-pixels.h"
#include "nikon-z62-raw-transfer.h"

typedef struct Z62CWProfile {
    uint32_t correction, geometry[5], packing[8], buffers[18];
    uint16_t lookup[256];
} Z62CWProfile;

typedef struct Z62CWTask {
    Z72InputConfig *owner;
    uint64_t generation;
    Z62MainLease lease;
    Z62CWProfile profile;
    Z62CaptureWorkPixelsConfig pixels;
    Z62RawTransfer transfer;
    uint32_t bank, slot, destination;
    uint8_t *input, *packed;
    size_t packed_bytes, row_bytes;
    bool submitted, ready, success;
} Z62CWTask;

typedef struct Z62CaptureWork {
    bool enabled, stopping, valid[3], known[0x4000/4];
    uint32_t held, allowed, running, cursor, reason, pending_front, pending_raw;
    uint64_t generation, last_publication, completed, rejected, cancelled, blocked, bytes;
    QEMUTimer *timer;
    Z62MainSource source;
    Z62CWProfile profile;
    Z62CWTask *task;
    qemu_irq complete[3];
    Error *migration_blocker;
    bool output_valid;
    Z62MainMetadata output_meta;
    Z62RawTransfer output_transfer;
    uint32_t output_address, output_width, output_height, output_stride, output_slot, output_bank;
} Z62CaptureWork;
