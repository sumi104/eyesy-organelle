import pygame

import organelle
from screen import Screen
from widget_menu import WidgetMenu, MenuItem

FOOTER_PLAIN = (chr(0x2680) + "     = Cancel     " + chr(0x2682)
                + "   = Up/Down     " + chr(0x2683) + "  = Enter")
FOOTER_ADJUST = (chr(0x2680) + "     = Cancel     " + chr(0x2681)
                 + "   = Adjust     " + chr(0x2682) + "   = Up/Down     "
                 + chr(0x2683) + "  = Save")

BLOCKED_MESSAGE = "Trigger is on. Let go of the foot switch or B to change this."


class ScreenControls(Screen):
    """The settings that belong to a key or a jack rather than to a subsystem.

    They were scattered: the pedal and the cycle under System Stuff, next to
    backing up an SD card, and knob modulation under MIDI Settings, where it
    has nothing to do with MIDI. Two of them are a pair - Knob Modulation
    times the knob wobble and Auto Random Cycle times the palette wobble - and
    that was invisible with one on each screen.

    Every row here is organelle only, which is why the whole screen is: on
    EYESY hardware there is no pedal, no upper octave and no key that switches
    the auto picker on, so all three would be settings with nothing to set.
    """

    def __init__(self, eyesy):
        super().__init__(eyesy)
        self.title = "Controls"
        self.footer = FOOTER_PLAIN

        self.footswitch_item = self._setting(
            "footswitch", 0, len(eyesy.FOOTSWITCH_ACTIONS) - 1)
        self.knob_mod_item = self._setting("knob_mod_sync", 0, 1)
        self.interval_item = self._setting(
            "auto_random_interval", 0, len(eyesy.AUTO_RANDOM_INTERVALS) - 1)

        items = [self.footswitch_item, self.knob_mod_item, self.interval_item,
                 MenuItem("◀  Exit", self.goto_home)]
        self.menu = WidgetMenu(eyesy, items)
        self.menu.visible_items = len(items)
        self.menu.off_y = 43

        # key press timers for repeats while adjusting a value
        self.key4_td = 0
        self.key5_td = 0

    def _setting(self, name, minv, maxv):
        item = MenuItem("", self.save)
        item.adjustable = True
        item.name = name
        item.min_value = minv
        item.max_value = maxv
        return item

    def before(self):
        # Exit is what the cursor opens on, so nothing here changes by
        # accident on the way past
        self.menu.selected_index = len(self.menu.items) - 1

        self.footswitch_item.value = self.eyesy.config["footswitch"]
        self.knob_mod_item.value = 1 if self.eyesy.config["knob_mod_sync"] else 0

        seconds = self.eyesy.config["auto_random_interval"]
        try:
            self.interval_item.value = \
                self.eyesy.AUTO_RANDOM_INTERVALS.index(seconds)
        except ValueError:
            self.interval_item.value = 0

        for item in self.menu.items:
            self.relabel(item)

    def after(self):
        pass

    # --- what each row says ------------------------------------------------

    def relabel(self, item):
        if item is self.footswitch_item:
            action = self.eyesy.FOOTSWITCH_ACTIONS[item.value]
            item.text = f"Foot Switch: {action}"
        elif item is self.knob_mod_item:
            item.text = ("Knob Modulation: Synced to Trigger" if item.value
                         else "Knob Modulation: Free Running")
        elif item is self.interval_item:
            seconds = self.eyesy.AUTO_RANDOM_INTERVALS[item.value]
            every = "Random" if seconds < 0 else f"{seconds} sec"
            item.text = f"Auto Random Cycle: {every}"

    # --- the pedal row locks while something is holding the trigger --------

    def trigger_held(self):
        """The pedal or the B key is down right now.

        Both drive the same trigger, and the pedal latches which of its two
        jobs it has when it goes down. Letting the setting move underneath a
        press that is already in flight is how the test tone gets stranded on,
        so the row stops responding until whatever is held is let go.
        """
        return bool(self.eyesy.key10_status or self.eyesy.footswitch_status)

    def footswitch_blocked(self):
        """True when the pedal row is under the cursor and cannot be moved."""
        selected = self.menu.items[self.menu.selected_index]
        return selected is self.footswitch_item and self.trigger_held()

    # --- adjusting ---------------------------------------------------------

    def menu_dec_value(self, item):
        item.value = max(item.value - item.value_delta, item.min_value)
        self.relabel(item)

    def menu_inc_value(self, item):
        item.value = min(item.value + item.value_delta, item.max_value)
        self.relabel(item)

    def save(self):
        if self.footswitch_blocked():
            return
        self.eyesy.config["footswitch"] = self.footswitch_item.value
        # a bool, not the 0 or 1 the menu holds: validate_config() checks this
        # one with isinstance and would throw an int away
        self.eyesy.config["knob_mod_sync"] = self.knob_mod_item.value == 1
        self.eyesy.config["auto_random_interval"] = \
            self.eyesy.AUTO_RANDOM_INTERVALS[self.interval_item.value]
        self.eyesy.save_config_file()

    def handle_events(self):
        self.menu.handle_events()

        item = self.menu.items[self.menu.selected_index]
        # Exit is the one row with nothing to adjust, so the footer says what
        # the keys actually do where the cursor is
        self.footer = FOOTER_ADJUST if item.adjustable else FOOTER_PLAIN
        if not item.adjustable or self.footswitch_blocked():
            return

        if self.eyesy.key4_press:
            self.menu_dec_value(item)
            self.key4_td = 0
        if self.eyesy.key4_status:
            self.key4_td += 1
            if self.key4_td > 10: self.menu_dec_value(item)

        if self.eyesy.key5_press:
            self.menu_inc_value(item)
            self.key5_td = 0
        if self.eyesy.key5_status:
            self.key5_td += 1
            if self.key5_td > 10: self.menu_inc_value(item)

    def render(self, surface):
        self.menu.render(surface)

        # say why the row is not moving rather than looking broken
        if self.footswitch_blocked():
            top = 30 + self.menu.off_y + len(self.menu.items) * 25 + 8
            notice = self.font.render(BLOCKED_MESSAGE, True, (255, 200, 80))
            surface.blit(notice, (32, top))

    def goto_home(self):
        self.eyesy.switch_menu_screen("home")
