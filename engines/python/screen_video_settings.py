import subprocess
import re
import helpers
import streamer
from screen import Screen
from widget_menu import WidgetMenu, MenuItem

STREAM_RATES = [10, 15, 20, 30]

FOOTER_PLAIN = (chr(0x2680) + "     = Cancel     " + chr(0x2682)
                + "   = Up/Down     " + chr(0x2683) + "  = Enter")
FOOTER_ADJUST = (chr(0x2680) + "     = Cancel     " + chr(0x2681)
                 + "   = Adjust     " + chr(0x2682) + "   = Up/Down     "
                 + chr(0x2683) + "  = Save & Exit")


CMDLINE_PATH = "/boot/firmware/cmdline.txt"
TV_NORM_PREFIX = "vc4.tv_norm="

def get_tv_norm():
    # Extract the current tv_norm value from cmdline.txt.
    try:
        with open(CMDLINE_PATH, "r") as f:
            match = re.search(rf"{TV_NORM_PREFIX}(\S+)", f.read())
            if match:
                return match.group(1)  # Return value after vc4.tv_norm=
    except FileNotFoundError:
        pass
    return "NTSC"  # Default if not found (though we assume it's always there)

def set_tv_norm(mode):
    # Replace the existing vc4.tv_norm= value with a new mode in cmdline.txt.
    # /boot/firmware is mounted read-only by default, so we need to remount it
    try:
        # Remount /boot/firmware as read-write
        print("Remounting /boot/firmware as read-write...")
        subprocess.run(
            ["sudo", "mount", "/boot/firmware", "-o", "remount,rw"],
            check=True
        )
        
        # Make the change
        print(f"Setting TV norm to {mode}...")
        subprocess.run(
            f"sudo sed -i 's/{TV_NORM_PREFIX}\\S\\+/{TV_NORM_PREFIX}{mode}/' {CMDLINE_PATH}",
            shell=True, check=True
        )
        
        # Remount /boot/firmware as read-only
        print("Remounting /boot/firmware as read-only...")
        subprocess.run(
            ["sudo", "mount", "/boot/firmware", "-o", "remount,ro"],
            check=True
        )
        
        print(f"Successfully set TV norm to {mode}")
        
    except subprocess.CalledProcessError as e:
        print(f"Error modifying {CMDLINE_PATH}: {e}")
        # Try to remount as read-only even if there was an error
        try:
            subprocess.run(
                ["sudo", "mount", "/boot/firmware", "-o", "remount,ro"],
                check=True
            )
        except:
            pass


