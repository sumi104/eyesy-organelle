#include "OledPages.h"

#include <stdio.h>
#include <string.h>

#define NOTIFY_MS 1200.f

// the 5x8 font advances 6px per character, so 21 characters fit across
#define MAXCHARS 21

static const char *KEY_NAMES[OLED_KEY_SLOTS] = {
    "C", "D", "E", "F", "G", "A", "B"
};

static void copyText(char *dst, const char *src) {
    strncpy(dst, src, OLED_TEXT_LEN - 1);
    dst[OLED_TEXT_LEN - 1] = 0;
}

OledPages::OledPages() {
    memset(&st, 0, sizeof(st));
    copyText(st.mode, "---");
    copyText(st.scene, "None");
    copyText(st.ssid, "off");
    copyText(st.ip, "-");
    copyText(st.midiDev, "none");
    copyText(st.trigSrc, "Audio");
    copyText(st.res, "-");
    copyText(st.ver, "3.1");
    copyText(st.url, "no network");
    copyText(st.streamInfo, "-");
    for (int i = 0; i < OLED_KEY_SLOTS; i++) st.keymap[i][0] = 0;
    for (int i = 0; i < 5; i++) st.knobCC[i] = -1;
    st.midiChannel = 1;
    page = OLED_PAGE_PERFORM;
    dirty = true;
    notifyLine1[0] = 0;
    notifyLine2[0] = 0;
    notifyTimeLeft = 0;
}

void OledPages::nextPage() {
    page = (page + 1) % OLED_NUM_PAGES;
    dirty = true;
}

void OledPages::prevPage() {
    page = (page + OLED_NUM_PAGES - 1) % OLED_NUM_PAGES;
    dirty = true;
}

void OledPages::setPage(int p) {
    if (p < 0 || p >= OLED_NUM_PAGES) return;
    page = p;
    dirty = true;
}

// pages that show an on/off setting let the encoder press switch it, the
// rest ignore the press so the knob behaves the same way everywhere
const char *OledPages::toggleAction() {
    switch (page) {
        case OLED_PAGE_STREAM: return "stream";
        case OLED_PAGE_MIDI:   return "clock";
        default:               return 0;
    }
}

void OledPages::setText(const char *key, const char *val) {
    if      (!strcmp(key, "mode"))  copyText(st.mode, val);
    else if (!strcmp(key, "scene")) copyText(st.scene, val);
    else if (!strcmp(key, "ssid"))  copyText(st.ssid, val);
    else if (!strcmp(key, "ip"))    copyText(st.ip, val);
    else if (!strcmp(key, "midi"))  copyText(st.midiDev, val);
    else if (!strcmp(key, "trig"))  copyText(st.trigSrc, val);
    else if (!strcmp(key, "res"))   copyText(st.res, val);
    else if (!strcmp(key, "ver"))   copyText(st.ver, val);
    else if (!strcmp(key, "url"))   copyText(st.url, val);
    else if (!strcmp(key, "sinfo")) copyText(st.streamInfo, val);
    else return;
    dirty = true;
}

void OledPages::setKeymap(int slot, const char *name) {
    if (slot < 0 || slot >= OLED_KEY_SLOTS) return;
    copyText(st.keymap[slot], name);
    dirty = true;
}

void OledPages::notify(const char *line1, const char *line2) {
    copyText(notifyLine1, line1);
    copyText(notifyLine2, line2 ? line2 : "");
    notifyTimeLeft = NOTIFY_MS;
    dirty = true;
}

void OledPages::tickNotify(float elapsedMs) {
    if (notifyTimeLeft <= 0) return;
    notifyTimeLeft -= elapsedMs;
    if (notifyTimeLeft <= 0) {
        notifyTimeLeft = 0;
        notifyLine1[0] = 0;
        notifyLine2[0] = 0;
        dirty = true;
    }
}

/* drawing helpers */

