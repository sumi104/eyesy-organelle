#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sched.h>
#include <sys/stat.h>

#include "OSC/OSCMessage.h"
#include "OSC/SimpleWriter.h"
#include "UdpSocket.h"
#include "Timer.h"
#include "OledScreen.h"
#include "OledPages.h"

#include "hw_interfaces/CM3GPIO.h"

#define OSC_IN_PORT 4001
#define OSC_OUT_PORT 4000

// oled refresh interval, the spi write of the 1k frame buffer costs about 2ms
#define OLED_INTERVAL_MS 50.f

// knob stuff
void knobsInput(void);
void sendKnobs(void);
void keysInput(void);
void encoderInput(void);
void encoderButton(void);
void footswitchInput(void);
static const unsigned int MAX_KNOBS = 6;
static int16_t knobs_[MAX_KNOBS];

// the organelle keyboard is 24 keys plus the aux button, we pass the foot
// switch along as one more key so the engine can map it like any other control
static const unsigned int NUM_KEYS = 25;
static const unsigned int FOOTSWITCH_KEY = 25;

// OSC callbacks
void setLED(OSCMessage &msg);
void flashLED(OSCMessage &msg);
void oledState(OSCMessage &msg);
void oledText(OSCMessage &msg);
void oledNotify(OSCMessage &msg);
void oledPage(OSCMessage &msg);
void batteryEnable(OSCMessage &msg);

// buffer for sending OSC messages
SimpleWriter oscBuf;

// hardware interface controls
CM3GPIO controls;

// the oled frame buffer and the page renderer that fills it
OledScreen oledScreen;
OledPages oledPages;

// socket for OSC com
UdpSocket udpSock(OSC_IN_PORT);

// exit flag
int quit = 0;

// Whether the battery hardware is there to read. The engine sends it, because
// the setting lives in the config file; it starts off, so an Organelle S that
// never enables it can never act on a pin it has nothing connected to.
//
// It is kept here rather than asked for again because the point of doing this
// on this side is that it still works when the engine is not running - a card
// being written to does not care which process noticed the battery.
bool batteryEnabled = false;

// said once as the last bar goes, rather than every second from then on
bool batteryWarned = false;

// Hold the encoder on the SETTINGS page to restart the video engine.
//
// The engine draws the settings menu that has a Restart Video in it, which
// means that menu is no use for the two times you want it: when there is no
// monitor plugged in to read it on, and when the engine is the thing that has
// stopped. The encoder and this display are the only controls that outlive it
// - turning it already pages locally - so the restart lives here too.
//
// Long rather than a press because it cannot be taken back. The bar while it
// is held is what makes that discoverable and what lets go of it mean no.
#define RESTART_HOLD_MS 3000.f
Timer encHoldTimer;
bool encHoldDone = false;

