/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef NIKON_Z62_ADC_INPUT_H
#define NIKON_Z62_ADC_INPUT_H

/* External analogue levels. A conversion already in progress retains the
 * sample latched by adc_write(); changes affect the next conversion only.
 * The existing channels[] migration/reset semantics remain unchanged. */
static void z62_adc_input_get(Object *obj, Visitor *v, const char *name,
                              void *opaque, Error **errp)
{
    unsigned channel = GPOINTER_TO_UINT(opaque);
    uint16_t value = Z72_CONTROLLER_ADC(obj)->channels[channel];
    visit_type_uint16(v, name, &value, errp);
}

static void z62_adc_input_set(Object *obj, Visitor *v, const char *name,
                              void *opaque, Error **errp)
{
    unsigned channel = GPOINTER_TO_UINT(opaque);
    uint16_t value;
    if (!visit_type_uint16(v, name, &value, errp)) {
        return;
    }
    if (value > 4095) {
        error_setg(errp, "External ADC input requires a 12-bit sample");
        return;
    }
    Z72_CONTROLLER_ADC(obj)->channels[channel] = value;
}

static void z62_adc_input_properties(ObjectClass *klass)
{
    for (unsigned channel = 0; channel < 19; channel++) {
        g_autofree char *name = g_strdup_printf("input-channel%u", channel);
        object_class_property_add(klass, name, "uint16", z62_adc_input_get,
                                  z62_adc_input_set, NULL, GUINT_TO_POINTER(channel));
    }
}
#endif
