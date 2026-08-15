import pygame

import oled
import organelle
from screen import Screen
from widget_menu import WidgetMenu, MenuItem


def wha(): pass


class ScreenKeyModes(Screen):
    """What the upper octave keys do, and how often A# picks something new.

    The mode slots can also be set while performing by holding shift and
    pressing the key; this screen is for going through them all at once, and
    for the one setting that has no key of its own.
    """

    def __init__(self, eyesy):
        super().__init__(eyesy)
        self.title = "Mode Keys and Auto Random"
        self.footer = (chr(0x2680) + "     = Cancel     " + chr(0x2681)
                       + "   = Adjust     " + chr(0x2682) + "   = Up/Down     "
                       + chr(0x2683) + "  = Save & Exit")

        self.interval_item = MenuItem("", wha)
        self.interval_item.adjustable = True
        self.interval_item.name = "auto_random_interval"
        self.interval_item.min_value = 0
        self.interval_item.max_value = len(eyesy.AUTO_RANDOM_INTERVALS) - 1

        self.slot_items = []
        for _ in range(0, organelle.NUM_MODE_SLOTS):
            item = MenuItem("", wha)
            item.adjustable = True
            self.slot_items.append(item)

        self.menu = WidgetMenu(eyesy, [self.interval_item] + self.slot_items)
        self.menu.visible_items = len(self.menu.items)
        self.menu.off_y = 43
        self.key4_td = 0
        self.key5_td = 0

    def before(self):
        seconds = self.eyesy.config["auto_random_interval"]
        try:
            self.interval_item.value = self.eyesy.AUTO_RANDOM_INTERVALS.index(seconds)
        except ValueError:
            self.interval_item.value = 0
        self._relabel(self.interval_item)

        for slot, item in enumerate(self.slot_items):
            item.value = self._mode_index(self.eyesy.key_modes[slot])
            self._relabel(item)

    def _mode_index(self, name):
        if name and name in self.eyesy.mode_names:
            return self.eyesy.mode_names.index(name)
        return -1

    def _relabel(self, item):
        if item is self.interval_item:
            seconds = self.eyesy.AUTO_RANDOM_INTERVALS[item.value]
            every = "Random" if seconds < 0 else f"{seconds} sec"
            item.text = f"Auto Random Cycle: {every}"
            return

        slot = self.slot_items.index(item)
        if item.value >= 0:
            name = self.eyesy.mode_names[item.value]
        else:
            name = "None"
        item.text = f"{organelle.SLOT_NAMES[slot]:<3} -> {name}"

    def render(self, surface):
        self.menu.render(surface)

    def _limits(self, item):
        if item is self.interval_item:
            return item.min_value, item.max_value
        return -1, len(self.eyesy.mode_names) - 1

    def menu_inc_value(self, item):
        item.value = min(item.value + 1, self._limits(item)[1])
        self._relabel(item)

    def menu_dec_value(self, item):
        item.value = max(item.value - 1, self._limits(item)[0])
        self._relabel(item)

    def handle_events(self):
        self.menu.handle_events()

        item = self.menu.items[self.menu.selected_index]
        if item.adjustable:
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

        if self.eyesy.key8_press:
            self.save()
            self.exit_menu()

    def save(self):
        self.eyesy.config["auto_random_interval"] = \
            self.eyesy.AUTO_RANDOM_INTERVALS[self.interval_item.value]

        for slot, item in enumerate(self.slot_items):
            if item.value >= 0:
                self.eyesy.key_modes[slot] = self.eyesy.mode_names[item.value]
            else:
                self.eyesy.key_modes[slot] = ""
            oled.send_keymap(slot, self.eyesy.key_modes[slot])
        self.eyesy.config["key_modes"] = list(self.eyesy.key_modes)
        self.eyesy.save_config_file()

    def exit_menu(self):
        self.eyesy.switch_menu_screen("home")
