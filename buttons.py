#!/usr/bin/env python

import time
import RPi.GPIO as GPIO
from subprocess import call
import array
import os
import dl
import shutil
import glob
from printrun import lcd
import serial

class Buttons:
    def mount(self):
        partitionsFile = open("/proc/partitions")
        lines = partitionsFile.readlines()[2:]#Skips the header lines
        for line in lines:
            words = [x.strip() for x in line.split()]
            minorNumber = int(words[1])
            deviceName = words[3]
            if not minorNumber % 16 == 0:
                path = "/sys/class/block/" + deviceName
                if os.path.islink(path):
                    if os.path.realpath(path).find("/usb") > 0:
                        dev = "/dev/%s" % deviceName
                        out=os.system("mount "+dev+" /mnt/")
                        return True
        return False

    def umount(self):
        print "Desmontando mnt"
        os.system ("umount /mnt/")

    def get_dest_file(self):
            if self.mount():
                newest = max(glob.iglob('/mnt/*.[Ss][Vv][Gg]'), key=os.path.getctime)
                if newest=="":
                    return False
                print "Parece que ha encontrado nuevo: " + newest
                shutil.copy(newest,'/root/part.svg')
                config="/mnt/config.txt"
                print "Copiando config"
                shutil.copy(config,'/root/.pronsolerc')
                self.umount()
                return True
            else:
                return False

    def setup (self):
        self.pin_start  = 23
        self.pin_stop   = 18
        self.pin_z_up   = 24
        self.pin_z_down = 25

        # Status = 0: stopped
        # Status = 1: printing
        # Status = 2: buttons disabled
        # Estado = 3: going up
        # Estado = 4: going down
        estado = 0

    def button (self,pin):

            time.sleep(0.05)
            if GPIO.input(pin)==GPIO.HIGH:
                # Noise
                # print('Pulsacion provocada por ruido probablemente')
                return;

            # START
            if (pin==self.pin_start and self.estado != 1):
                self.estado=1
                print "Start pulsado"
                self.l.put_lines("Iniciando...","")
                if not self.get_dest_file():
                    self.estado = 0
                    self.umount()
                    self.l.put_lines("Introduzca USB","con .svg valido")
                    return
                call(["/usr/bin/python", "/root/Resinrun_2/pronterface.py","-c","/root/.pronsolerc"])
                print "Terminado"
                self.l.put_lines("Pieza terminada","")
                self.estado=0

            # STOP
            elif (pin==self.pin_stop and self.estado!=2):
                self.estado=2

                # Stop printing
                if(call(["/usr/bin/killall", "python"])==0):
                    if (self.arduino.isOpen()): self.arduino.close()
                    self.arduino.open()
                    self.arduino.close()
                    self.arduino.open()
                    self.arduino.write("G90\n")
                    self.arduino.write("M210 Z160\n")
                    self.arduino.write("G0 Z400\n")
                    self.arduino.close()
                else:

                    # Close projector
                    if (self.arduino.isOpen()): self.arduino.close()
                    self.arduino.open()
                    self.arduino.close()
                    self.arduino.open()
                    self.arduino.close()
                 
                # Rewrite LCD
                self.l.clear()
                self.l.put_lines(" Maquina parada","")

                self.estado=0
                return
    
            # UP
            elif (pin==self.pin_z_up and (self.estado == 0 or self.estado==4)):
                self.estado=3
                if (self.arduino.isOpen()):
                    self.arduino.close()
                if (not self.arduino.isOpen()):
                    self.arduino.open()
                time.sleep(2)
                self.arduino.write("G90\n")
                self.arduino.write("M210 Z160\n")
                self.arduino.write("G0 Z400\n")
                self.arduino.close()

            # DOWN
            elif (pin==self.pin_z_down and (self.estado == 0 or self.estado==3)):
                self.estado=4
                if (self.arduino.isOpen()):
                    self.arduino.close()
                if (not self.arduino.isOpen()):
                    self.arduino.open()
                time.sleep(2)
                self.arduino.write("M210 Z160\n")
                self.arduino.write("G28\n")
                self.arduino.close()

            else:
                pass
            
    def __init__(self):
        self.l=lcd.Lcd()
        self.l.put_lines(" Arcade Printer ","  A imprimir!   ")
        self.setup()
        self.estado=0
        self.arduino = serial.Serial('/dev/ttyACM0',
                     baudrate=115200,
                     bytesize=serial.EIGHTBITS,
                     parity=serial.PARITY_NONE,
                     stopbits=serial.STOPBITS_ONE,
                     timeout=1,
                     xonxoff=0,
                     rtscts=0
                     )
        self.arduino.close()

        # Set numbering
        GPIO.setmode(GPIO.BCM)
       
        # Set mode input
        GPIO.setup(self.pin_start, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.pin_stop,  GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.pin_z_up,  GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.pin_z_down,GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
        # Call handler on falling
        GPIO.add_event_detect(self.pin_start, GPIO.FALLING, callback=self.button, bouncetime=500)
        GPIO.add_event_detect(self.pin_stop,  GPIO.FALLING, callback=self.button, bouncetime=500)
        GPIO.add_event_detect(self.pin_z_up,  GPIO.FALLING, callback=self.button, bouncetime=500)
        GPIO.add_event_detect(self.pin_z_down,GPIO.FALLING, callback=self.button, bouncetime=500)

libc = dl.open('/lib/arm-linux-gnueabihf/libc.so.6')
libc.call('prctl',15,'buttonlistener',0,0,0)
b=Buttons()

try:
    while True:
        time.sleep(10)
except:
    GPIO.cleanup()
