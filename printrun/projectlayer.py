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

import xml.etree.ElementTree
import wx
import wx.lib.agw.floatspin as floatspin
import os
import sys
import time
import zipfile
import tempfile
import shutil
import cairosvg
import cairosvg.surface
from cairosvg.surface import PNGSurface
import cStringIO
import imghdr
import copy
import re
from collections import OrderedDict
import itertools
import math 

class DisplayFrame(wx.Frame):
    def __init__(self, parent, title, res=(1024, 768), printer=None, scale=1.0, offset=(0,0)):
        wx.Frame.__init__(self, parent=parent, title=title, size=res)
        self.printer = printer
        self.control_frame = parent
        self.pic = wx.StaticBitmap(self)
        self.bitmap = wx.EmptyBitmap(*res)
        self.bbitmap = wx.EmptyBitmap(*res)
        self.slicer = 'bitmap'
        self.dpi = 96
        dc = wx.MemoryDC()
        dc.SelectObject(self.bbitmap)
        dc.SetBackground(wx.Brush("black"))
        dc.Clear()
        dc.SelectObject(wx.NullBitmap)

        self.SetBackgroundColour("black")
        self.pic.Hide()
        self.SetDoubleBuffered(True)
        self.SetPosition((self.control_frame.GetSize().x, 0))
        
        self.scale = scale
        self.index = 0
        self.size = res
        self.offset = offset
        self.running = False
        self.layer_red = False

    def repos(self,x,y):
        self.SetPosition((x,y))

    def clear_layer(self):
        try:
            dc = wx.MemoryDC()
            dc.SelectObject(self.bitmap)
            dc.SetBackground(wx.Brush("black"))
            dc.Clear()
            self.pic.SetBitmap(self.bitmap)
            self.pic.Show()
            self.Refresh()
        except:
            raise
            pass
        
    def resize(self, res=(1024, 768)):
        self.bitmap = wx.EmptyBitmap(*res)
        self.bbitmap = wx.EmptyBitmap(*res)
        dc = wx.MemoryDC()
        dc.SelectObject(self.bbitmap)
        dc.SetBackground(wx.Brush("black"))
        dc.Clear()
        dc.SelectObject(wx.NullBitmap)
        
    def draw_layer(self, image):
        try:
            dc = wx.MemoryDC()
            dc.SelectObject(self.bitmap)
            dc.SetBackground(wx.Brush("black"))
            dc.Clear()

            if self.slicer == 'Slic3r' or self.slicer == 'Skeinforge':
                
                if self.scale != 1.0:
                    layercopy = copy.deepcopy(image)
                    height = float(layercopy.get('height').replace('m',''))
                    width = float(layercopy.get('width').replace('m',''))
                    
                    layercopy.set('height', str(height*self.scale) + 'mm')
                    layercopy.set('width', str(width*self.scale) + 'mm')
                    layercopy.set('viewBox', '0 0 ' + str(width*self.scale) + ' ' + str(height*self.scale))

                    g = layercopy.find("{http://www.w3.org/2000/svg}g")
                    g.set('transform', 'scale('+str(self.scale)+')')
                    stream = cStringIO.StringIO(PNGSurface.convert(dpi=self.dpi, bytestring=xml.etree.ElementTree.tostring(layercopy)))
                else:
                    stream = cStringIO.StringIO(PNGSurface.convert(dpi=self.dpi, bytestring=xml.etree.ElementTree.tostring(image)))
                    pngImage = wx.ImageFromStream(stream)
                if self.layer_red:
                    pngImage = pngImage.AdjustChannels(1,0,0,1)
                dc.DrawBitmap(wx.BitmapFromImage(pngImage), self.offset[0], self.offset[1], True)

            elif self.slicer == 'bitmap':
                if isinstance(image, str):
                    image = wx.Image(image)
                if self.layer_red:
                    image = image.AdjustChannels(1,0,0,1)
                dc.DrawBitmap(wx.BitmapFromImage(image.Scale(image.Width * self.scale, image.Height * self.scale)), self.offset[0], -self.offset[1], True)

            else:
                raise Exception(self.slicer + " is an unknown method.")
            
            self.pic.SetBitmap(self.bitmap)
            self.pic.Show()
            self.Refresh()            
            
        except:
            raise
            pass
            
    def show_img_delay(self, image):
        if self.ended:
            return
        self.draw_layer(image)
        # Show first layer fl_time seconds long
        if (self.index==1):
            wx.FutureCall(2000 + 1000 * self.fl_time, self.hide_pic_and_rise)
            print "Primera capa a " + str(self.fl_time) + "."
            wx.FutureCall(2000 , self.servo_open)
        else:
            wx.FutureCall(1000 * self.interval, self.hide_pic_and_rise)

    def go_home(self):
    	self.printer.send_now("M210 Z160")
    	self.printer.send_now("G28")

    def go_top(self):
        self.printer.send_now("G90")
    	self.printer.send_now("M210 Z160")
    	self.printer.send_now("G0 Z200")

    def servo_open(self):
        self.printer.send_now("G93")
        
    def servo_close(self):
        self.printer.send_now("G94")
        
 
    def rise(self):
        if self.ended:
            return
        if self.printer != None and self.printer.online and not self.ended:
            self.printer.send_now("G91")
            
            if (not self.ended):
                if (self.index==1):
                    self.printer.send_now("G2 O%f L%f" % (self.overshoot*3,self.thickness,))
                else:
                    self.printer.send_now("G2 O%f L%f" % (self.overshoot,self.thickness,))
            self.printer.send_now("G90")
        else:
            time.sleep(self.pause)
        
        if (self.index==1):
            # primera capa
            wx.FutureCall(1000 * self.pause * 3, self.next_img)
        else:
            wx.FutureCall(1000 * self.pause, self.next_img)
        
    def hide_pic(self):
        self.pic.Hide()
        
    def hide_pic_and_rise(self):
        wx.CallAfter(self.hide_pic)
        wx.FutureCall(500, self.rise)

    def layer_counter(self):
        ns=len(str(len(self.layers)))-len(str(self.index))
        s="                "
        percent=str((self.index*100)/len(self.layers))
        # Mostrar en el lcd el tiempo que queda
        if (self.index == 1):
          timeS = (len(self.layers) - self.index)*(float(self.interval) + float(self.pause) + 0.5) + self.fl_time
        else:
          timeS = (len(self.layers) - self.index) * (float(self.interval) + float(self.pause) + 0.5)
        self.l.put_line1("Tiempo: " + time.strftime("%H:%M:%S",time.gmtime(timeS)))
        self.l.put_line2(s[:ns] + str(self.index) + "/" + str(len(self.layers)) + "  " + percent + "%")
                    
    def next_img(self):
        if not self.running:
            return
        if self.ended:
            return
        if self.index < len(self.layers):
            self.layer_counter()
            wx.CallAfter(self.show_img_delay, self.layers[self.index])
            self.index += 1
        else:
            # Last layer
            self.l.put_lines("    Impresion","   finalizada")
            print "End"
            self.go_top()
            self.ended=True
            self.servo_close()
            wx.CallAfter(self.pic.Hide)
            wx.CallAfter(self.Refresh)
            sys.exit()
        
    def present(self, 
                layers, 
                interval=0.5, 
                pause=0.2, 
                overshoot=0.0, 
                z_axis_rate=200, 
                thickness=0.4, 
                scale=1, 
                size=(1024, 768), 
                offset=(0, 0),
                layer_red=False):
        if self.ended:
            return
        wx.CallAfter(self.pic.Hide)
        wx.CallAfter(self.Refresh)
        self.layers = layers
        self.scale = scale
        self.thickness = thickness
        self.size = size
        self.interval = interval
        self.pause = pause
        self.overshoot = overshoot
        self.z_axis_rate = z_axis_rate
        self.layer_red = layer_red
        self.offset = offset
        self.index = 0
        self.running = True
        
        self.next_img()

