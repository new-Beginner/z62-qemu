/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef NIKON_Z62_PAIRED_INGRESS_API_H
#define NIKON_Z62_PAIRED_INGRESS_API_H
/* Internal model API under BQL, not guest registers or Nikon protocol.
 * tags = epoch, publication, external frame, external virtual timestamp. */
#define Z62_PAIRED_SCENE_BYTES (1006u * 2272u)
bool z62_paired_scene_copy(DeviceState *dev, uint8_t *pixels, uint64_t tags[4]);
bool z62_paired_scene_used(DeviceState *dev, const uint64_t tags[4]);
#endif
