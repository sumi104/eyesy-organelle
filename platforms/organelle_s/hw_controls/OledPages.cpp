#include "OledPages.h"

#include <stdio.h>
#include <string.h>

#define NOTIFY_MS 1200.f
// a refusal has to be read to be any use, a confirmation does not
#define NOTIFY_WARN_MS 2200.f

// the 5x8 font advances 6px per character, so 21 characters fit across
#define MAXCHARS 21

// A mode name wider than its line slides through it instead of being cut off.
// Two characters a second is about reading pace, and both ends stop long
// enough that the start and the finish are read rather than caught going past.
#define SCROLL_STEP_MS 500.f
#define SCROLL_HOLD_MS 1500.f

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
    copyText(st.clockLine, "Clock on");
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
    notifyWarn = false;
    notifyTimeLeft = 0;
    for (int i = 0; i < 2; i++) {
        marquee[i].offset = 0;
        marquee[i].max = 0;
        marquee[i].ms = 0;
        marquee[i].text[0] = 0;
    }
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
    else if (!strcmp(key, "clock")) copyText(st.clockLine, val);
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

void OledPages::notify(const char *line1, const char *line2, bool warn) {
    copyText(notifyLine1, line1);
    copyText(notifyLine2, line2 ? line2 : "");
    notifyWarn = warn;
    notifyTimeLeft = warn ? NOTIFY_WARN_MS : NOTIFY_MS;
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

const char *OledPages::sceneName() {
    return st.sceneIndex >= 0 ? st.scene : "none";
}

void OledPages::resetMarquee(Marquee &m) {
    if (m.offset != 0) dirty = true;
    m.offset = 0;
    m.ms = 0;
}

void OledPages::tickMarquee(Marquee &m, const char *text, float elapsedMs) {
    // New text starts from the left. Without this a short name inherits a long
    // one's offset and turns up already part way through itself, or with
    // nothing on the line at all.
    if (strcmp(m.text, text)) {
        copyText(m.text, text);
        resetMarquee(m);
        return;
    }

    // marqueeLine works out how much is over the end, so a name that fits sits
    // still and costs nothing. It is a frame behind after the text changes,
    // which the reset above has already covered.
    if (m.max <= 0) {
        resetMarquee(m);
        return;
    }

    m.ms += elapsedMs;
    bool atEnd = m.offset == 0 || m.offset >= m.max;
    if (m.ms < (atEnd ? SCROLL_HOLD_MS : SCROLL_STEP_MS)) return;
    m.ms = 0;

    m.offset = (m.offset >= m.max) ? 0 : m.offset + 1;
    dirty = true;
}

void OledPages::tickScroll(float elapsedMs) {
    // Only the perform page has sliding lines. Leaving it puts them back to
    // their starts, so coming back reads from the beginning rather than from
    // wherever they had wandered to while you were not looking.
    if (page != OLED_PAGE_PERFORM) {
        for (int i = 0; i < 2; i++) resetMarquee(marquee[i]);
        return;
    }

    tickMarquee(marquee[MARQUEE_MODE], st.mode, elapsedMs);
    tickMarquee(marquee[MARQUEE_SCENE], sceneName(), elapsedMs);
}

void OledPages::marqueeLine(Marquee &m, char *dst, int dstLen,
                            const char *prefix, const char *text) {
    int n = snprintf(dst, dstLen, "%s", prefix);
    if (n < 0 || n > MAXCHARS) n = MAXCHARS;

    int room = MAXCHARS - n;
    int over = (int) strlen(text) - room;
    m.max = (room > 0 && over > 0) ? over : 0;

    int off = m.offset > m.max ? m.max : m.offset;
    snprintf(dst + n, dstLen - n, "%s", text + off);
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
    char st_letters[12];
    int n = 0;
    // M and S say what the auto picker is picking, so the audio mute and the
    // shift key give those letters up: X is the usual mark for muted and ^ is
    // what shift is called on a keyboard
    if (st.flags & OLED_FLAG_AUDIO_MUTE) st_letters[n++] = 'X';
    if (st.flags & OLED_FLAG_CLOCK_MUTE) st_letters[n++] = 'K';
    if (st.flags & OLED_FLAG_NOTE_MUTE)  st_letters[n++] = 'N';
    if (st.flags & OLED_FLAG_FREEZE)     st_letters[n++] = 'F';
    if (st.flags & OLED_FLAG_PERSIST)    st_letters[n++] = 'P';
    if (st.flags & OLED_FLAG_AUTO_MODES)  st_letters[n++] = 'M';
    if (st.flags & OLED_FLAG_AUTO_SCENES) st_letters[n++] = 'S';
    // the three sequencer states are exclusive, so this stays one letter:
    // lower case r is armed and waiting for a knob, capital R is recording
    if (st.flags & OLED_FLAG_SEQ_REC)       st_letters[n++] = 'R';
    else if (st.flags & OLED_FLAG_SEQ_ARM)  st_letters[n++] = 'r';
    else if (st.flags & OLED_FLAG_SEQ_PLAY) st_letters[n++] = 'Q';
    // last because it is the one to lose when they do not all fit: shift is
    // the only one of these you are holding down while you read it
    if (st.flags & OLED_FLAG_SHIFT)      st_letters[n++] = '^';
    // Right aligned against the wifi icon, but never far enough left to run
    // into the page name: MODE KEYS is the longest at nine characters and
    // ends at x 55. That leaves room for seven letters, which is as many as
    // can be set at once, and any more are dropped rather than drawn over
    // something else.
    const int lettersLeft = 58;
    const int maxLetters = (100 - lettersLeft) / 6;
    if (n > maxLetters) n = maxLetters;
    st_letters[n] = 0;
    if (n) {
        int x = 96 - (n * 6);
        if (x < lettersLeft) x = lettersLeft;
        s.println(st_letters, x, 0, 8, 1);
    }

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

    char prefix[24];

    // "12/57 " and "S 2/8 " stay put and the names slide through what is left
    // of their lines. Which half is worth scrolling is not a close call: the
    // numbers are read at a glance, the names are what run off the end.
    snprintf(prefix, sizeof(prefix), "%d/%d ", st.modeIndex + 1, st.modeCount);
    marqueeLine(marquee[MARQUEE_MODE], buf, sizeof(buf), prefix, st.mode);
    s.setLine(1, buf);

    if (st.sceneIndex >= 0)
        snprintf(prefix, sizeof(prefix), "S %d/%d ",
                 st.sceneIndex + 1, st.sceneCount);
    else
        snprintf(prefix, sizeof(prefix), "S -/%d ", st.sceneCount);
    marqueeLine(marquee[MARQUEE_SCENE], buf, sizeof(buf), prefix, sceneName());
    s.setLine(2, buf);

    // Knob faders, left to right same as the panel: knob 1-4 then volume. A
    // dot over one says that knob is being wobbled, the same filled circle
    // the MODE KEYS page uses, so the two pages read the same way. Nothing is
    // drawn for a knob that is not, which keeps the usual case quiet.
    for (int i = 0; i < 5; i++) {
        int x = 2 + (i * 13);
        if (st.flags & OLED_FLAG_KNOB_MOD(i)) s.draw_filled_circle(x + 5, 33, 2, 1);
        drawKnobBar(s, x, 38, 24, st.knobs[i]);
    }

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
    // the engine composes this: it says the clock is muted, or which Link
    // session is being followed, depending on where the beat comes from
    s.setLine(4, st.clockLine);
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
#define HELP_COL_RIGHT 66
#define HELP_ROWS      6

void OledPages::renderHelp(OledScreen &s) {
    static const HelpEntry ENTRIES[] = {
        // left column, up to 61 pixels
        { "AUX", 0,    false, "Osd"     },
        { "C#",  0,    false, "Shift"   },
        { "D#",  0,    false, "Persist" },
        { "C#",  "K1", true,  "Gain"    },
        { "C#",  "D#", true,  "Seq"     },
        { "C",   "D",  false, "Mode"    },
        // right column, up to 49
        { "E",   "F",  false, "Scene"   },
        { "G",   0,    false, "Save"    },
        { "A",   0,    false, "Grab"    },
        { "B",   0,    false, "Trig"    },
        { "F#",  0,    false, "Mute"    },
        { "G#",  0,    false, "Clock"   },
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

// Both lines in the small font. The second line is usually the half that
// matters — which mode was stored, why something was refused — and setting the
// first in the big font made the important one the harder one to read.
//
// Drawn over the page rather than instead of it, so a second of message does
// not cost you your place.
void OledPages::renderNotify(OledScreen &s) {
    const bool twoLines = notifyLine2[0] != 0;
    const int top = twoLines ? 19 : 24;
    const int height = twoLines ? 30 : 18;

    s.fill_area(0, top, 128, height, 0);
    s.draw_box(0, top, 128, height, 1);

    // a reversed ! or i, the same mark the key names wear, so what kind of
    // message it is reads before any of the words do
    const int line1 = top + 6;
    int x = 8 + drawKey(s, 6, line1, notifyWarn ? "!" : "i");
    s.println(notifyLine1, x, line1, 8, 1);

    if (twoLines) s.println(notifyLine2, 6, top + 17, 8, 1);
}

void OledPages::render(OledScreen &s) {
    s.clear();

    {
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

    if (notifyTimeLeft > 0) renderNotify(s);

    dirty = false;
}
