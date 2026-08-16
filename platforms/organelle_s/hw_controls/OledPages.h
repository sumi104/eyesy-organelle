#ifndef OLEDPAGES_H
#define OLEDPAGES_H

/*

OLED page renderer for EYESY on Organelle S.

The python video engine pushes state here over OSC (see engines/python/oled.py),
this side owns the page state so the encoder stays responsive even while the
engine is busy drawing or restarting.

*/

#include <stdint.h>
#include "OledScreen.h"

#define OLED_NUM_PAGES 6

// pages
#define OLED_PAGE_PERFORM 0
#define OLED_PAGE_STATUS  1
#define OLED_PAGE_MIDI    2
#define OLED_PAGE_KEYS    3
#define OLED_PAGE_STREAM  4
#define OLED_PAGE_HELP    5

// bits of OledState.flags, kept in sync with engines/python/oled.py
#define OLED_FLAG_TRIG        (1 << 0)
#define OLED_FLAG_PERSIST     (1 << 1)
#define OLED_FLAG_AUDIO_MUTE  (1 << 2)
#define OLED_FLAG_CLOCK_MUTE  (1 << 3)
#define OLED_FLAG_FREEZE      (1 << 4)
#define OLED_FLAG_SHIFT       (1 << 5)
#define OLED_FLAG_MENU        (1 << 6)
#define OLED_FLAG_OSD         (1 << 7)
#define OLED_FLAG_USB         (1 << 8)
#define OLED_FLAG_WIFI        (1 << 9)
#define OLED_FLAG_MIDI_ACT    (1 << 10)
#define OLED_FLAG_SEQ_PLAY    (1 << 11)
#define OLED_FLAG_SEQ_REC     (1 << 12)
#define OLED_FLAG_NOTE_MUTE   (1 << 13)
#define OLED_FLAG_STREAM      (1 << 14)
// bits 15 to 19, one per knob, set while its random modulation is running
#define OLED_FLAG_KNOB_MOD(i) (1 << (15 + (i)))
#define OLED_FLAG_AUTO_MODES  (1 << 20)
#define OLED_FLAG_AUTO_SCENES (1 << 21)
#define OLED_FLAG_SEQ_ARM     (1 << 22)

#define OLED_TEXT_LEN 40

// one per upper octave white key
#define OLED_KEY_SLOTS 7

struct OledState {
    int knobs[5];          // 0 - 1023
    int vuL, vuR;          // 0 - 100
    int gain;              // 0 - 100
    unsigned flags;
    int modeIndex, modeCount;
    int sceneIndex, sceneCount;
    int fps;
    int wifiLevel;         // 0 - 4, 0 is not connected
    int midiChannel;
    int knobCC[5];

    char mode[OLED_TEXT_LEN];
    char scene[OLED_TEXT_LEN];
    char ssid[OLED_TEXT_LEN];
    char ip[OLED_TEXT_LEN];
    char midiDev[OLED_TEXT_LEN];
    char trigSrc[OLED_TEXT_LEN];
    char clockLine[OLED_TEXT_LEN];  // clock mute, or the Link session
    char res[OLED_TEXT_LEN];
    char ver[OLED_TEXT_LEN];
    char url[OLED_TEXT_LEN];       // where to watch the live stream
    char streamInfo[OLED_TEXT_LEN]; // size and frame rate of the stream
    char keymap[OLED_KEY_SLOTS][OLED_TEXT_LEN];
};

class OledPages
{
    public:
        OledPages();

        OledState st;

        void nextPage();
        void prevPage();
        void setPage(int p);
        int  getPage() { return page; }

        // key is one of: mode scene ssid ip midi trig clock res ver url sinfo
        void setText(const char *key, const char *val);

        // Name of the on/off setting this page owns, or null when there is
        // nothing to switch here and the encoder press should do nothing.
        // The engine maps these in osc.py.
        const char *toggleAction();
        void setKeymap(int slot, const char *name);

        // Transient message over the current page. warn marks the ones that
        // say an action did not happen, which get a different mark and a
        // little longer on screen than the ones that just report.
        void notify(const char *line1, const char *line2, bool warn);
        void tickNotify(float elapsedMs);

        // Slides the mode and scene names, when they are too long for their
        // lines, through the room they have: a character at a time, holding at
        // each end. Called on the same tick as tickNotify. Wrapping is what
        // this avoids - neither line has anywhere to move down to.
        void tickScroll(float elapsedMs);

        // true when something changed since the last render
        bool isDirty() { return dirty; }
        void touch() { dirty = true; }

        void render(OledScreen &s);

    private:
        int page;
        bool dirty;
        char notifyLine1[OLED_TEXT_LEN];
        char notifyLine2[OLED_TEXT_LEN];
        bool notifyWarn;
        float notifyTimeLeft;

        // One of these per line of the perform page that slides. They run on
        // their own clocks rather than a shared one: the two names are
        // different lengths, so a shared clock would reach one end before the
        // other and they would drift apart at the holds anyway.
        struct Marquee {
            int offset;     // characters currently off the left
            int max;        // how many there are to give, 0 when it fits
            float ms;       // since the last step
            char text[OLED_TEXT_LEN];   // to notice the line's text changing
        };
        Marquee marquee[2];
        static const int MARQUEE_MODE  = 0;
        static const int MARQUEE_SCENE = 1;

        void resetMarquee(Marquee &m);
        void tickMarquee(Marquee &m, const char *text, float elapsedMs);

        // Lays out one sliding line: the prefix stays put and the text slides
        // through whatever is left. Sets m.max on the way, since that is where
        // the room is known.
        void marqueeLine(Marquee &m, char *dst, int dstLen,
                         const char *prefix, const char *text);

        // what the scene line calls a name, which is not st.scene when there
        // is no scene loaded
        const char *sceneName();

        void renderTopBar(OledScreen &s);
        void renderPerform(OledScreen &s);
        void renderStatus(OledScreen &s);
        void renderMidi(OledScreen &s);
        void renderKeys(OledScreen &s);
        void renderStream(OledScreen &s);
        void renderHelp(OledScreen &s);
        void renderNotify(OledScreen &s);

        int  drawKey(OledScreen &s, int x, int y, const char *key);
        void drawKnobBar(OledScreen &s, int x, int y, int h, int val);
        void drawMeter(OledScreen &s, int x, int y, int w, int h, int val);
        void drawWifi(OledScreen &s, int x, int y, int level);
};

#endif
