/* SPDX-License-Identifier: GPL-2.0-or-later
 * Fixed-size external scene mailbox. All setters and RAW DMA run under BQL.
 * Publishing changes only external pixels/tags. Completion remains owned by
 * raw_submit after all four preflighted writes actually succeed.
 */
#include "qemu/bswap.h"
#include <glib/gstdio.h>

static uint64_t scene_frame_number(uint64_t ns)
{
    return (ns / 1000000000) * 30 + (ns % 1000000000) * 30 / 1000000000;
}

static void scene_digest(const uint8_t *pixels, uint8_t digest[32])
{
    GChecksum *checksum = g_checksum_new(G_CHECKSUM_SHA256);
    gsize length = 32;
    g_checksum_update(checksum, pixels, Z62_SCENE_BYTES);
    g_checksum_get_digest(checksum, digest, &length);
    g_checksum_free(checksum);
}

static bool scene_accept(Z72InputConfig *s, const uint8_t *data,
                         size_t length, Error **errp)
{
    Z62SceneSource *p = &s->scene;
    uint8_t digest[32];
    if (!p->enabled) {
        error_setg(errp, "Z62 scene source is disabled");
        return false;
    }
    if (length != Z62_SCENE_HEADER + Z62_SCENE_BYTES ||
        memcmp(data, "Z62S", 4) || ldl_le_p(data + 4) != 1 ||
        ldl_le_p(data + 40) != Z62_SCENE_WIDTH ||
        ldl_le_p(data + 44) != Z62_SCENE_HEIGHT ||
        ldl_le_p(data + 48) != Z62_SCENE_STRIDE ||
        ldl_le_p(data + 52) != Z62_SCENE_BYTES) {
        error_setg(errp, "Invalid fixed-size Z62 scene header");
        return false;
    }
    uint64_t id = ldq_le_p(data + 16), ns = ldq_le_p(data + 32);
    if (!id || id > INT64_MAX || (p->valid && id <= p->publish_id) ||
        ns > INT64_MAX || ldq_le_p(data + 24) != scene_frame_number(ns)) {
        error_setg(errp, "Invalid or stale Z62 scene sequence/frame/time");
        return false;
    }
    const uint8_t *pixels = data + Z62_SCENE_HEADER;
    scene_digest(pixels, digest);
    if (memcmp(digest, data + 56, 32)) {
        error_setg(errp, "Z62 scene payload checksum mismatch");
        return false;
    }
    for (unsigned y = 0; y < Z62_SCENE_HEIGHT; y++) {
        if (pixels[(y + 1) * Z62_SCENE_STRIDE - 1]) {
            error_setg(errp, "Z62 scene row padding must be zero");
            return false;
        }
    }
    /* Everything above was read-only. Publish pixels and all tags atomically. */
    memcpy(p->pixels, pixels, Z62_SCENE_BYTES);
    memcpy(p->digest, digest, 32);
    p->epoch = ldq_le_p(data + 8);
    p->publish_id = id;
    p->frame_id = ldq_le_p(data + 24);
    p->time_ns = ns;
    p->publications++;
    p->valid = true;
    return true;
}

static void scene_packet_set(Object *obj, const char *value, Error **errp)
{
    size_t bytes = Z62_SCENE_HEADER + Z62_SCENE_BYTES;
    size_t encoded = ((bytes + 2) / 3) * 4;
    if (strlen(value) != encoded) {
        error_setg(errp, "Z62 scene base64 size differs from bounded packet");
        return;
    }
    gsize length;
    g_autofree uint8_t *data = g_base64_decode(value, &length);
    g_autofree char *canonical = g_base64_encode(data, length);
    if (length != bytes || strcmp(canonical, value)) {
        error_setg(errp, "Z62 scene requires canonical base64");
        return;
    }
    scene_accept(Z72_INPUT_CONFIG(obj), data, length, errp);
}

static bool scene_realize(Z72InputConfig *s, Error **errp)
{
    Z62SceneSource *p = &s->scene;
    if (!p->enabled) {
        if (p->initial_file) {
            error_setg(errp, "Initial scene file requires scene-source=on");
            return false;
        }
        return true;
    }
    if (!s->z62_layout || !s->functional_raw) {
        error_setg(errp, "Scene source requires Z62 functional RAW");
        return false;
    }
    if (p->initial_file) {
        GStatBuf info;
        g_autofree char *data = NULL;
        GError *error = NULL;
        gsize length;
        if (g_stat(p->initial_file, &info) || !S_ISREG(info.st_mode) ||
            info.st_size != Z62_SCENE_HEADER + Z62_SCENE_BYTES) {
            error_setg(errp, "Initial Z62 scene must be a bounded ordinary file");
            return false;
        }
        if (!g_file_get_contents(p->initial_file, &data, &length, &error)) {
            error_setg(errp, "Cannot read initial Z62 scene: %s", error->message);
            g_error_free(error);
            return false;
        }
        if (!scene_accept(s, (uint8_t *)data, length, errp)) {
            return false;
        }
    }
    return true;
}

