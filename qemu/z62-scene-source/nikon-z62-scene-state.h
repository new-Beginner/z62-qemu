/* SPDX-License-Identifier: GPL-2.0-or-later */
/* External level-C frame state. This is not recovered Nikon sensor protocol. */
#define Z62_SCENE_WIDTH 1514u
#define Z62_SCENE_HEIGHT 1006u
#define Z62_SCENE_STRIDE 2272u
#define Z62_SCENE_BYTES (Z62_SCENE_HEIGHT * Z62_SCENE_STRIDE)
#define Z62_SCENE_HEADER 88u

typedef struct Z62SceneSource {
    bool enabled, valid;
    char *initial_file;
    uint8_t pixels[Z62_SCENE_BYTES], digest[32];
    uint64_t epoch, publish_id, frame_id, time_ns, publications;
    uint64_t used_epoch, used_publish_id, used_frame_id, used_time_ns;
    uint64_t uses, repeats;
} Z62SceneSource;
