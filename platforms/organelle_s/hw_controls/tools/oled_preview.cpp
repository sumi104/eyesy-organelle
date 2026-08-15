/*

Renders every OLED page to a raw 1024 byte frame buffer dump so the layout can
be checked on a desktop without flashing the Organelle.

    make -f tools/Makefile
    ./oled_preview /tmp/oled
    python3 tools/oled_view.py /tmp/oled*.raw -o /tmp/oled.png

*/

#include <stdio.h>
#include <string.h>

#include "../OledScreen.h"
#include "../OledPages.h"

static void dump(OledScreen &s, const char *prefix, int page) {
    char path[512];
    snprintf(path, sizeof(path), "%s%d.raw", prefix, page);
    FILE *f = fopen(path, "wb");
    if (!f) {
        fprintf(stderr, "could not write %s\n", path);
        return;
    }
    fwrite(s.pix_buf, 1, 1024, f);
    fclose(f);
    printf("wrote %s\n", path);
}

int main(int argc, char *argv[]) {
    const char *prefix = argc > 1 ? argv[1] : "oled";

    OledScreen screen;
    OledPages pages;

    // plausible performing state
    OledState &st = pages.st;
    int knobs[5] = { 200, 640, 1023, 80, 500 };
    for (int i = 0; i < 5; i++) st.knobs[i] = knobs[i];
    st.vuL = 72;
    st.vuR = 45;
    st.gain = 25;
    st.flags = OLED_FLAG_TRIG | OLED_FLAG_PERSIST | OLED_FLAG_AUDIO_MUTE
             | OLED_FLAG_WIFI | OLED_FLAG_SEQ_PLAY | OLED_FLAG_MIDI_ACT
             | OLED_FLAG_STREAM
             | OLED_FLAG_KNOB_MOD(0) | OLED_FLAG_KNOB_MOD(2)
             | OLED_FLAG_KNOB_MOD(3);
    st.modeIndex = 11;
    st.modeCount = 57;
    st.sceneIndex = 1;
    st.sceneCount = 8;
    st.fps = 30;
    st.wifiLevel = 3;
    st.midiChannel = 1;
    int cc[5] = { 20, 21, 22, 23, 24 };
    for (int i = 0; i < 5; i++) st.knobCC[i] = cc[i];

    pages.setText("mode", "S - Bounce Bounce");
    pages.setText("scene", "scene-0002");
    pages.setText("ssid", "StudioWifi");
    pages.setText("ip", "192.168.1.42");
    pages.setText("midi", "Keystep");
    pages.setText("trig", "Audio");
    pages.setText("res", "1280x720");
    pages.setText("ver", "3.1");
    pages.setText("url", "192.168.1.42/live");
    pages.setText("sinfo", "480x270 12fps");

    const char *slots[OLED_KEY_SLOTS] = {
        "Bounce", "Trails", "Grid", "", "Spiral", "Wave", "Strobe"
    };
    for (int i = 0; i < OLED_KEY_SLOTS; i++) pages.setKeymap(i, slots[i]);

    for (int p = 0; p < OLED_NUM_PAGES; p++) {
        pages.setPage(p);
        pages.render(screen);
        dump(screen, prefix, p);
    }

    // and the transient overlay, one line and two, info and warning
    pages.setPage(OLED_PAGE_PERFORM);
    pages.notify("Audio Muted", "", false);
    pages.render(screen);
    dump(screen, prefix, OLED_NUM_PAGES);

    pages.notify("C# set", "Bounce Bounce Bounce", false);
    pages.render(screen);
    dump(screen, prefix, OLED_NUM_PAGES + 2);

    pages.notify("Modulation", "knob seq is playing", true);
    pages.render(screen);
    dump(screen, prefix, OLED_NUM_PAGES + 3);

    pages.notify("Depth 3", "0.62 =========-----", false);
    pages.render(screen);
    dump(screen, prefix, OLED_NUM_PAGES + 4);

    // the live page again with the stream stopped
    pages.tickNotify(10000);
    pages.setPage(OLED_PAGE_STREAM);
    st.flags &= ~OLED_FLAG_STREAM;
    pages.render(screen);
    dump(screen, prefix, OLED_NUM_PAGES + 1);

    return 0;
}