static void scene_used(Z72InputConfig *s)
{
    Z62SceneSource *p = &s->scene;
    if (!p->enabled) { return; }
    if (p->uses && p->used_publish_id == p->publish_id) { p->repeats++; }
    p->used_epoch = p->epoch;
    p->used_publish_id = p->publish_id;
    p->used_frame_id = p->frame_id;
    p->used_time_ns = p->time_ns;
    p->uses++;
}

static void scene_reset(Z72InputConfig *s)
{
    /* External illumination/frame input survives a device reset, like GPIO. */
    s->scene.used_epoch = s->scene.used_publish_id = 0;
    s->scene.used_frame_id = s->scene.used_time_ns = 0;
    s->scene.uses = s->scene.repeats = 0;
}

static bool scene_valid_get(Object *obj, Error **errp)
{
    return Z72_INPUT_CONFIG(obj)->scene.valid;
}

static void scene_qom_init(Object *obj)
{
    Z62SceneSource *p = &Z72_INPUT_CONFIG(obj)->scene;
    object_property_add_str(obj, "scene-packet", NULL, scene_packet_set);
    object_property_add_bool(obj, "scene-valid", scene_valid_get, NULL);
    object_property_add_uint64_ptr(obj, "scene-publications", &p->publications, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "scene-epoch", &p->epoch, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "scene-publish-id", &p->publish_id, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "scene-frame-id", &p->frame_id, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "scene-time-ns", &p->time_ns, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "scene-used-epoch", &p->used_epoch, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "scene-used-publish-id", &p->used_publish_id, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "scene-used-frame-id", &p->used_frame_id, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "scene-used-time-ns", &p->used_time_ns, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "scene-uses", &p->uses, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "scene-repeat-uses", &p->repeats, OBJ_PROP_FLAG_READ);
}

static bool scene_vmstate_needed(void *opaque)
{
    return Z72_INPUT_CONFIG(opaque)->scene.enabled;
}

static int scene_state_post_load(void *opaque, int version)
{
    Z62SceneSource *p = opaque;
    uint8_t digest[32];
    if (!p->valid) { return p->publish_id || p->uses ? -EINVAL : 0; }
    scene_digest(p->pixels, digest);
    if (!p->publish_id || p->publish_id > INT64_MAX || p->time_ns > INT64_MAX ||
        p->frame_id != scene_frame_number(p->time_ns) ||
        p->used_publish_id > p->publish_id || memcmp(digest, p->digest, 32)) {
        return -EINVAL;
    }
    for (unsigned y = 0; y < Z62_SCENE_HEIGHT; y++) {
        if (p->pixels[(y + 1) * Z62_SCENE_STRIDE - 1]) { return -EINVAL; }
    }
    return 0;
}

static const VMStateDescription scene_state_vmstate = {
    .name = "z62-external-scene-state",
    .version_id = 1,
    .minimum_version_id = 1,
    .post_load = scene_state_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_BOOL(valid, Z62SceneSource),
        VMSTATE_UINT8_ARRAY(pixels, Z62SceneSource, Z62_SCENE_BYTES),
        VMSTATE_UINT8_ARRAY(digest, Z62SceneSource, 32),
        VMSTATE_UINT64(epoch, Z62SceneSource),
        VMSTATE_UINT64(publish_id, Z62SceneSource),
        VMSTATE_UINT64(frame_id, Z62SceneSource),
        VMSTATE_UINT64(time_ns, Z62SceneSource),
        VMSTATE_UINT64(publications, Z62SceneSource),
        VMSTATE_UINT64(used_epoch, Z62SceneSource),
        VMSTATE_UINT64(used_publish_id, Z62SceneSource),
        VMSTATE_UINT64(used_frame_id, Z62SceneSource),
        VMSTATE_UINT64(used_time_ns, Z62SceneSource),
        VMSTATE_UINT64(uses, Z62SceneSource),
        VMSTATE_UINT64(repeats, Z62SceneSource),
        VMSTATE_END_OF_LIST()
    }
};

static const VMStateDescription scene_vmstate = {
    .name = TYPE_Z72_INPUT_CONFIG "/external-scene",
    .version_id = 1,
    .minimum_version_id = 1,
    .needed = scene_vmstate_needed,
    .fields = (const VMStateField[]) {
        VMSTATE_STRUCT(scene, Z72InputConfig, 1, scene_state_vmstate, Z62SceneSource),
        VMSTATE_END_OF_LIST()
    }
};
