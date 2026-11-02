/* SPDX-License-Identifier: GPL-2.0-or-later
 * Fast C-level external-frame transport. Reuse the r23a bounded packet
 * validator; opening or loading a file never acknowledges successful DMA.
 */
static void scene_file_set(Object *obj, const char *value, Error **errp)
{
    Z72InputConfig *s = Z72_INPUT_CONFIG(obj);
    const size_t bytes = Z62_SCENE_HEADER + Z62_SCENE_BYTES;
    GStatBuf info;
    if (!s->scene.enabled) {
        error_setg(errp, "Z62 scene source is disabled");
        return;
    }
    if (strlen(value) > 4096 || !g_str_is_ascii(value) || !g_path_is_absolute(value) ||
        (value[0] == '\\' && value[1] == '\\') ||
        g_stat(value, &info) || !S_ISREG(info.st_mode) || info.st_size != bytes) {
        error_setg(errp, "Z62 scene file must be a bounded ordinary ASCII staging file");
        return;
    }
    FILE *file = g_fopen(value, "rb");
    if (!file) {
        error_setg_errno(errp, errno, "Cannot open Z62 scene file");
        return;
    }
    g_autofree uint8_t *data = g_malloc(bytes);
    bool complete = fread(data, 1, bytes, file) == bytes &&
                    fgetc(file) == EOF && !ferror(file);
    fclose(file);
    if (!complete) {
        error_setg(errp, "Z62 scene file changed or was not read completely");
        return;
    }
    scene_accept(s, data, bytes, errp);
}

static void scene_file_qom_init(Object *obj)
{
    object_property_add_str(obj, "scene-file", NULL, scene_file_set);
}