int main(int argc, char* argv[]) {
    printf("build date " __DATE__ "   " __TIME__ "\n");
    char udpPacketIn[2048];
    int i = 0;
    int len = 0;

    Timer knobPollTimer, pingTimer, oledTimer, upTime;

    knobPollTimer.reset();
    pingTimer.reset();
    oledTimer.reset();
    upTime.reset();

    udpSock.setDestination(OSC_OUT_PORT, "localhost");
    OSCMessage msgIn;

    controls.init();

    // something on screen while the video engine starts up
    oledPages.notify("EYESY", "", false);
    oledPages.render(oledScreen);
    controls.updateOLED(oledScreen);

    quit = 0;

    for (;;) {
        // receive udp osc messages
        len = udpSock.readBuffer(udpPacketIn, 2048, 0);
        if (len > 0) {
            msgIn.empty();
            for (i = 0; i < len; i++) {
                msgIn.fill(udpPacketIn[i]);
            }
            if (!msgIn.hasError()) {
                // or'ing will do lazy eval, i.e. as soon as one succeeds it will stop
                bool processed =
                    msgIn.dispatch("/led", setLED, 0)
                    || msgIn.dispatch("/led/flash", flashLED, 0)
                    || msgIn.dispatch("/oled/state", oledState, 0)
                    || msgIn.dispatch("/oled/text", oledText, 0)
                    || msgIn.dispatch("/oled/notify", oledNotify, 0)
                    || msgIn.dispatch("/oled/page", oledPage, 0)
                    || msgIn.dispatch("/battery", batteryEnable, 0)
                    ;
                if (!processed) {
                    char buf[128];
                    msgIn.getAddress(buf,0,128);
                    fprintf(stderr, "unrecognised osc message received %s %i\n",buf,msgIn.size());
                }
            }
            else {
                fprintf(stderr, "osc message has error \n ");
            }
            msgIn.empty();
        }

        // check for events from hardware controls
        controls.poll();

        // handle events
        if (controls.knobFlag) knobsInput();
        if (controls.keyFlag) keysInput();
        if (controls.encTurnFlag) encoderInput();
        if (controls.encButFlag) encoderButton();
        if (controls.footswitchFlag) footswitchInput();

        // clear the flags for next time
        controls.clearFlags();

        // every 1 second do slow periodic tasks
        if (pingTimer.getElapsed() > 1000.f) {
            pingTimer.reset();
            controls.ping();
            sendKnobs();

            if (batteryEnabled) {
                OledState &st = oledPages.st;
                if (st.batteryBars != (int) controls.batteryBars
                        || st.onBattery != (bool) controls.pwrStatus) {
                    st.batteryBars = controls.batteryBars;
                    st.onBattery = controls.pwrStatus;
                    oledPages.touch();
                }

                // Both halves, the way Organelle_OS does it: the flag latches
                // once it is set, so the power pin is what says the battery is
                // still the thing running this.
                if (controls.lowBatteryShutdown && controls.pwrStatus) {
                    printf("low battery, shutting down\n");
                    oledPages.renderBigMessage(oledScreen, "Low Battery",
                                               "Auto Shutdown");
                    controls.updateOLED(oledScreen);
                    // no grace period. Organelle_OS does not give one either,
                    // and the threshold already has the margin in it - waiting
                    // spends exactly the charge the shutdown is there to save.
                    system("sudo shutdown -h now");
                    // straight out rather than through the quit flag: the
                    // refresh further down this same pass would render a page
                    // over the message if anything had marked it dirty, and
                    // the display keeps whatever was last written to it.
                    // Restart=on-failure, so leaving with 0 stays left.
                    return 0;
                }
                else if (controls.pwrStatus && controls.batteryBars <= 1) {
                    if (!batteryWarned) {
                        batteryWarned = true;
                        oledPages.notify("Low Battery", "charge or plug in", true);
                    }
                }
                else batteryWarned = false;
            }
        }

        // poll knobs every 20 ms
        if (knobPollTimer.getElapsed() > 20.f) {
            knobPollTimer.reset();
            controls.pollKnobs();
        }

        // refresh the oled, only pushing pixels out when something changed
        if (oledTimer.getElapsed() > OLED_INTERVAL_MS) {
            float elapsed = oledTimer.getElapsed();
            oledTimer.reset();
            oledPages.tickNotify(elapsed);
            oledPages.tickScroll(elapsed);

            // Held on the settings page: fill a bar, and at the end of it
            // restart the engine. Anywhere else the hold means nothing, so
            // paging away mid hold abandons it.
            if (controls.encBut && !encHoldDone
                    && oledPages.getPage() == OLED_PAGE_SETTINGS) {
                float held = encHoldTimer.getElapsed();
                if (held >= RESTART_HOLD_MS) {
                    encHoldDone = true;
                    printf("restart requested from the encoder\n");
                    oledPages.renderBigMessage(oledScreen, "Restart Video",
                                               "Restarting...");
                    controls.updateOLED(oledScreen);
                    // systemctl rather than asking the engine to exit: asking
                    // only works while it is well enough to be asked, and a
                    // hung engine is one of the two reasons this exists.
                    system("sudo systemctl restart eyesypy");
                    // nothing more this pass, or the refresh below paints a
                    // page over the message
                    continue;
                }
                oledPages.notifyHold("Restart Video", held / RESTART_HOLD_MS);
            }
            if (oledPages.isDirty()) {
                oledPages.render(oledScreen);
                controls.updateOLED(oledScreen);
            }
        }

        // check exit flag
        if (quit) {
            printf("quitting\n");
            return 0;
        }

        // main polling loop delay
        // slow it down for cm3 cause all the bit banging starts to eat CPU
        usleep(2000);
    } // for;;
}

/** OSC messages received internally (from the video engine or other program) **/

void setLED(OSCMessage &msg) {
    if (msg.isInt(0)) {
        controls.setLED(msg.getInt(0));
    }
}

void flashLED(OSCMessage &msg) {
}

// one packed message with everything that changes while performing,
// the field order has to match send_state() in engines/python/oled.py
void oledState(OSCMessage &msg) {
    int v[16];
    unsigned n = msg.size() < 16 ? msg.size() : 16;
    for (unsigned i = 0; i < n; i++) v[i] = msg.isInt(i) ? msg.getInt(i) : 0;
    if (n < 15) return;   // not the message we expect

    OledState &st = oledPages.st;
    for (int i = 0; i < 5; i++) st.knobs[i] = v[i];
    st.vuL = v[5];
    st.vuR = v[6];
    st.gain = v[7];
    st.flags = (unsigned) v[8];
    st.modeIndex = v[9];
    st.modeCount = v[10];
    st.sceneIndex = v[11];
    st.sceneCount = v[12];
    st.fps = v[13];
    st.wifiLevel = v[14];
    if (n >= 16) st.midiChannel = v[15];
    oledPages.touch();
}

void oledText(OSCMessage &msg) {
    char key[24];
    char val[64];
    if (!msg.isString(0) || !msg.isString(1)) return;
    msg.getString(0, key, sizeof(key));
    msg.getString(1, val, sizeof(val));
    oledPages.setText(key, val);
}

