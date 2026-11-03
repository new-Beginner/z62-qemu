/* SPDX-License-Identifier: GPL-2.0-or-later
 * Include after the preserved preview-results profile. New layout is default-off
 * at the device boundary. This qualifies the captured680/698 unit49 recipe.
 * Projection below is a local template comparison, never a guest-memory write.
 */
#ifndef NIKON_Z62_PHOTO_RESULTS_PROFILE_H
#define NIKON_Z62_PHOTO_RESULTS_PROFILE_H
#include <string.h>

static inline uint32_t z62_photo_result_mask(unsigned index, uint32_t width,
                                             uint32_t height, const uint32_t *r,
                                             const uint8_t *parameters)
{
    if (index != 1 || width != 1024 || height != 680 || !r || !parameters ||
        z62_result_word(parameters,0x30) != (697u<<16)) {
        return 0;
    }
    uint8_t projected[160];
    memcpy(projected,parameters,sizeof(projected));
    /* All other opaque fields must match the preserved complete qualifier.
     * The actual renderer still receives680 active rows, not682 or700. */
    projected[0x30]=0;
    projected[0x31]=0;
    projected[0x32]=699 & 255;
    projected[0x33]=699 >> 8;
    return z62_preview_result_mask(1,1024,682,r,projected);
}
#endif
