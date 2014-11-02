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

import cmd
import glob
import os
import time
import sys
import subprocess
import codecs
import argparse
import locale
import logging
import traceback

from . import printcore
from printrun.printrun_utils import install_locale, run_command, \
    format_time, format_duration, RemainingTimeEstimator, \
    get_home_pos, parse_build_dimensions
install_locale('pronterface')
from printrun import gcoder

from functools import wraps

READLINE = True
try:
    import readline
    try:
        readline.rl.mode.show_all_if_ambiguous = "on"  # config pyreadline on windows
    except:
        pass
except:
    READLINE = False  # neither readline module is available

def dosify(name):
    return os.path.split(name)[1].split(".")[0][:8] + ".g"

def setting_add_tooltip(func):
    @wraps(func)
    def decorator(self, *args, **kwargs):
        widget = func(self, *args, **kwargs)
        helptxt = self.help or ""
        sep, deftxt = "", ""
        if len(helptxt):
            sep = "\n"
            if helptxt.find("\n") >= 0:
                sep = "\n\n"
        if self.default is not "":
            deftxt = _("Default: ")
            resethelp = _("(Control-doubleclick to reset to default value)")
            if len(repr(self.default)) > 10:
                deftxt += "\n    " + repr(self.default).strip("'") + "\n" + resethelp
            else:
                deftxt += repr(self.default) + "  " + resethelp
        helptxt += sep + deftxt
        if len(helptxt):
            widget.SetToolTipString(helptxt)
        return widget
    return decorator

class Setting(object):

    DEFAULT_GROUP = "Printer"

    hidden = False

    def __init__(self, name, default, label = None, help = None, group = None):
        self.name = name
        self.default = default
        self._value = default
        self.label = label
        self.help = help
        self.group = group if group else Setting.DEFAULT_GROUP

    def _get_value(self):
        return self._value

    def _set_value(self, value):
        raise NotImplementedError
    value = property(_get_value, _set_value)

    def set_default(self, e):
        import wx
        if e.CmdDown() and e.ButtonDClick() and self.default is not "":
            confirmation = wx.MessageDialog(None, _("Are you sure you want to reset the setting to the default value: {0!r} ?").format(self.default), _("Confirm set default"), wx.ICON_EXCLAMATION | wx.YES_NO | wx.NO_DEFAULT)
            if confirmation.ShowModal() == wx.ID_YES:
                self._set_value(self.default)
        else:
            e.Skip()

    @setting_add_tooltip
    def get_label(self, parent):
        import wx
        widget = wx.StaticText(parent, -1, self.label or self.name)
        widget.set_default = self.set_default
        return widget

    @setting_add_tooltip
    def get_widget(self, parent):
        return self.get_specific_widget(parent)

    def get_specific_widget(self, parent):
        raise NotImplementedError

    def update(self):
        raise NotImplementedError

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name

class HiddenSetting(Setting):

    hidden = True

    def _set_value(self, value):
        self._value = value
    value = property(Setting._get_value, _set_value)