void oledNotify(OSCMessage &msg) {
    char line1[64];
    char line2[64];
    line2[0] = 0;
    if (!msg.isString(0)) return;
    msg.getString(0, line1, sizeof(line1));
    if (msg.isString(1)) msg.getString(1, line2, sizeof(line2));
    bool warn = msg.isInt(2) && msg.getInt(2) != 0;
    oledPages.notify(line1, line2, warn);
}

void oledPage(OSCMessage &msg) {
    if (msg.isInt(0)) oledPages.setPage(msg.getInt(0));
}

// The Battery row on Settings > Controls. Off on an Organelle S, which has no
// cells and no power pin worth reading.
void batteryEnable(OSCMessage &msg) {
    if (!msg.isInt(0)) return;
    bool on = msg.getInt(0) != 0;
    if (on == batteryEnabled) return;
    batteryEnabled = on;
    batteryWarned = false;
    oledPages.st.batteryOn = on;
    oledPages.touch();
}

/* functions to handle input from the organelle hardware controls */

void knobsInput() {
    bool changed = false;
    // knob 1-4 + volume + expression pedal, all 0-1023
    for(unsigned i = 0; i < MAX_KNOBS;i++) {
        int v = controls.adcs[i];

        // clamp to valid range in case of hardware glitches
        if(v < 0) v = 0;
        if(v > 1023) v = 1023;

        if(v==0 || v==1023) {
            // allow extremes
            changed |= v != knobs_[i];
            knobs_[i] = v;
        } else {
            // 75% new value, 25% old value
            int16_t nv = (v >> 1) + (v >> 2) + (knobs_[i] >> 2);
            int diff = nv - knobs_[i];
            if(diff>2 || diff <-2) {
                changed = true;
                knobs_[i] = nv;
            }
        }
    }
    if(changed) {
        OSCMessage msgOut("/knobs");
        for(unsigned i = 0; i < MAX_KNOBS;i++) {
            msgOut.add(knobs_[i]);
        }
        msgOut.send(oscBuf);
        udpSock.writeBuffer(oscBuf.buffer, oscBuf.length);
    }
}

void sendKnobs() {
    OSCMessage msgOut("/knobs");
    for(unsigned i = 0; i < MAX_KNOBS;i++) {
        msgOut.add(knobs_[i]);
    }
    msgOut.send(oscBuf);
    udpSock.writeBuffer(oscBuf.buffer, oscBuf.length);
}

// send the raw organelle key index, 0 is the aux button and 1-24 are the
// keyboard from low C up. the engine decides what each one does.
void keysInput(void) {
    for (unsigned i = 0; i < NUM_KEYS; i++){
        if(((controls.keyStates >> i) & 1) != ((controls.keyStatesLast >> i) & 1)){
            OSCMessage msgOut("/key");
            msgOut.add((int32_t) i);
            msgOut.add((int32_t) (((controls.keyStates >> i) & 1) * 100));
            msgOut.send(oscBuf);
            udpSock.writeBuffer(oscBuf.buffer, oscBuf.length);
        }
    }
    controls.keyStatesLast = controls.keyStates;
}

// the pedal jack looks like one more key to the engine
void footswitchInput(void) {
    OSCMessage msgOut("/key");
    msgOut.add((int32_t) FOOTSWITCH_KEY);
    msgOut.add((int32_t) (controls.footswitch ? 0 : 100));   // normally closed
    msgOut.send(oscBuf);
    udpSock.writeBuffer(oscBuf.buffer, oscBuf.length);
}

// the encoder pages the oled locally so it stays responsive, the engine gets
// a copy in case a menu wants it
void encoderInput(void) {
    // clockwise pages forward
    if (controls.encTurn == 1) oledPages.nextPage();
    else oledPages.prevPage();

    OSCMessage msgOut("/encoder/turn");
    msgOut.add((int32_t) controls.encTurn);
    msgOut.send(oscBuf);
    udpSock.writeBuffer(oscBuf.buffer, oscBuf.length);
}

void encoderButton(void) {
    if (controls.encBut) {
        encHoldTimer.reset();
        encHoldDone = false;
    }

    // the press switches whatever on/off setting the current page owns, and
    // does nothing at all on the pages that have none
    if (controls.encBut) {
        const char *action = oledPages.toggleAction();
        if (action) {
            OSCMessage msgOut("/oled/toggle");
            msgOut.add(action);
            msgOut.send(oscBuf);
            udpSock.writeBuffer(oscBuf.buffer, oscBuf.length);
        }
    }

    // forwarded so a future menu can use the encoder, nothing acts on it yet
    OSCMessage msgOut("/encoder/button");
    msgOut.add((int32_t) controls.encBut);
    msgOut.send(oscBuf);
    udpSock.writeBuffer(oscBuf.buffer, oscBuf.length);
}
