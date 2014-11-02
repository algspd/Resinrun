#!/usr/bin/python

import smbus
import time
import string
import socket
import fcntl
import struct
import array
import threading

class Lcd:
	def __init__(self):
                self.lock=threading.Lock()
                self.lock.acquire()
		init()
		backlight()
                self.lock.release()
                self.line1=""
                self.line2=""
                self.write_line1()
                self.write_line2()

        def put_lines(self,l1,l2):
                self.lock.acquire()
                self.line1=l1
                self.line2=l2
                clear()
                setCursor(0, 0)
		sendString(self.line1)
                setCursor(0, 1)
		sendString(self.line2)
                self.lock.release()
                

	def put_line1(self,text):
                if (self.line1!=text):
                    self.line1=text
                    self.write_line1()

	def write_line1(self):
                self.lock.acquire()
                setCursor(0, 0)
		sendString("                ")
                setCursor(0, 0)
		sendString(self.line1)
                self.lock.release()

	def put_line2(self,text):
                if (self.line2!=text):
                    self.line2=text
                    self.write_line2()
	def write_line2(self):
                self.lock.acquire()
                setCursor(0, 1)
		sendString("                ")
                setCursor(0, 1)
		sendString(self.line2)
                self.lock.release()

	def clear(self):		
		clear()

# commands
LCD_CLEARDISPLAY=0x01
LCD_RETURNHOME=0x02
LCD_ENTRYMODESET=0x04
LCD_DISPLAYCONTROL=0x08
LCD_CURSORSHIFT=0x10
LCD_FUNCTIONSET=0x20
LCD_SETCGRAMADDR=0x40
LCD_SETDDRAMADDR=0x80

# flags for display entry mode
LCD_ENTRYRIGHT=0x00
LCD_ENTRYLEFT=0x02
LCD_ENTRYSHIFTINCREMENT=0x01
LCD_ENTRYSHIFTDECREMENT=0x00

# flags for display on/off control
LCD_DISPLAYON=0x04
LCD_DISPLAYOFF=0x00
LCD_CURSORON=0x02
LCD_CURSOROFF=0x00
LCD_BLINKON=0x01
LCD_BLINKOFF=0x00

# flags for display/cursor shift
LCD_DISPLAYMOVE=0x08
LCD_CURSORMOVE=0x00
LCD_MOVERIGHT=0x04
LCD_MOVELEFT=0x00

# flags for function set
LCD_8BITMODE=0x10
LCD_4BITMODE=0x00
LCD_2LINE=0x08
LCD_1LINE=0x00
LCD_5x10DOTS=0x04
LCD_5x8DOTS=0x00

# flags for backlight control
LCD_BACKLIGHT=0x08
LCD_NOBACKLIGHT=0x00

En=int('00000100',2) # Enable=bit
Rw=int('00000010',2) # Read/Write=bit
Rs=int('00000001',2) # Register=select=bit

bus = smbus.SMBus(1);
address = 0x27
_cols = 16;
_rows = 2;
_backlightval=LCD_NOBACKLIGHT;
_displaycontrol = LCD_DISPLAYON | LCD_CURSOROFF | LCD_BLINKOFF;
_displaymode = LCD_ENTRYLEFT | LCD_ENTRYSHIFTDECREMENT;

def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])

digs = string.digits + string.lowercase

def int2base(x, base):
  if x < 0: sign = -1
  elif x==0: return '0'
  else: sign = 1
  x *= sign
  digits = []
  while x:
    digits.append(digs[x % base])
    x /= base
  if sign < 0:
    digits.append('-')
  digits.reverse()
  return ''.join(digits)

def init():
        init_priv();

def init_priv() :
        global bus;
	bus = smbus.SMBus(1)
        global _displayfunction;
        _displayfunction = LCD_4BITMODE | LCD_1LINE | LCD_5x8DOTS;
        begin(_cols, _rows,0);  


def begin(cols, lines, dotsize) :
        if (lines > 1) :
		global _displayfunction;
                _displayfunction |= LCD_2LINE;
        global _numlines;
        _numlines = lines;

        # for some 1 line displays you can select a 10 pixel high font
        if ((dotsize != 0) & (lines == 1)) :
                _displayfunction |= LCD_5x10DOTS;
        

        # according to datasheet, we need at least 40ms after power rises above 2.7V
        # before sending commands. Arduino can turn on way befer 4.5V so we'll wait 50
	time.sleep(0.005);		# enable pulse must be >450ns
  
        # Now we pull both RS and R/W low to begin commands
        expanderWrite(_backlightval);   # reset expanderand turn backlight off (Bit 8 =1)
	time.sleep(1);		# enable pulse must be >450ns

        #put the LCD into 4 bit mode
        # this is according to the hitachi HD44780 datasheet
        # figure 24, pg 46
        
          # we start in 8bit mode, try to set 4 bit mode
	write4bits(0x03 << 4);
	time.sleep(0.0045);		# enable pulse must be >450ns

	# second try
	write4bits(0x03 << 4);
	time.sleep(0.0045);		# enable pulse must be >450ns
   
	# third go!
	write4bits(0x03 << 4); 
	time.sleep(0.0015); # wait min 4.1ms
   
	# finally, set to 4-bit interface
	write4bits(0x02 << 4); 

        # set # lines, font size, etc.
        command(LCD_FUNCTIONSET | _displayfunction);  
        
        # turn the display on with no cursor or blinking default
        _displaycontrol = LCD_DISPLAYON | LCD_CURSOROFF | LCD_BLINKOFF;
        display();
        
        # clear it off
        clear();
        
        # Initialize to default text direction (for roman languages)
        _displaymode = LCD_ENTRYLEFT | LCD_ENTRYSHIFTDECREMENT;
        
        # set the entry mode
        command(LCD_ENTRYMODESET | _displaymode);
        
        home();