class SettingsFrame(wx.Frame):
    
    def _set_setting(self, name, value):
        if self.pronterface:
            self.pronterface.set(name,value)
    
    def _get_setting(self,name, val):
        if self.pronterface:
            try:
                return getattr(self.pronterface.settings, name)
            except AttributeError, x:
                return val
        else: 
            return val
        
    def __init__(self, parent, printer=None):
        wx.Frame.__init__(self, parent, title="ProjectLayer Control",style=(wx.DEFAULT_FRAME_STYLE | wx.WS_EX_CONTEXTHELP))
        self.pronterface = parent
        self.display_frame = DisplayFrame(self, title="ProjectLayer Display", printer=printer)
        
        self.thickness      = "0.1"
        self.interval       = str(self._get_setting("project_tiempo_exposicion", "0.5"))
        self.pause          = str(self._get_setting("project_pausa", "0.5"))
        self.scale          = "1.0"
        self.overshoot      = float(self._get_setting('project_elevacion', 3.0))
        projectX            = int(math.floor(float(self._get_setting("project_x", 1920))))
        self.X              = str(projectX)
        projectY            = int(math.floor(float(self._get_setting("project_y", 1200))))
        self.Y              = str(projectY)
        self.projected_X_mm = self._get_setting("project_x_proyectada", 505.0)
        self.fl_time        = int(self._get_setting("project_primera_capa",20))
        self.z_axis_rate    = str(self._get_setting("project_velocidad_z", 200))
        
        self.layer_red = False

    def __del__(self):
        if hasattr(self, 'image_dir') and self.image_dir != '':
            shutil.rmtree(self.image_dir)
        if self.display_frame:
            self.display_frame.Destroy()

    def reload_config(self):
        self.interval       = str(self._get_setting("project_tiempo_exposicion", "0.5"))
        self.pause          = str(self._get_setting("project_pausa", "0.5"))
        self.overshoot      = float(self._get_setting('project_elevacion', 3.0))
        projectX            = int(math.floor(float(self._get_setting("project_x", 1920))))
        self.X              = str(projectX)
        projectY            = int(math.floor(float(self._get_setting("project_y", 1200))))
        self.Y              = str(projectY)
        self.projected_X_mm = self._get_setting("project_x_proyectada", 505.0)
        self.fl_time        = int(self._get_setting("project_primera_capa",20))
        self.z_axis_rate    = str(self._get_setting("project_velocidad_z", 200))

    def parse_svg(self, name):
        et = xml.etree.ElementTree.ElementTree(file=name)
        #xml.etree.ElementTree.dump(et)
        
        slicer = 'Slic3r' if et.getroot().find('{http://www.w3.org/2000/svg}metadata') == None else 'Skeinforge'
        zlast = 0
        zdiff = 0
        ol = []
        height = et.getroot().get('height').replace('m','')
        width = et.getroot().get('width').replace('m','')

        # Save this data to center the part
        self.display_frame.part_h=height
        self.display_frame.part_w=width
            
        for i in et.findall("{http://www.w3.org/2000/svg}g"):
            z = float(i.get('{http://slic3r.org/namespaces/slic3r}z'))
            zdiff = z - zlast
            zlast = z

            svgSnippet = xml.etree.ElementTree.Element('{http://www.w3.org/2000/svg}svg')
            svgSnippet.set('height', height + 'mm')
            svgSnippet.set('width', width + 'mm')

            svgSnippet.set('viewBox', '0 0 ' + width + ' ' + height)
            svgSnippet.set('style','background-color:black;fill:white;')
            svgSnippet.append(i)
    
            ol += [svgSnippet]
        return ol, zdiff, slicer
    
    def load_file_this(self,path):
        print("Cargando pieza")
        name = path
        if not(os.path.exists(name)):
            return "Falta el .svg"
        else:
            layers = self.parse_svg(name)
            layerHeight = layers[1]
            self.thickness = str(layers[1])
            print "Layer thickness detected:", layerHeight, "mm"
            ret=("H:"+str(layerHeight)+" N:"+str(len(layers[0])))
        print len(layers[0]), "layers found, total height", layerHeight * len(layers[0]), "mm"
        self.layers = layers
        self.current_filename = os.path.basename(name) 
        self.slicer = layers[2]
        self.display_frame.slicer = self.slicer
        print("Pieza cargada")
        return ret

    def present_calibrate2(self):
        self.display_frame.Raise()
        self.display_frame.offset = (float(0), -float(0))
        self.display_frame.scale = 1.0
        resolution_x_pixels = int(self.X)
        resolution_y_pixels = int(self.Y)
        
        gridBitmap = wx.EmptyBitmap(resolution_x_pixels, resolution_y_pixels)
        dc = wx.MemoryDC()
        dc.SelectObject(gridBitmap)
        dc.SetBackground(wx.Brush("black"))
        dc.Clear()
        
        dc.SetPen(wx.Pen("red", 9))
        dc.DrawLine(0, 0, resolution_x_pixels, 0);
        dc.DrawLine(0, 0, 0, resolution_y_pixels);
        dc.DrawLine(resolution_x_pixels, 0, resolution_x_pixels, resolution_y_pixels);
        dc.DrawLine(0, resolution_y_pixels, resolution_x_pixels, resolution_y_pixels);
        
        dc.SetPen(wx.Pen("red", 2))
        aspectRatio = float(resolution_x_pixels) / float(resolution_y_pixels)
        
        projectedXmm = float(self.projected_X_mm)            
        projectedYmm = round(projectedXmm / aspectRatio)
        
        pixelsXPerMM = resolution_x_pixels / projectedXmm
        pixelsYPerMM = resolution_y_pixels / projectedYmm
        
        gridCountX = int(projectedXmm / 10)
        gridCountY = int(projectedYmm / 10)
            
        for y in xrange(0, gridCountY + 1):
            for x in xrange(0, gridCountX + 1):
                dc.DrawLine(0, y * (pixelsYPerMM * 10), resolution_x_pixels, y * (pixelsYPerMM * 10));
                dc.DrawLine(x * (pixelsXPerMM * 10), 0, x * (pixelsXPerMM * 10), resolution_y_pixels);
        self.first_layer=False
        self.display_frame.slicer = 'bitmap'
        self.display_frame.draw_layer(gridBitmap.ConvertToImage())

    def update_fullscreen2(self):
        self.display_frame.Maximize(True)
        self.display_frame.resize(wx.DisplaySize())
        self.display_frame.repos(0,0)
    
    def update_resolution(self, event):
        x = int(self.X)
        y = int(self.Y)
        self.display_frame.resize((x,y))
        self._set_setting('project_x',x)
        self._set_setting('project_y',y)
        self.refresh_display(event)
    
    def get_dpi(self):
        resolution_x_pixels = int(self.X)
        projected_x_mm = float(self.projected_X_mm)
        projected_x_inches = projected_x_mm / 25.4
        return resolution_x_pixels / projected_x_inches                         
        
    def start_present2(self,l): 
        self.display_frame.l=l
        if not hasattr(self, "layers"):
            print "No model loaded!"
            return
        self.display_frame.ended=False 
        self.display_frame.slicer = self.layers[2]
        self.display_frame.dpi = self.get_dpi()
        self.display_frame.fl_time = self.fl_time
        of_x=float(self.X)/2-(float(self.display_frame.part_w)/2)*self.get_dpi()/25.4
        of_y=float(self.Y)/2-(float(self.display_frame.part_h)/2)*self.get_dpi()/25.4
        offset=(of_x,of_y)

        self.display_frame.present(self.layers[0][:],
            thickness=float(self.thickness),
            interval=float(self.interval),
            overshoot=float(self.overshoot),
            scale=float(self.scale),
            pause=float(self.pause),
            z_axis_rate=int(self.z_axis_rate),
            size=(float(self.X), float(self.Y)),
            offset=offset,
            layer_red=False)
        
    def stop_present2(self):
        self.index=(0)
        self.display_frame.hide_pic()
        self.display_frame.running = False
        
if __name__ == "__main__":
    provider = wx.SimpleHelpProvider()
    wx.HelpProvider_Set(provider)
    a = wx.App()