class ScreenVideoSettings(Screen):
    def __init__(self, eyesy):
        super().__init__(eyesy)
        self.state = "idle"
        self.title = "Video Settings"
        self.footer = FOOTER_PLAIN
        self.new_video_res = 0

        # key press timers for repeats while adjusting a value
        self.key4_td = 0
        self.key5_td = 0

        self.menu = WidgetMenu(eyesy, [
            MenuItem('HDMI Resolution  ▶', self.select_res),
            MenuItem('Composite Video Settings  ▶', self.select_compvid),
            MenuItem('Live Video Stream  ▶', self.select_stream),
            MenuItem('◀  Exit', self.goto_home)
        ])
        self.menu.off_y = 43

        # adjusted with the mode keys and confirmed with save, same as the
        # MIDI settings screen. Nothing is applied until save, so holding a
        # key down does not restart the encoder on every repeat.
        self.menu_stream = WidgetMenu(eyesy, [
            self.create_stream_item("stream_enabled", 0, 1),
            self.create_stream_item("stream_width", 0, len(streamer.WIDTHS) - 1),
            self.create_stream_item("stream_fps", 0, len(STREAM_RATES) - 1),
            self.create_stream_item("stream_smooth", 0, 1),
            MenuItem('◀  Exit', self.goto_home)
        ])
        self.menu_stream.off_y = 75
        
        self.menu_select_res = WidgetMenu(
            eyesy,
            [MenuItem(res["name"], self.select_res_callback(i)) for i, res in enumerate(self.eyesy.RESOLUTIONS)] 
            + [MenuItem('◀  Exit', self.goto_home)]
        )
        
        self.menu_select_res.off_y = 75
        
        self.menu_select_compvid = WidgetMenu(
            eyesy,
            [MenuItem(res, self.select_compvid_callback(res)) for i, res in enumerate(self.eyesy.COMPVIDS)] 
            + [MenuItem('◀  Exit', self.goto_home)]
        )
        
        self.menu_select_compvid.off_y = 75
        self.menu_select_compvid.visible_items  = 12
         
        self.menu_confirm_res = WidgetMenu(eyesy, [
            MenuItem('Yes', self.confirm_res),
            MenuItem('◀  Cancel', self.goto_home)
        ])
        self.menu_confirm_res.off_y = 75
        
        self.current_compvid = ""

    def before(self):
        self.eyesy.ip = helpers.get_ip()
        self.menu_select_res.set_selected_index(self.eyesy.config["video_resolution"])
        self.menu_select_compvid.set_selected_index(len(self.menu_select_compvid.items) - 1)
        self.menu_confirm_res.set_selected_index(1)
        self.current_compvid = get_tv_norm()
        self.state = "idle"
        self.footer = FOOTER_PLAIN

    def after(self):
        pass

    def handle_events(self):
        if self.state == "idle":
            self.menu.handle_events()
        elif self.state == "select_res":
            self.menu_select_res.handle_events()
        elif self.state == "select_compvid":
            self.menu_select_compvid.handle_events()
        elif self.state == "confirm_res":
            self.menu_confirm_res.handle_events()
        elif self.state == "stream":
            self.menu_stream.handle_events()
            item = self.menu_stream.items[self.menu_stream.selected_index]
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

    def render(self, surface):

        msg_xy = (32, 68)
        font = self.menu.font
        color = (200, 200, 200)
        if self.state == "idle":
            self.menu.render(surface)
        elif self.state == "select_res" :
            reso = self.eyesy.RESOLUTIONS[self.eyesy.config["video_resolution"]]["name"]
            message = f"Select resolution for HDMI. Currently {reso} "
            rendered_text = font.render(message, True, color)
            surface.blit(rendered_text, msg_xy)
            self.menu_select_res.render(surface)
        elif self.state == "select_compvid" :
            message = f"Select composite video format. Currently {self.current_compvid}"
            rendered_text = font.render(message, True, color)
            surface.blit(rendered_text, msg_xy)
            self.menu_select_compvid.render(surface)
        elif self.state == "confirm_res" :
            message = "New screen resolution selected, restart video?"
            rendered_text = font.render(message, True, color)
            surface.blit(rendered_text, msg_xy)
            self.menu_confirm_res.render(surface)
        elif self.state == "stream" :
            message = f"Watch at  http://{self.eyesy.ip or 'eyesy.local'}/live"
            rendered_text = font.render(message, True, color)
            surface.blit(rendered_text, msg_xy)
            self.menu_stream.render(surface)

    def select_res_callback(self, res):
        def callback():
            if res != self.eyesy.config["video_resolution"] :
                self.new_video_res = res
                self.state = "confirm_res"
        return callback

    def select_compvid_callback(self, compvid):
        def callback():
            print(f"setting compvid {compvid}")
            set_tv_norm(compvid)
            self.current_compvid = compvid
        return callback

    def confirm_res(self):
        self.eyesy.config["video_resolution"] = self.new_video_res
        self.eyesy.save_config_file()
        self.eyesy.restart = True

    def select_res(self):
        self.state = "select_res"

    def select_stream(self):
        self.state = "stream"
        self.footer = FOOTER_ADJUST
        self.load_stream_values()

    def create_stream_item(self, name, minv, maxv):
        item = MenuItem("", self.save_stream)
        item.adjustable = True
        item.name = name
        item.min_value = minv
        item.max_value = maxv
        item.value = minv
        return item

    def stream_item(self, name):
        for item in self.menu_stream.items:
            if item.name == name:
                return item
        return None

    def text_for_stream_item(self, item):
        if item.name == "stream_enabled":
            item.text = f"Stream: {'On' if item.value else 'Off'}"
        elif item.name == "stream_width":
            item.text = f"Size: {streamer.WIDTHS[item.value]} wide"
        elif item.name == "stream_fps":
            item.text = f"Frame Rate: {STREAM_RATES[item.value]} fps"
        elif item.name == "stream_smooth":
            item.text = f"Smoothing: {'On' if item.value else 'Off'}"

    def _index_of(self, choices, value, fallback=0):
        try:
            return choices.index(value)
        except ValueError:
            return fallback

    def load_stream_values(self):
        c = self.eyesy.config
        self.stream_item("stream_enabled").value = 1 if c["stream_enabled"] else 0
        self.stream_item("stream_width").value = \
            self._index_of(streamer.WIDTHS, c["stream_width"])
        self.stream_item("stream_fps").value = \
            self._index_of(STREAM_RATES, c["stream_fps"])
        self.stream_item("stream_smooth").value = 1 if c["stream_smooth"] else 0
        for item in self.menu_stream.items:
            if item.adjustable:
                self.text_for_stream_item(item)

    def save_stream(self):
        c = self.eyesy.config
        c["stream_enabled"] = bool(self.stream_item("stream_enabled").value)
        c["stream_width"] = streamer.WIDTHS[self.stream_item("stream_width").value]
        c["stream_fps"] = STREAM_RATES[self.stream_item("stream_fps").value]
        c["stream_smooth"] = bool(self.stream_item("stream_smooth").value)
        self.eyesy.save_config_file()
        streamer.apply(self.eyesy)
        self.goto_home()

    def menu_dec_value(self, item):
        item.value = max(item.value - item.value_delta, item.min_value)
        self.text_for_stream_item(item)

    def menu_inc_value(self, item):
        item.value = min(item.value + item.value_delta, item.max_value)
        self.text_for_stream_item(item)

    def select_compvid(self):
        self.state = "select_compvid"

    def goto_home(self):
        self.eyesy.switch_menu_screen("home")