class Settings(object):
    def _baudrate_list(self): return ["2400", "9600", "19200", "38400", "57600", "115200", "250000"]

    def __init__(self):
        self._add(HiddenSetting("port",""))
        self._add(HiddenSetting("baudrate", 115200))
        self._add(HiddenSetting("project_tiempo_exposicion", 2.0))
        self._add(HiddenSetting("project_pausa", 2.5))
        self._add(HiddenSetting("project_x", 1024))
        self._add(HiddenSetting("project_y", 768))
        self._add(HiddenSetting("project_x_proyectada", 150.0))
        self._add(HiddenSetting("project_elevacion", 3.0))
        self._add(HiddenSetting("project_velocidad_z", 200))
        self._add(HiddenSetting("project_primera_capa", 20))
        self._add(HiddenSetting("pause_between_prints", True))
        self._add(HiddenSetting("default_extrusion", 5.0))
        self._add(HiddenSetting("last_extrusion", 5.0))

    _settings = []

    def __setattr__(self, name, value):
        if name.startswith("_"):
            return object.__setattr__(self, name, value)
        if isinstance(value, Setting):
            if not value.hidden:
                self._settings.append(value)
            object.__setattr__(self, "_" + name, value)
        elif hasattr(self, "_" + name):
            getattr(self, "_" + name).value = value
        else:
            setattr(self, name, StringSetting(name = name, default = value))

    def __getattr__(self, name):
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        return getattr(self, "_" + name).value

    def _add(self, setting, callback = None):
        setattr(self, setting.name, setting)
        if callback:
            setattr(self, "_" + setting.name + "_cb", callback)

    def _set(self, key, value):
        try:
            value = getattr(self, "_%s_alias" % key)()[value]
        except KeyError:
            pass
        except AttributeError:
            pass
        try:
            getattr(self, "_%s_validate" % key)(value)
        except AttributeError:
            pass
        t = type(getattr(self, key))
        if t == bool and value == "False": setattr(self, key, False)
        else: setattr(self, key, t(value))
        try:
            cb = None
            try:
                cb = getattr(self, "_%s_cb" % key)
            except AttributeError:
                pass
            if cb is not None: cb(key, value)
        except:
            logging.warning((_("Failed to run callback after setting \"%s\":") % key) +
                            "\n" + traceback.format_exc())
        return value

    def _all_settings(self):
        return self._settings

