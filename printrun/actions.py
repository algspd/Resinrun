#!/usr/bin/env python

import time
import RPi.GPIO as GPIO
import lcd
import array
import sys
import os
import glob
import shutil
from pronterface import PronterApp
from threading import Lock

class Actions:
    def start (self):
        print "Iniciando impresion"
        ret=self.app.startPrint(self.l)

    def __init__(self,app):
        self.l=lcd.Lcd()
        self.l.put_lines("Cargando...","")
        self.app=app
