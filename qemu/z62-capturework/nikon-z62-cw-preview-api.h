/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef NIKON_Z62_CW_PREVIEW_API_H
#define NIKON_Z62_CW_PREVIEW_API_H
#include "nikon-z62-main-source.h"
#include "nikon-z62-raw-transfer.h"
#define Z62_CW_COHORT_BYTES (2272u*1006u)
/* Internal BQL-owned view, valid only for the synchronous producer callback.
 * Packed linear12 is private; original guest LUT-coded RAW is untouched. */
typedef struct Z62CWCohortView {
    const uint8_t *linear[4];
    uint32_t address[4],bank;
    uint64_t generation,sequence;
    Z62MainMetadata meta[4];
    Z62RawTransfer transfer[4];
    char sha256[4][65];
} Z62CWCohortView;
typedef struct Z62CWPreviewCache {
    bool owns;
    uint8_t *linear[4];
    uint64_t accepted,blocked,rejected,stale,last_seen,sequence,generation;
    uint32_t bank,address[4];
    Z62MainMetadata meta[4];
    char sha256[4][65];
} Z62CWPreviewCache;
bool z62_capturework_preview_enabled(DeviceState *dev);
bool z62_capturework_cohort_view(DeviceState *dev,Z62CWCohortView *view);
#endif
