/*

Renders the OLED as it moves, one frame per refresh, so anything animated on
it can be watched at its real speed on a desktop before it is flashed.

oled_preview answers "is the layout right". This answers "is the speed right",
which a contact sheet cannot: it drives the same OledPages the instrument runs,
on the same OLED_INTERVAL_MS clock main.cpp ticks it with, and writes one dump
per refresh. oled_view.py --html plays them back at that interval.

    make -f tools/Makefile oled_anim
    ./oled_anim /tmp/anim
    python3 tools/oled_view.py --html /tmp/anim.html /tmp/anim*.raw

The mode name on the perform page is the only thing that moves so far, so that
is what this sets up. Pass a name to try your own.

*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../OledScreen.h"
#include "../OledPages.h"

// main.cpp refreshes the display on this interval, so the frames are this far
// apart and the playback interval has to match
#define INTERVAL_MS 50.f

// A name half again as long as the line takes about ten and a half seconds to
// go round. Twelve seconds covers that and lands back inside the hold at the
// start, so the player's own loop does not jump.
#define FRAMES 240

static void dump(OledScreen &s, const char *prefix, int frame) {
    char path[512];
    // zero padded so a shell glob hands them back in order
    snprintf(path, sizeof(path), "%s%04d.raw", prefix, frame);
    FILE *f = fopen(path, "wb");
    if (!f) {
        fprintf(stderr, "could not write %s\n", path);
        exit(1);
    }
    fwrite(s.pix_buf, 1, 1024, f);
    fclose(f);
}

int main(int argc, char *argv[]) {
    const char *prefix = argc > 1 ? argv[1] : "anim";
    const char *mode = argc > 2 ? argv[2] : "S - Sound Jaws - Uniform Color";

    OledScreen screen;
    OledPages pages;

    OledState &st = pages.st;
    int knobs[5] = { 200, 640, 1023, 80, 500 };
    for (int i = 0; i < 5; i++) st.knobs[i] = knobs[i];
    st.vuL = 72;
    st.vuR = 45;
    st.gain = 25;
    st.flags = OLED_FLAG_PERSIST | OLED_FLAG_WIFI;
    st.modeIndex = 11;
    st.modeCount = 57;
    st.sceneIndex = 1;
    st.sceneCount = 8;
    st.wifiLevel = 3;

    pages.setPage(OLED_PAGE_PERFORM);
    pages.setText("mode", mode);
    pages.setText("scene", "scene-0002");

    for (int i = 0; i < FRAMES; i++) {
        // the same order main.cpp ticks it in, so the timing is the timing
        pages.tickNotify(INTERVAL_MS);
        pages.tickScroll(INTERVAL_MS);
        pages.render(screen);
        dump(screen, prefix, i);
    }

    printf("wrote %d frames of %s at %.0fms\n", FRAMES, prefix, INTERVAL_MS);
    printf("python3 tools/oled_view.py --html %s.html %s*.raw\n",
           prefix, prefix);
    return 0;
}
