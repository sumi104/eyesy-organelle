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

#define OLED_TEXT_LEN 40
#define OLED_KEY_SLOTS 12

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

        // key is one of: mode scene ssid ip midi trig res ver url sinfo
        void setText(const char *key, const char *val);

        // Name of the on/off setting this page owns, or null when there is
        // nothing to switch here and the encoder press should do nothing.
        // The engine maps these in osc.py.
        const char *toggleAction();
        void setKeymap(int slot, const char *name);

        // transient full screen message, the second line is optional and is
        // set in the small font under the first
        void notify(const char *line1, const char *line2);
        void tickNotify(float elapsedMs);

        // true when something changed since the last render
        bool isDirty() { return dirty; }
        void touch() { dirty = true; }

        void render(OledScreen &s);

    private:
        int page;
        bool dirty;
        char notifyLine1[OLED_TEXT_LEN];
        char notifyLine2[OLED_TEXT_LEN];
        float notifyTimeLeft;

        void renderTopBar(OledScreen &s);
        void renderPerform(OledScreen &s);
        void renderStatus(OledScreen &s);
        void renderMidi(OledScreen &s);
        void renderKeys(OledScreen &s);
        void renderStream(OledScreen &s);
        void renderHelp(OledScreen &s);
        void renderNotify(OledScreen &s);

        void drawKnobBar(OledScreen &s, int x, int y, int h, int val);
        void drawMeter(OledScreen &s, int x, int y, int w, int h, int val);
        void drawWifi(OledScreen &s, int x, int y, int level);
};

#endif
