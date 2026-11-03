/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef NIKON_Z62_CAPTUREWORK_API_H
#define NIKON_Z62_CAPTUREWORK_API_H
/* Internal serialized device interface, not new guest MMIO. */
void z62_capturework_control(DeviceState *dev, hwaddr address, uint32_t value);
#endif