// A key name reversed out of a filled block, which is what tells a key apart
// from the words around it. Returns how far to move along for the next thing.
// Eight tall against a nine pixel row pitch so a column of them reads as
// separate keys rather than one continuous bar; the names are all capitals
// and do not reach into the row that gives up.
int OledPages::drawKey(OledScreen &s, int x, int y, const char *key) {
    int w = (strlen(key) * 6) + 1;
    s.fill_area(x - 1, y - 1, w, 8, 1);
    s.println(key, x, y, 8, 0);
    return w + 1;
}

// vertical fader, like the knob sliders in the video OSD
void OledPages::drawKnobBar(OledScreen &s, int x, int y, int h, int val) {
    const int w = 11;
    if (val < 0) val = 0;
    if (val > 1023) val = 1023;
    s.draw_box(x, y, w, h, 1);
    int fill = (val * (h - 2)) / 1023;
    if (fill > 0) s.fill_area(x + 1, y + h - 1 - fill, w - 2, fill, 1);
}

// horizontal bar used for VU and gain, val is 0 - 100
void OledPages::drawMeter(OledScreen &s, int x, int y, int w, int h, int val) {
    if (val < 0) val = 0;
    if (val > 100) val = 100;
    s.draw_box(x, y, w, h, 1);
    int fill = (val * (w - 2)) / 100;
    if (fill > 0) s.fill_area(x + 1, y + 1, fill, h - 2, 1);
}

// small 3 bar wifi indicator, level 0 draws a crossed out base
void OledPages::drawWifi(OledScreen &s, int x, int y, int level) {
    for (int i = 0; i < 3; i++) {
        int h = 2 + (i * 2);
        if (level > i) s.fill_area(x + (i * 3), y + 6 - h, 2, h, 1);
        else s.fill_area(x + (i * 3), y + 6, 2, 1, 1);
    }
}

/* pages */

void OledPages::renderTopBar(OledScreen &s) {
    char buf[MAXCHARS + 1];

    // page name on the left
    const char *name = "PERFORM";
    if (page == OLED_PAGE_STATUS) name = "STATUS";
    else if (page == OLED_PAGE_MIDI) name = "MIDI";
    else if (page == OLED_PAGE_KEYS) name = "MODE KEYS";
    else if (page == OLED_PAGE_STREAM) name = "LIVE";
    else if (page == OLED_PAGE_HELP) name = "CONTROLS";
    s.println(name, 2, 0, 8, 1);

    // status letters in the middle, right aligned against the wifi icon
    char st_letters[10];
    int n = 0;
    if (st.flags & OLED_FLAG_AUDIO_MUTE) st_letters[n++] = 'M';
    if (st.flags & OLED_FLAG_CLOCK_MUTE) st_letters[n++] = 'K';
    if (st.flags & OLED_FLAG_NOTE_MUTE)  st_letters[n++] = 'N';
    if (st.flags & OLED_FLAG_FREEZE)     st_letters[n++] = 'F';
    if (st.flags & OLED_FLAG_PERSIST)    st_letters[n++] = 'P';
    if (st.flags & OLED_FLAG_SHIFT)      st_letters[n++] = 'S';
    if (st.flags & OLED_FLAG_SEQ_REC)    st_letters[n++] = 'R';
    else if (st.flags & OLED_FLAG_SEQ_PLAY) st_letters[n++] = 'Q';
    st_letters[n] = 0;
    if (n) s.println(st_letters, 96 - (n * 6), 0, 8, 1);

    // wifi and page number on the right
    drawWifi(s, 100, 1, st.wifiLevel);
    snprintf(buf, sizeof(buf), "%d", page + 1);
    s.println(buf, 118, 0, 8, 1);

    // a dot by the page number means the encoder press does something here
    if (toggleAction()) s.fill_area(112, 2, 3, 3, 1);

    // separator
    s.draw_line(0, 8, 127, 8, 1);
}

