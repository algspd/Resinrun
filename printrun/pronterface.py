#!/usr/bin/env python

# This file is part of the Printrun suite.
#
# Printrun is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Printrun is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Printrun.  If not, see <http://www.gnu.org/licenses/>.

import os
import Queue
import re
import sys
import time
import threading
import traceback
import cStringIO as StringIO
import subprocess
import shlex
import glob
import logging

try: import simplejson as json
except ImportError: import json

from . import pronsole
from . import printcore

from printrun.printrun_utils import install_locale, setup_logging
install_locale('pronterface')

try:
    import wx
except:
    logging.error(_("WX is not installed. This program requires WX to run."))
    raise

from serial import SerialException

winsize = (800, 500)
layerindex = 0

from printrun.printrun_utils import iconfile, configfile, format_time, format_duration
from printrun import gcoder

class MainWindow(wx.Frame):
    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

class PronterWindow(MainWindow,pronsole.pronsole):

    def __init__(self, app, filename = None, size = winsize):
        pronsole.pronsole.__init__(self)
        self.app = app
        self.monitor_interval = 3

        # configs to restore the size, but this might have some unforeseen
        # consequences.
        os.putenv("UBUNTU_MENUPROXY", "0")
        size = (1,1)
        MainWindow.__init__(self, None, title = _("Pronterface"), size = size)


        self.parse_cmdline(sys.argv[1:])

        #make printcore aware of me
        self.p.pronterface = self

        self.stdout = sys.stdout
        self.connect()

    def online(self):
        print ("Printer is now online.")

    def project(self, event):
        from printrun import projectlayer
        projectlayer.SettingsFrame(self, self.p).Show()

    def project_init(self):
	from printrun import projectlayer
        # Show only projected part, not settings
        projector=projectlayer.SettingsFrame(self, self.p)
        projector.update_fullscreen2()
        return projector

    def project_calibrate(self,projector):
        projector.present_calibrate2()

    def OnExit(self, event):
        self.Close()

    def rescanports(self, event = None):
        scanned = self.scanserial()
        portslist = list(scanned)
        if self.settings.port != "" and self.settings.port not in portslist:
            portslist.append(self.settings.port)
            self.serialport.Clear()
            self.serialport.AppendItems(portslist)
        if os.path.exists(self.settings.port) or self.settings.port in scanned:
            self.serialport.SetValue(self.settings.port)
        elif portslist:
            self.serialport.SetValue(portslist[0])

    def stop(self):
        self.disconnect()
        self.connect()
        
    def wait_printer_available(self):
        while (True):
            time.sleep(0.5)
            self.p.send_now("G0")
            try:
                l = self.p._readline()
                if (l.startswith('ok')):
                  return
            except:
                pass
        
    def statuschecker(self):
        while self.statuscheck:
            string = ""
            fractioncomplete = 0.0
            if self.p.queueindex > 0:
                pass
            if self.p.online:
                if self.p.writefailures >= 4:
                    self.logError(_("Disconnecting after 4 failed writes."))
                    self.status_thread = None
                    self.disconnect()
                    return
            time.sleep(self.monitor_interval)

    def connect(self, event = None):
        print _("Connecting...")
        port = None
        port="/dev/ttyACM0"
        baud = 115200
        if self.paused:
            self.p.paused = 0
            self.p.printing = 0
            self.paused = 0
        try:
            self.p.connect(port, baud)
        except SerialException as e:
            # Currently, there is no errno, but it should be there in the future
            if e.errno == 2:
                self.logError(_("Error: You are trying to connect to a non-existing port."))
            elif e.errno == 8:
                self.logError(_("Error: You don't have permission to open %s.") % port)
                self.logError(_("You might need to add yourself to the dialout group."))
            else:
                self.logError(traceback.format_exc())
            # Kill the scope anyway
            return
        except OSError as e:
            if e.errno == 2:
                self.logError(_("Error: You are trying to connect to a non-existing port."))
            else:
                self.logError(traceback.format_exc())
            return
        self.statuscheck = True
        if port != self.settings.port:
            self.set("port", port)
        if baud != self.settings.baudrate:
            self.set("baudrate", str(baud))
        self.status_thread = threading.Thread(target = self.statuschecker)
        self.status_thread.start()

    def disconnect(self, event = None):
        print _("Disconnected.")
        if self.p.printing or self.p.paused or self.paused:
            self.store_predisconnect_state()
        self.p.disconnect()
        self.statuscheck = False
        if self.status_thread:
            self.status_thread.join()
            self.status_thread = None

        if self.paused:
            self.p.paused = 0
            self.p.printing = 0
            self.paused = 0

    def reset(self, event):
        print _("Reset.")
        self.p.reset()
        self.p.printing = 0
        if self.paused:
            self.p.paused = 0
            self.paused = 0

class PronterApp(wx.App):

    mainwindow = None

    def startPrint(self,l):
        # Reload config
        self.mainwindow.load_default_rc()
        self.projector.reload_config()
        # Load part
        ret=self.projector.load_file_this("/root/part.svg")
        l.put_lines("Imprimiendo...",ret)
        self.projector.display_frame.go_home()
        self.mainwindow.wait_printer_available()
        self.projector.start_present2(l) 

    def stopPrint(self):
        # Stop printer
        self.projector.ended=True
        self.projector.stop_present2()

    def servo_close(self):
        self.projector.display_frame.servo_close()

    def __init__(self, *args, **kwargs):
        super(PronterApp, self).__init__(*args, **kwargs)
        # CUSTOM for arcadeprinter
        self.mainwindow = PronterWindow(self)
        self.projector=self.mainwindow.project_init()
        self.projector.display_frame.Show()