class pronsole(cmd.Cmd):
    def __init__(self):
        cmd.Cmd.__init__(self)
        if not READLINE:
            self.completekey = None
        self.p = printcore.printcore()
        self.p.onlinecb = self.online
        self.p.errorcb = self.logError
        self.listing = 0
        self.paused = False
        self.tempreadings = ""
        self.rc_loaded = False
        self.processing_rc = False
        self.processing_args = False
        self.settings = Settings()
        self.settings._port_list = self.scanserial
        self.monitoring = 0
        self.starttime = 0
        self.extra_print_time = 0
        self.silent = False
        self.commandprefixes = 'MGT$'

    def confirm(self):
        y_or_n = raw_input("y/n: ")
        if y_or_n == "y":
            return True
        elif y_or_n != "n":
            return self.confirm()
        return False

    def log(self, *msg):
        print u"".join(unicode(i) for i in msg)

    def logError(self, *msg):
        msg = u"".join(unicode(i) for i in msg)
        logging.error(msg)
        if not self.settings.error_command:
            return
        run_command(self.settings.error_command,
                    {"$m": msg},
                    stderr = subprocess.STDOUT, stdout = subprocess.PIPE,
                    blocking = False)

    def scanserial(self):
        """scan for available ports. return a list of device names."""
        baselist = []
        if os.name == "nt":
            try:
                key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, "HARDWARE\\DEVICEMAP\\SERIALCOMM")
                i = 0
                while(1):
                    baselist += [_winreg.EnumValue(key, i)[1]]
                    i += 1
            except:
                pass

        for g in ['/dev/ttyUSB*', '/dev/ttyACM*', "/dev/tty.*", "/dev/cu.*", "/dev/rfcomm*"]:
            baselist += glob.glob(g)
        return filter(self._bluetoothSerialFilter, baselist)

    def online(self):
        self.log("\rPrinter is now online")
        self.write_prompt()

    def write_prompt(self):
        sys.stdout.write(self.promptf())
        sys.stdout.flush()

    def help_help(self, l = ""):
        self.do_help("")

    def do_gcodes(self, l = ""):
        self.help_gcodes()

    def help_gcodes(self):
        self.log("Gcodes are passed through to the printer as they are")

    def parseusercmd(self, line):
        pass

    def set(self, var, str):
        try:
            t = type(getattr(self.settings, var))
            value = self.settings._set(var, str)
            if not self.processing_rc and not self.processing_args:
                self.save_in_rc("set " + var, "set %s %s" % (var, value))
        except AttributeError:
            logging.warning("Unknown variable '%s'" % var)
        except ValueError, ve:
            self.logError("Bad value for variable '%s', expecting %s (%s)" % (var, repr(t)[1:-1], ve.args[0]))

    def do_set(self, argl):
        args = argl.split(None, 1)
        if len(args) < 1:
            for k in [kk for kk in dir(self.settings) if not kk.startswith("_")]:
                self.log("%s = %s" % (k, str(getattr(self.settings, k))))
            return
        if len(args) < 2:
            try:
                self.log("%s = %s" % (args[0], getattr(self.settings, args[0])))
            except AttributeError:
                logging.warning("Unknown variable '%s'" % args[0])
            return
        self.set(args[0], args[1])

    def postloop(self):
        self.p.disconnect()
        cmd.Cmd.postloop(self)

    def load_rc(self, rc_filename):
        self.processing_rc = True
        try:
            rc = codecs.open(rc_filename, "r", "utf-8")
            self.rc_filename = os.path.abspath(rc_filename)
            for rc_cmd in rc:
                if not rc_cmd.lstrip().startswith("#"):
                    self.onecmd(rc_cmd)
            rc.close()
            if hasattr(self, "cur_macro_def"):
                self.end_macro()
            self.rc_loaded = True
        finally:
            self.processing_rc = False

    def load_default_rc(self, rc_filename = ".pronsolerc"):
        if rc_filename == ".pronsolerc" and hasattr(sys, "frozen") and sys.frozen in ["windows_exe", "console_exe"]:
            rc_filename = "printrunconf.ini"
        try:
            try:
                self.load_rc(os.path.join(os.path.expanduser("~"), rc_filename))
            except IOError:
                self.load_rc(rc_filename)
        except IOError:
            # make sure the filename is initialized
            self.rc_filename = os.path.abspath(os.path.join(os.path.expanduser("~"), rc_filename))

    def save_in_rc(self, key, definition):
        """
        Saves or updates macro or other definitions in .pronsolerc
        key is prefix that determines what is being defined/updated (e.g. 'macro foo')
        definition is the full definition (that is written to file). (e.g. 'macro foo move x 10')
        Set key as empty string to just add (and not overwrite)
        Set definition as empty string to remove it from .pronsolerc
        To delete line from .pronsolerc, set key as the line contents, and definition as empty string
        Only first definition with given key is overwritten.
        Updates are made in the same file position.
        Additions are made to the end of the file.
        """
        rci, rco = None, None
        if definition != "" and not definition.endswith("\n"):
            definition += "\n"
        try:
            written = False
            if os.path.exists(self.rc_filename):
                import shutil
                shutil.copy(self.rc_filename, self.rc_filename + "~bak")
                rci = codecs.open(self.rc_filename + "~bak", "r", "utf-8")
            rco = codecs.open(self.rc_filename, "w", "utf-8")
            if rci is not None:
                overwriting = False
                for rc_cmd in rci:
                    l = rc_cmd.rstrip()
                    ls = l.lstrip()
                    ws = l[:len(l) - len(ls)]  # just leading whitespace
                    if overwriting and len(ws) == 0:
                        overwriting = False
                    if not written and key != "" and rc_cmd.startswith(key) and (rc_cmd + "\n")[len(key)].isspace():
                        overwriting = True
                        written = True
                        rco.write(definition)
                    if not overwriting:
                        rco.write(rc_cmd)
                        if not rc_cmd.endswith("\n"): rco.write("\n")
            if not written:
                rco.write(definition)
            if rci is not None:
                rci.close()
            rco.close()
            #if definition != "":
            #    self.log("Saved '"+key+"' to '"+self.rc_filename+"'")
            #else:
            #    self.log("Removed '"+key+"' from '"+self.rc_filename+"'")
        except Exception, e:
            # Error ignored, setup file not editable
            #self.logError("Saving failed for ", key + ":", str(e))
            pass
        finally:
            del rci, rco

    def preloop(self):
        self.log("Welcome to the printer console! Type \"help\" for a list of available commands.")
        self.prompt = self.promptf()
        cmd.Cmd.preloop(self)

    def do_connect(self, l):
        a = l.split()
        p = self.scanserial()
        port = self.settings.port
        if (port == "" or port not in p) and len(p) > 0:
            port = p[0]
        baud = self.settings.baudrate or 115200
        if len(a) > 0:
            port = a[0]
        if len(a) > 1:
            try:
                baud = int(a[1])
            except:
                self.log("Bad baud value '" + a[1] + "' ignored")
        if len(p) == 0 and not port:
            self.log("No serial ports detected - please specify a port")
            return
        if len(a) == 0:
            self.log("No port specified - connecting to %s at %dbps" % (port, baud))
        if port != self.settings.port:
            self.settings.port = port
            self.save_in_rc("set port", "set port %s" % port)
        if baud != self.settings.baudrate:
            self.settings.baudrate = baud
            self.save_in_rc("set baudrate", "set baudrate %d" % baud)
        self.p.connect(port, baud)

    def complete_connect(self, text, line, begidx, endidx):
        if (len(line.split()) == 2 and line[-1] != " ") or (len(line.split()) == 1 and line[-1] == " "):
            return [i for i in self.scanserial() if i.startswith(text)]
        elif(len(line.split()) == 3 or (len(line.split()) == 2 and line[-1] == " ")):
            return [i for i in ["2400", "9600", "19200", "38400", "57600", "115200"] if i.startswith(text)]
        else:
            return []

    def do_disconnect(self, l):
        self.p.disconnect()

    def emptyline(self):
        pass

    def do_shell(self, l):
        exec(l)

    def do_reset(self, l):
        self.p.reset()

    def default(self, l):
        if l[0] in self.commandprefixes.upper():
            if self.p and self.p.online:
                if not self.p.loud:
                    self.log("SENDING:" + l)
                self.p.send_now(l)
            else:
                self.logError(_("Printer is not online."))
            return
        elif l[0] in self.commandprefixes.lower():
            if self.p and self.p.online:
                if not self.p.loud:
                    self.log("SENDING:" + l.upper())
                self.p.send_now(l.upper())
            else:
                self.logError(_("Printer is not online."))
            return
        elif l[0] == "@":
            if self.p and self.p.online:
                if not self.p.loud:
                    self.log("SENDING:" + l[1:])
                self.p.send_now(l[1:])
            else:
                self.logError(_("Printer is not online."))
            return
        else:
            cmd.Cmd.default(self, l)

    def do_exit(self, l):
        self.log("Disconnecting from printer...")
        if self.p.printing:
            print "Are you sure you want to exit while printing?"
            print "(this will terminate the print)."
            if not self.confirm():
                return
        self.log(_("Exiting program. Goodbye!"))
        self.p.disconnect()
        sys.exit()

    def expandcommand(self, c):
        return c.replace("$python", sys.executable)

    def add_cmdline_arguments(self, parser):
        parser.add_argument('-c', '--conf', '--config', help = _("load this file on startup instead of .pronsolerc ; you may chain config files, if so settings auto-save will use the last specified file"), action = "append", default = [])
        parser.add_argument('-e', '--execute', help = _("executes command after configuration/.pronsolerc is loaded ; macros/settings from these commands are not autosaved"), action = "append", default = [])
        parser.add_argument('filename', nargs='?', help = _("file to load"))

    def process_cmdline_arguments(self, args):
        for config in args.conf:
            self.load_rc(config)
        if not self.rc_loaded:
            self.load_default_rc()
        self.processing_args = True
        for command in args.execute:
            self.onecmd(command)
        self.processing_args = False
        if args.filename:
            filename = args.filename.decode(locale.getpreferredencoding())
            self.cmdline_filename_callback(filename)

    def cmdline_filename_callback(self, filename):
        self.do_load(filename)

    def parse_cmdline(self, args):
        parser = argparse.ArgumentParser(description = 'Printrun 3D printer interface')
        self.add_cmdline_arguments(parser)
        args = [arg for arg in args if not arg.startswith("-psn")]
        args = parser.parse_args(args = args)
        self.process_cmdline_arguments(args)