void OledPages::renderPerform(OledScreen &s) {
    char buf[64];

    snprintf(buf, sizeof(buf), "%d/%d %s",
             st.modeIndex + 1, st.modeCount, st.mode);
    s.setLine(1, buf);

    if (st.sceneIndex >= 0)
        snprintf(buf, sizeof(buf), "S %d/%d %s",
                 st.sceneIndex + 1, st.sceneCount, st.scene);
    else
        snprintf(buf, sizeof(buf), "S -/%d none", st.sceneCount);
    s.setLine(2, buf);

    // knob faders, left to right same as the panel: knob 1-4 then volume
    for (int i = 0; i < 5; i++)
        drawKnobBar(s, 2 + (i * 13), 34, 26, st.knobs[i]);

    // stereo VU and input gain on the right
    s.println("L", 70, 34, 8, 1);
    drawMeter(s, 78, 33, 49, 8, st.vuL);
    s.println("R", 70, 44, 8, 1);
    drawMeter(s, 78, 43, 49, 8, st.vuR);
    s.println("G", 70, 55, 8, 1);
    drawMeter(s, 78, 55, 49, 5, st.gain);

    // trigger flashes a bar under the meters
    if (st.flags & OLED_FLAG_TRIG) s.fill_area(78, 61, 49, 3, 1);
}

void OledPages::renderStatus(OledScreen &s) {
    char buf[64];

    snprintf(buf, sizeof(buf), "Wifi %s", st.ssid);
    s.setLine(1, buf);
    snprintf(buf, sizeof(buf), "IP   %s", st.ip);
    s.setLine(2, buf);
    snprintf(buf, sizeof(buf), "Res  %s", st.res);
    s.setLine(3, buf);
    snprintf(buf, sizeof(buf), "FPS  %d   %s", st.fps,
             (st.flags & OLED_FLAG_USB) ? "USB" : "SD");
    s.setLine(4, buf);
    snprintf(buf, sizeof(buf), "EYESY v%s  OG-S", st.ver);
    s.setLine(5, buf);
}

void OledPages::renderMidi(OledScreen &s) {
    char buf[64];

    snprintf(buf, sizeof(buf), "Channel %d", st.midiChannel);
    s.setLine(1, buf);
    snprintf(buf, sizeof(buf), "CC %d %d %d %d %d",
             st.knobCC[0], st.knobCC[1], st.knobCC[2], st.knobCC[3], st.knobCC[4]);
    s.setLine(2, buf);
    snprintf(buf, sizeof(buf), "Trig %s", st.trigSrc);
    s.setLine(3, buf);
    snprintf(buf, sizeof(buf), "Clock %s",
             (st.flags & OLED_FLAG_CLOCK_MUTE) ? "MUTED" : "on");
    s.setLine(4, buf);
    snprintf(buf, sizeof(buf), "In %s", st.midiDev);
    s.setLine(5, buf);

    // note activity indicator
    if (st.flags & OLED_FLAG_MIDI_ACT) s.fill_area(120, 43, 6, 6, 1);
}

// The upper octave, split the way the keyboard is: the five black keys drive
// knob modulation across the top, the seven white keys recall modes below.
void OledPages::renderKeys(OledScreen &s) {
    char buf[24];

    // one lamp per knob, filled while that knob is being wobbled
    s.println("MOD", 2, 11, 8, 1);
    for (int i = 0; i < 5; i++) {
        int cx = 32 + (i * 18);
        if (st.flags & OLED_FLAG_KNOB_MOD(i)) s.draw_filled_circle(cx, 15, 4, 1);
        else s.draw_circle(cx, 15, 4, 1);
    }

    s.draw_line(0, 21, 127, 21, 1);

    // Seven white keys, four in the left column and three in the right. The
    // key is reversed out of a filled block so the eye can pick it out of the
    // run of mode names, then a space, then the name.
    for (int i = 0; i < OLED_KEY_SLOTS; i++) {
        int col = i / 4;
        int row = i % 4;
        int x = (col * 64) + 2;
        int y = 24 + (row * 9);
        int after = x + drawKey(s, x, y, KEY_NAMES[i]);

        const char *name = st.keymap[i][0] ? st.keymap[i] : "-";
        snprintf(buf, sizeof(buf), "%s", name);
        buf[8] = 0;   // what is left of the column after the key and the space
        s.println(buf, after + 4, y, 8, 1);
    }
}

