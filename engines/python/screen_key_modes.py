import pygame

import oled
import organelle
from screen import Screen
from widget_menu import WidgetMenu, MenuItem


def wha(): pass


class ScreenKeyModes(Screen):
    """Assigns a mode to each of the twelve upper octave keys.

    The same slots can be set while performing by holding shift and pressing
    the key, this screen is for going through them all at once.
    """

    def __init__(self, eyesy):
        super().__init__(eyesy)
        self.title = "Upper Octave Mode Keys"
        self.footer = (chr(0x2680) + "     = Cancel     " + chr(0x2681)
                       + "   = Adjust     " + chr(0x2682) + "   = Up/Down     "
                       + chr(0x2683) + "  = Save & Exit")
        self.menu = WidgetMenu(eyesy, [MenuItem("", wha) for _ in range(12)])
        for item in self.menu.items:
            item.adjustable = True
        self.menu.visible_items = 12
        self.menu.off_y = 43
        self.key4_td = 0
        self.key5_td = 0

    def before(self):
        for slot, item in enumerate(self.menu.items):
            item.value = self._mode_index(self.eyesy.key_modes[slot])
            self._relabel(slot, item)

    def _mode_index(self, name):
        if name and name in self.eyesy.mode_names:
            return self.eyesy.mode_names.index(name)
        return -1

    def _relabel(self, slot, item):
        if item.value >= 0:
            name = self.eyesy.mode_names[item.value]
        else:
            name = "None"
        item.text = f"{organelle.SLOT_NAMES[slot]:<3} -> {name}"

    def render(self, surface):
        self.menu.render(surface)

    def menu_inc_value(self, item):
        item.value = min(item.value + 1, len(self.eyesy.mode_names) - 1)
        self._relabel(self.menu.selected_index, item)

    def menu_dec_value(self, item):
        item.value = max(item.value - 1, -1)
        self._relabel(self.menu.selected_index, item)

    def handle_events(self):
        self.menu.handle_events()

        item = self.menu.items[self.menu.selected_index]
        if item.adjustable and len(self.eyesy.mode_names) > 0:
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
        for slot, item in enumerate(self.menu.items):
            if item.value >= 0:
                self.eyesy.key_modes[slot] = self.eyesy.mode_names[item.value]
            else:
                self.eyesy.key_modes[slot] = ""
            oled.send_keymap(slot, self.eyesy.key_modes[slot])
        self.eyesy.config["key_modes"] = list(self.eyesy.key_modes)
        self.eyesy.save_config_file()

    def exit_menu(self):
        self.eyesy.switch_menu_screen("home")