def send(value, mode):
	highnib=value&0xf0;
	lownib=(value<<4)&0xf0;
	write4bits((highnib)|mode);
	write4bits((lownib)|mode); 

def pulseEnable(_data):
	expanderWrite(_data | En);	# En high
	time.sleep(0.001);		# enable pulse must be >450ns
	expanderWrite(_data & ~En);	# En low
	time.sleep(0.05);		# commands need > 37us to settle

def clear():
	command(LCD_CLEARDISPLAY);# clear display, set cursor position to zero
	time.sleep(0.2); # this command takes a long time!

def home():
	command(LCD_RETURNHOME);  # set cursor position to zero
	time.sleep(0.2);  # this command takes a long time!

def setCursor(col, row):
	row_offsets=array.array('b',[0x00, 0x40, 0x14, 0x54]);
	if ( row > _numlines ):
		row = _numlines-1;    # we count rows starting w/0
	command(LCD_SETDDRAMADDR | (col + row_offsets[row]));
# Turn the display on/off (quickly)
def noDisplay() :
        global _displaycontrol;
        _displaycontrol = _displaycontrol&~LCD_DISPLAYON;
        command(LCD_DISPLAYCONTROL | _displaycontrol);

def display() :
        global _displaycontrol;
        _displaycontrol = _displaycontrol|LCD_DISPLAYON;
        command(LCD_DISPLAYCONTROL | _displaycontrol);


# Turns the underline cursor on/off
def noCursor() :
        global _displaycontrol;
        _displaycontrol &= ~LCD_CURSORON;
        command(LCD_DISPLAYCONTROL | _displaycontrol);

def cursor() :
        global _displaycontrol;
        _displaycontrol |= LCD_CURSORON;
        command(LCD_DISPLAYCONTROL | _displaycontrol);


# Turn on and off the blinking cursor
def noBlink() :
        global _displaycontrol;
        _displaycontrol &= ~LCD_BLINKON;
        command(LCD_DISPLAYCONTROL | _displaycontrol);

def blink() :
        global _displaycontrol;
        _displaycontrol |= LCD_BLINKON;
        command(LCD_DISPLAYCONTROL | _displaycontrol);


# These commands scroll the display without changing the RAM
def scrollDisplayLeft(void) :
        command(LCD_CURSORSHIFT | LCD_DISPLAYMOVE | LCD_MOVELEFT);

def scrollDisplayRight(void) :
        command(LCD_CURSORSHIFT | LCD_DISPLAYMOVE | LCD_MOVERIGHT);


# This is for text that flows Left to Right
def leftToRight(void) :
        global _displaymode;
        _displaymode |= LCD_ENTRYLEFT;
        command(LCD_ENTRYMODESET | _displaymode);


# This is for text that flows Right to Left
def rightToLeft(void) :
        global _displaymode;
        _displaymode &= ~LCD_ENTRYLEFT;
        command(LCD_ENTRYMODESET | _displaymode);


# This will 'right justify' text from the cursor
def autoscroll(void) :
        global _displaymode;
        _displaymode |= LCD_ENTRYSHIFTINCREMENT;
        command(LCD_ENTRYMODESET | _displaymode);


# This will 'left justify' text from the cursor
def noAutoscroll(void) :
        global _displaymode;
        _displaymode &= ~LCD_ENTRYSHIFTINCREMENT;
        command(LCD_ENTRYMODESET | _displaymode);


# Allows us to fill the first 8 CGRAM locations
# with custom characters
def createChar(location, charmap) :
        location &= 0x7; # we only have 8 locations 0-7
        command(LCD_SETCGRAMADDR | (location << 3));
        for i in range(8) :
                write(charmap[i]);

# Turn the (optional) backlight off/on
def noBacklight():
        global _backlightval;
        _backlightval=LCD_NOBACKLIGHT;
        expanderWrite(0);

def backlight():
        global _backlightval;
        _backlightval=LCD_BACKLIGHT;
        expanderWrite(0);

def command(value) :
        send(value, 0);

def write(value) :
        send(value, Rs);

def write4bits(value) :
        expanderWrite(value);
        pulseEnable(value);

def expanderWrite(_data):                                        
	bus.write_byte_data(address, 0, (int)(_data) | _backlightval)

def pulseEnable(_data):
        expanderWrite(_data | En);      # En high
        time.sleep(0.001)
        expanderWrite(_data & ~En);     # En low
        time.sleep(0.050)

def cursor_on():
        cursor();

def cursor_off():
        noCursor();

def blink_on():
        blink();

def blink_off():
        noBlink();

def load_custom_character(char_num, *rows):
	createChar(char_num, rows);

def setBacklight(new_val):
        if(new_val):
		backlight();            # turn backlight on
        else:
		noBacklight();          # turn backlight off

def printstr(c):
        #This function is not identical to the function used for "real" I2C displays
        #it's here so the user sketch doesn't have to be changed 
        print(c);

def sendChar(c):
        cnum=ord(c);
	highnib=cnum & 0xf0;
	lownib=(cnum<<4) & 0xf0;
        expanderWrite((highnib)|0x9);
	expanderWrite((highnib)|0xD);
	expanderWrite((highnib)|0x9);
	expanderWrite((lownib)|0x9);
	expanderWrite((lownib)|0xD);
	expanderWrite((lownib)|0x9);

def sendString(s):
	for i in range(0, len(s)):
		sendChar(s[i]);

