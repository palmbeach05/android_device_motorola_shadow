/*
   Copyright (c) 2013, The Linux Foundation. All rights reserved.

   Redistribution and use in source and binary forms, with or without
   modification, are permitted provided that the following conditions are
   met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above
      copyright notice, this list of conditions and the following
      disclaimer in the documentation and/or other materials provided
      with the distribution.
    * Neither the name of The Linux Foundation nor the names of its
      contributors may be used to endorse or promote products derived
      from this software without specific prior written permission.

   THIS SOFTWARE IS PROVIDED "AS IS" AND ANY EXPRESS OR IMPLIED
   WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
   MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT
   ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS
   BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
   CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
   SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
   BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
   WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
   OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
   IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#include <stdlib.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <private/android_filesystem_config.h>

#include "vendor_init.h"
#include "property_service.h"
#include "log.h"
#include "util.h"
#include <sys/system_properties.h>

#include <sys/resource.h>

void property_override(char const prop[], char const value[])
{
	prop_info *pi;

	pi = (prop_info*) __system_property_find(prop);
	if (pi)
		__system_property_update(pi, value, strlen(value));
	else
		__system_property_add(prop, strlen(prop), value, strlen(value));
}

void vendor_load_properties()
{
	char incremental[PROP_VALUE_MAX];
	char description[255];
	char fingerprint[255];
    
	property_get("ro.build.version.incremental", incremental);
    
	property_set("ro.product.model", "DROIDX");
	property_set("ro.product.brand", "Verizon");
	property_set("ro.product.device", "shadow");
	property_set("ro.product.name", "shadow_cdma");
	property_set("ro.product.manufacturer", "Motorola");
	property_set("ro.hardware", "mapphone_cdma");
	property_set("ro.board.platform", "omap3");

	/* Build Metadata & Modern Fingerprint */
	snprintf(description, sizeof(description), 
             "cdma_shadow-user 4.4.4 KTU84Q %s release-keys", incremental);
	snprintf(fingerprint, sizeof(fingerprint), 
             "Verizon/shadow_vzw/cdma_shadow:4.4.4/KTU84Q/%s:user/release-keys", incremental);

	property_override("ro.build.description", description);
	property_override("ro.build.fingerprint", fingerprint);
	property_override("ro.build.version.base_os", "4.4.4");

	/* Camera and Media Hardware */
	property_set("ro.media.capture.maxres", "8m");
	property_set("ro.media.capture.flash", "led");
	property_set("ro.media.capture.torchIntensity", "50");
	property_set("ro.media.capture.classification", "classE");
	property_set("ro.media.capture.flip", "horizontalandvertical");
	property_set("ro.media.dec.jpeg.memcap", "20000000");

	property_set("ro.opengles.version", "131072");
	property_set("windowsmgr.max_events_per_sec", "200");
	property_set("ro.mot.dpmext", "true");
	property_set("ro.mot.setuptype", "2");
	property_set("ro.kernel.android.ril", "yes");
}
