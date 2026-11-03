/* SPDX-License-Identifier: GPL-2.0-or-later
 * Private, opt-in provenance of completed level-C ISP output. No guest writes,
 * IRQs, scheduling, acceptance conditions, or pixel arithmetic are changed.
 */
static void output_lineage_source(NikonZ72BootConfig *s, const uint64_t tags[4], unsigned kind)
{
    if (!s->z62_output_lineage) return;
    memcpy(s->lineage_source_tags,tags,sizeof(s->lineage_source_tags));
    s->lineage_source_seq=s->preview_source_seq;
    s->lineage_source_kind=kind;
    s->lineage_source_valid=tags[1]!=0;
}

static void output_lineage_raw_source(NikonZ72BootConfig *s)
{
    if (!s->z62_output_lineage) return;
    uint64_t tags[4]={0};
    if (s->paired_input) z62_paired_scene_last_used(s->paired_input,tags);
    output_lineage_source(s,tags,1);
}

static void output_lineage_video_drop(NikonZ72BootConfig *s)
{
    s->lineage_video_valid=false; s->lineage_video_seq=0; s->lineage_video_kind=0;
    memset(s->lineage_video_tags,0,sizeof(s->lineage_video_tags));
}

static void output_lineage_video_capture(NikonZ72BootConfig *s)
{
    if (!s->z62_output_lineage) return;
    s->lineage_video_seq=s->video_source_seq;
    s->lineage_video_kind=s->lineage_source_kind;
    s->lineage_video_valid=s->lineage_source_valid &&
        s->lineage_source_seq==s->video_source_seq;
    memcpy(s->lineage_video_tags,s->lineage_source_tags,sizeof(s->lineage_video_tags));
}

static void output_lineage_commit(NikonZ72BootConfig *s, unsigned mode, unsigned kind,
                                  uint64_t sequence, bool valid, const uint64_t tags[4])
{
    if (!s->z62_output_lineage) return;
    s->lineage_output_count++; s->lineage_output_seq=sequence;
    s->lineage_output_mode=mode; s->lineage_output_kind=kind;
    s->lineage_output_valid=valid;
    memset(s->lineage_output_tags,0,sizeof(s->lineage_output_tags));
    if (valid) memcpy(s->lineage_output_tags,tags,sizeof(s->lineage_output_tags));
}

static void output_lineage_commit_photo(NikonZ72BootConfig *s)
{
    if (!s->z62_output_lineage) return;
    /* Photo reads guest RAW directly. Another actual RAW DMA with different
     * scene tags invalidates attribution; it is never labelled as success. */
    uint64_t used[4]={0};
    bool valid=s->lineage_source_valid && s->lineage_source_seq==s->preview_source_seq &&
        s->paired_input && z62_paired_scene_last_used(s->paired_input,used) &&
        !memcmp(used,s->lineage_source_tags,sizeof(used));
    output_lineage_commit(s,1,s->lineage_source_kind,s->preview_source_seq,valid,s->lineage_source_tags);
}

static void output_lineage_commit_video(NikonZ72BootConfig *s)
{
    /* Video owns a private immutable cohort. Use the tags captured with that
     * cohort, even if the external scene mailbox has since been republished. */
    output_lineage_commit(s,2,s->lineage_video_kind,s->video_source_seq,
        s->lineage_video_valid && s->lineage_video_seq==s->video_source_seq,s->lineage_video_tags);
}

static void output_lineage_reset(NikonZ72BootConfig *s)
{
    s->lineage_source_valid=s->lineage_output_valid=false;
    s->lineage_source_seq=s->lineage_output_seq=s->lineage_output_count=0;
    s->lineage_source_kind=s->lineage_output_kind=s->lineage_output_mode=0;
    memset(s->lineage_source_tags,0,sizeof(s->lineage_source_tags));
    memset(s->lineage_output_tags,0,sizeof(s->lineage_output_tags));
    output_lineage_video_drop(s);
}

static bool output_lineage_tags_valid(const uint64_t tags[4])
{
    uint64_t ns=tags[3];
    return tags[1]>0 && tags[1]<=INT64_MAX && ns<=INT64_MAX &&
        tags[2]==(ns/1000000000)*30+(ns%1000000000)*30/1000000000;
}

static int output_lineage_post_load(NikonZ72BootConfig *s)
{
    if (s->lineage_source_kind>2 || s->lineage_video_kind>2 || s->lineage_output_kind>2 ||
        s->lineage_output_mode>2 || s->lineage_output_count>s->preview_batches ||
        s->lineage_source_seq>s->preview_source_seq || s->lineage_output_seq>s->preview_last_seq) return -EINVAL;
    if ((s->lineage_source_valid && (!s->z62_output_lineage || !s->lineage_source_seq ||
                                     !output_lineage_tags_valid(s->lineage_source_tags))) ||
        (s->lineage_video_valid && (!s->z62_output_lineage || !s->video_source_valid ||
                                   s->lineage_video_seq!=s->video_source_seq ||
                                   !output_lineage_tags_valid(s->lineage_video_tags))) ||
        (s->lineage_output_valid && (!s->z62_output_lineage || !s->lineage_output_seq ||
                                    !s->lineage_output_count || !s->lineage_output_mode ||
                                    !output_lineage_tags_valid(s->lineage_output_tags)))) return -EINVAL;
    return 0;
}

static char *output_lineage_get(Object *obj, Error **errp)
{
    NikonZ72BootConfig *s=NIKON_Z72_BOOT_CONFIG(obj);
    const char *mode=s->lineage_output_mode==1 ? "photo" : s->lineage_output_mode==2 ? "video" : "unknown";
    const char *source=s->lineage_output_kind==1 ? "legacy-raw-stream" :
        s->lineage_output_kind==2 ? "software-paired" : "unknown";
    return g_strdup_printf("{\"schema\":1,\"enabled\":%s,\"valid\":%s,\"commits\":%" PRIu64
        ",\"mode\":\"%s\",\"source\":\"%s\",\"sequence\":%" PRIu64
        ",\"epoch\":%" PRIu64 ",\"publish_id\":%" PRIu64 ",\"frame_id\":%" PRIu64 ",\"time_ns\":%" PRIu64
        ",\"scope\":\"device-input-to-software-isp-output\",\"pixel_identity_proven\":false}",
        s->z62_output_lineage ? "true":"false",s->lineage_output_valid ? "true":"false",
        s->lineage_output_count,mode,source,s->lineage_output_seq,s->lineage_output_tags[0],
        s->lineage_output_tags[1],s->lineage_output_tags[2],s->lineage_output_tags[3]);
}

static void output_lineage_init(Object *obj)
{
    object_property_add_str(obj,"paired-output-lineage",output_lineage_get,NULL);
}