// the only page where the encoder press does something other than page home
void OledPages::renderStream(OledScreen &s) {
    bool on = (st.flags & OLED_FLAG_STREAM) != 0;

    s.println(on ? "ON" : "OFF", 4, 11, 16, 1);
    s.println(on ? "STREAMING" : "stopped", 56, 15, 8, 1);

    s.draw_line(0, 30, 127, 30, 1);

    // the watch address, without the scheme so it fits on one line
    s.println(st.url, 2, 34, 8, 1);
    s.println(st.streamInfo, 2, 45, 8, 1);
    s.println(on ? "Push knob to stop" : "Push knob to start", 2, 56, 8, 1);
}

// Keys reversed out the same way as on MODE KEYS, so the whole instrument
// reads one way. Two keys next to each other are the pair that steps a thing
// down and up, two with a + between them are held together.
struct HelpEntry {
    const char *key;
    const char *second;   // null for a single key
    bool held;            // draw a + between them rather than butting them up
    const char *label;
};

// The columns are not the same width. Held combinations are much the widest
// thing here, so the left column is given the room for them and the right one
// takes the entries that are a single key and a short word.
#define HELP_COL_LEFT  2
#define HELP_COL_RIGHT 72
#define HELP_ROWS      6

void OledPages::renderHelp(OledScreen &s) {
    static const HelpEntry ENTRIES[] = {
        // left column, up to 67 pixels
        { "AUX", 0,     false, "Osd"     },
        { "C#",  0,     false, "Shift"   },
        { "D#",  0,     false, "Persist" },
        { "C#",  "AUX", true,  "Menu"    },
        { "C#",  "D#",  true,  "Seq"     },
        { "C",   "D",   false, "Mode"    },
        // right column, up to 49
        { "E",   "F",   false, "Scene"   },
        { "G",   0,     false, "Save"    },
        { "A",   0,     false, "Grab"    },
        { "B",   0,     false, "Trig"    },
        { "F#",  0,     false, "Mute"    },
        { "G#",  0,     false, "Clock"   },
    };
    const int count = sizeof(ENTRIES) / sizeof(ENTRIES[0]);

    for (int i = 0; i < count; i++) {
        const HelpEntry &e = ENTRIES[i];
        int cx = (i / HELP_ROWS) ? HELP_COL_RIGHT : HELP_COL_LEFT;
        int y = 10 + ((i % HELP_ROWS) * 9);

        cx += drawKey(s, cx, y, e.key);
        if (e.second) {
            if (e.held) {
                s.println("+", cx, y, 8, 1);
                cx += 6;
            }
            cx += drawKey(s, cx, y, e.second);
        }
        s.println(e.label, cx + 3, y, 8, 1);
    }
}

void OledPages::renderNotify(OledScreen &s) {
    s.clear();

    if (!notifyLine2[0]) {
        s.draw_box(0, 18, 128, 28, 1);
        s.println(notifyLine1, 4, 24, 16, 1);
        return;
    }

    // the heading gets the big font, the detail goes underneath in the small
    // one where a long mode name still fits across the screen
    s.draw_box(0, 12, 128, 40, 1);
    s.println(notifyLine1, 5, 16, 16, 1);
    s.println(notifyLine2, 5, 37, 8, 1);
}

void OledPages::render(OledScreen &s) {
    s.clear();

    if (notifyTimeLeft > 0) {
        renderNotify(s);
    } else {
        renderTopBar(s);
        switch (page) {
            case OLED_PAGE_STATUS: renderStatus(s); break;
            case OLED_PAGE_MIDI:   renderMidi(s);   break;
            case OLED_PAGE_KEYS:   renderKeys(s);   break;
            case OLED_PAGE_STREAM: renderStream(s); break;
            case OLED_PAGE_HELP:   renderHelp(s);   break;
            default:               renderPerform(s); break;
        }
    }

    dirty = false;
}
