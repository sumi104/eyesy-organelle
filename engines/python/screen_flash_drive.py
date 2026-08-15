import threading
import subprocess
import os
import shutil
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

class ScreenFlashDrive(Screen):
    def __init__(self, eyesy):
        super().__init__(eyesy)
        self.state = "idle"  # "idle" or "running"
        self.title = "System Stuff"
        self.footer = FOOTER_PLAIN

        items = [
            MenuItem('Backup SD card to USB drive', self.start_backup),
            MenuItem('Eject USB drive', self.eject),
            MenuItem('Forget all WiFi networks', self.forgetnets),
            MenuItem('Restart Video', self.restart),
            MenuItem('◀  Exit', self.goto_home)
        ]

        # the pedal jack is only wired up on the organelle
        self.footswitch_item = None
        if organelle.is_organelle():
            self.footswitch_item = MenuItem("", self.save_footswitch)
            self.footswitch_item.adjustable = True
            self.footswitch_item.name = "footswitch"
            self.footswitch_item.min_value = 0
            self.footswitch_item.max_value = len(eyesy.FOOTSWITCH_ACTIONS) - 1
            items.insert(0, self.footswitch_item)

        self.menu = WidgetMenu(eyesy, items)
        self.menu.off_y = 43
        self.font = pygame.font.Font("font.ttf", 16)
        self.font_small = pygame.font.Font("font.ttf", 12)
        self.logs = []

        # key press timers for repeats while adjusting a value
        self.key4_td = 0
        self.key5_td = 0

    def before(self):
        # by index the menu would land somewhere else as soon as a row is
        # added or removed, and Exit is the one that has to stay under the
        # cursor so nothing here goes off by accident
        self.menu.selected_index = len(self.menu.items) - 1
        self.logs = []
        if self.footswitch_item is not None:
            self.footswitch_item.value = self.eyesy.config["footswitch"]
            self.relabel_footswitch()
        self.ensure_usb_mounted()

    def after(self):
        pass

    def relabel_footswitch(self):
        action = self.eyesy.FOOTSWITCH_ACTIONS[self.footswitch_item.value]
        self.footswitch_item.text = f"Foot Switch: {action}"

    def menu_dec_value(self, item):
        item.value = max(item.value - item.value_delta, item.min_value)
        self.relabel_footswitch()

    def menu_inc_value(self, item):
        item.value = min(item.value + item.value_delta, item.max_value)
        self.relabel_footswitch()

    def trigger_held(self):
        """The pedal or the B key is down right now.

        Both drive the same trigger, and the pedal latches which of its two
        jobs it has when it goes down. Letting the setting move underneath a
        press that is already in flight is how the test tone gets stranded on,
        so the row stops responding until whatever is held is let go.
        """
        return bool(self.eyesy.key10_status or self.eyesy.footswitch_status)

    def footswitch_blocked(self):
        """True when the row is under the cursor and cannot be moved."""
        if self.footswitch_item is None:
            return False
        selected = self.menu.items[self.menu.selected_index]
        return selected is self.footswitch_item and self.trigger_held()

    def save_footswitch(self):
        if self.trigger_held():
            return
        self.eyesy.config["footswitch"] = self.footswitch_item.value
        self.eyesy.save_config_file()

    def handle_events(self):
        if self.state != "idle":
            return

        self.menu.handle_events()

        item = self.menu.items[self.menu.selected_index]
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

        #msg_xy = (32, 68)
        #color = (200, 200, 200)
        #message = "Backup Modes, Scenes, Settings, and Screen Grabs?"
        #rendered_text = self.font.render(message, True, color)
        #surface.blit(rendered_text, msg_xy)
        self.menu.render(surface)

        line_height = self.font_small.get_linesize()
        top = self.log_top()

        # say why the row is not moving rather than looking broken
        if self.footswitch_blocked():
            notice = self.font_small.render(BLOCKED_MESSAGE, True, (255, 200, 80))
            surface.blit(notice, (32, top))
            top += line_height

        for i, log in enumerate(self.logs[-10:]):  # Show last 10 log entries
            text_surface = self.font_small.render(log, True, (200, 200, 200))  # White text
            surface.blit(text_surface, (32, top + i * line_height))

    def log_top(self):
        """First log line, kept below the last menu row.

        This used to be a fixed 200, which the pedal row pushed Exit into.
        Measuring the menu instead means another row can be added without
        landing on top of whatever the backup is saying.
        """
        rows = min(len(self.menu.items), self.menu.visible_items)
        # the row geometry WidgetMenu.render() lays out, plus a gap
        return 30 + self.menu.off_y + rows * 25 + 8

    def restart(self):
        self.eyesy.restart = True
 
    def eject(self):
        self.logs = []  # Clear previous logs
        self.log("Ejecting USB drive...")
        subprocess.run(["sudo", "umount", "/usbdrive"])
        self.log("Safe to remove.")
 
    def forgetnets(self):
        self.logs = []  # Clear previous logs
        self.log("Removing stored WiFi networks...")
        subprocess.run("sudo bash -c 'rm /sdcard/system-connections/*'", shell=True)
        self.log("Removed WiFi networks.")

    def log(self, message):
        """Append a message to logs and trigger a screen update."""
        self.logs.append(message)

    def start_backup(self):
        """Start the backup process in a separate thread."""
        if self.state == "running":
            return  # Prevent multiple backups from running at once

        self.logs = []  # Clear previous logs
        self.state = "running"
        self.log("Starting backup...")

        backup_thread = threading.Thread(target=self.backup, daemon=True)
        backup_thread.start()

    def backup(self):
        """Performs the backup process in a separate thread."""
        if not self.ensure_usb_mounted():
            self.log("USB drive not found or failed to mount.")
            self.state = "idle"
            return

        backup_folder = self.create_backup_folder()
        if not backup_folder:
            self.log("Failed to create backup folder.")
            self.state = "idle"
            return

        self.copy_directories(backup_folder)

        self.log("Syncing drive...")
        subprocess.run(["sync"])

        #self.log("Unmounting drive...")
        #subprocess.run(["sudo", "umount", "/usbdrive"])

        self.log("Backup complete.")
        self.state = "idle"

    def ensure_usb_mounted(self):
        """Ensure the USB drive is mounted."""
        usb_device = self.get_usb_device()
        if not usb_device:
            self.log("No USB device found.")
            return False

        if not os.path.exists("/usbdrive"):
            self.log("mount point /usbdrive not found on system")
            return False

        if "/usbdrive" in subprocess.getoutput("mount"):
            self.log("USB mounted mounted.")
            if self.eyesy.running_from_usb : self.log("EYESY running patches from USB")
            return True

        result = subprocess.run(["sudo", "mount", "-o", "uid=1000,gid=1000", usb_device, "/usbdrive"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            self.log(f"Mounted {usb_device} at /usbdrive.")
            return True
        else:
            self.log(f"Mount failed: {result.stderr}")
            return False

    def get_usb_device(self):
        """Find the first USB storage device."""
        devices = subprocess.getoutput("lsblk -o KNAME,TYPE | grep 'disk' | awk '{print $1}'").splitlines()
        for dev in devices:
            if "sd" in dev:  # Typical USB storage devices start with "sd"
                return f"/dev/{dev}1"  # Assuming first partition
        return None

    def create_backup_folder(self):
        """Create the next numbered backup folder."""
        backup_path = "/usbdrive/backups"
        if not os.path.exists(backup_path):
            self.log(f"Creating folder for backups")
            try:
                os.makedirs(backup_path)
                return backup_folder
            except Exception as e:
                self.log(f"Error creating backup folder: {e}")
                return None

        existing_folders = [
            int(f) for f in os.listdir(backup_path)
            if f.isdigit() and len(f) == 4
        ]
        next_number = max(existing_folders, default=0) + 1
        backup_folder = os.path.join(backup_path, f"{next_number:04d}")

        try:
            os.makedirs(backup_folder)
            self.log(f"Created backup folder: {backup_folder}")
            return backup_folder
        except Exception as e:
            self.log(f"Error creating backup folder: {e}")
            return None

    def copy_directories(self, dest_folder):
        """Copy the four directories to the backup folder."""
        paths = {
            "Grabs": "/sdcard/Grabs/",
            "Modes": "/sdcard/Modes/",
            "Scenes": "/sdcard/Scenes/",
            "System": "/sdcard/System/"
        }

        for name, src in paths.items():
            self.log(f"Copying {name} to backup...")
            if os.path.exists(src):
                dest = os.path.join(dest_folder, name)
                try:
                    shutil.copytree(src, dest)
                    self.log(f"Copied {name} to backup.")
                except Exception as e:
                    self.log(f"Error copying {name}: {e}")
            else:
                self.log(f"Skipping {name}, does not exist.")

    def goto_home(self):
        self.eyesy.switch_menu_screen("home")

