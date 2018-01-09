#!/usr/bin/env python3
# coding:utf-8

from collections import deque
import threading
import serial
import serial.tools
import serial.tools.list_ports
import cbor  # = require('cbor');

import crc8  # = require('./crc8');

#PORT = "/dev/ttyS0"
BAUD = 115200
TIMEOUT = 0.01    # Число секунд ожидания или None

def portList():
    """ return list of ports """
    return serial.tools.list_ports.comports()

class ITMPSerialLink:
    """Return the pathname of the KOS root directory."""
    def __init__(self, name, portname):  # props =  baudRate: 115200
        self.lnkname = name
        self.addressable = True

        try:
            ser = serial.Serial(portname)
        except:  # SerialException:
            print("Проблема: не могу открыть порт {0}".format(portname))
            exit(0)

        # Настраиваем последовательный порт
        ser.baudrate = BAUD
        ser.timeout = TIMEOUT
        ser.bytesize = serial.EIGHTBITS
        ser.parity = serial.PARITY_NONE
        ser.stopbits = serial.STOPBITS_ONE

        self.port = ser


        self.polls = {}

        # incoming messages encoding
        self.inbuf = bytearray(1024)
        self.overflow = 0
        self.inpos = 0  # // number of received bytes (inbuf position)
        self.lastchar = 0  # // code of last received char =0 means no special character
        self.incrc = 0xff  # // current crc calculation

        self.ready = False  # // port opened flag
        self.busy = False  # // bus busy flag
        self.timerId = None #// timeout timer id

        self.cur_addr = 0  # // current transaction address
        self.cur_buf = bytearray(1024)
        self.msgqueue = deque()
        self.itmp = None

        self.readThread = threading.Thread(target=self.read_thread)
        self.readThread.daemon = True
        # self.reopen = (that) => {
        #  if (not that.port.isOpen) {
        #    that.port.open(() => {
        #      setTimeout(that.reopen, 1000, that);
        #    );

        # self.port.on('close', () =>
        #// open logic
        #  self.ready = False; #// port opened flag
        #  setTimeout(self.reopen, 1000, self);
        #  print('close');

        self.ports = {}
        # SerialPort.list((err, ports) => {
        #  const ctx = self;
        #  ports.forEach((port) => {
        #    ctx.ports[port.comName] = port;
        #// print(port.comName+JSON.stringify(port));
        #// print(port.manufacturer);
        #  );

    def start(self, itmp):
        """ start read thread while connected to itmp"""
        self.itmp = itmp

        self.readThread.start()

    """
    def subscribe(subaddr, suburi, opts, done):
        #//    const that = self;
        const sub = setInterval(() => {
          const that2 = self;
          self.itmp.call(f"${self.lnkname}/${subaddr}", suburi, null, (data, ropts) => 
            const url = f"${that2.lnkname}/${subaddr}/${suburi}";
            #// if ()
            that2.itmp.emitEvent(url, data, ropts);
          );
        , 1000)
        self.polls.set(f"${subaddr}/${suburi}", sub)
        done()

    def unsubscribe(subaddr, suburi, opts, done, err)
        const timer = self.polls.get(f"${subaddr}/${suburi}")
        if (timer) 
          clearInterval(timer)
          done()
        else 
          err()

    def call(subaddr, suburi) :
        if (suburi === '') 
          return self.ports;
        
        return null;
    """

    def income(self, data):
        """Process incoming bytes."""
        for bt in data:
            if bt == 0x7e:
                frame = self.inpos > 0 
                if self.inpos > 2 and self.incrc == 0 and self.overflow == 0:
                    addr = self.inbuf[0]
                    msg = cbor.loads(self.inbuf[1:self.inpos])
                    self.itmp.process(f"{self.lnkname}/{addr}", msg)

                self.lastchar = 0
                self.inpos = 0
                self.incrc = 0xff
                self.overflow = 0
                if frame:
                    self.nexttransaction()
            elif bt == 0x7d:
                self.lastchar = 0x7d
            elif self.inpos >= len(self.inbuf):
                self.overflow += 1
            elif self.lastchar == 0x7d:
                self.inbuf[self.inpos] = bt ^ 0x20
                self.incrc = crc8.docrc8(self.incrc, bt ^ 0x20)
                self.inpos += 1
                self.lastchar = 0
            else:
                self.inbuf[self.inpos] = bt
                self.incrc = crc8.docrc8(self.incrc, bt)
                self.inpos += 1

    def nexttransaction(self):
        """process next transaction, or if no next transaction finish current"""
        if self.msgqueue:  # if not empty
            [addr, msg] = self.msgqueue.popleft()
            self.internalsend(addr, msg)
        else:
            self.cur_addr = 0
            if self.timerId:
                self.timerId.cancel()
                self.timerId = None
            if self.busy:
                self.busy = False
            else:
                print('message written')

    def timeisout(self):
        """time to get answer is over"""
        self.nexttransaction()

    def send(self, addr, msg, key=None):
        """send message to this link"""
        binmsg = cbor.dumps(msg)
#        if key:
#            self.itmp.sendfail(f"{self.lnkname}/{addr}", key, (500, "internal error"))
#            return None

        if self.busy:
            self.msgqueue.append([addr, binmsg])
        else:
            self.busy = True
            self.internalsend(addr, binmsg)
        return None # no errors

    def internalsend(self, addr, binmsg):
        """ send prepared message directly to serial link"""
        self.cur_addr = addr
        if self.timerId:
            self.timerId.cancel()
        self.timerId = threading.Timer(0.200, self.timeisout)
        self.timerId.start()

        if len(self.cur_buf) < len(binmsg) * 2:
            self.cur_buf = bytearray(len(binmsg) * 2)

        crc = 0xff
        self.cur_buf[0] = 0x7e
        self.cur_buf[1] = int(addr)  # // address
        crc = crc8.docrc8(crc, self.cur_buf[1])

        pos = 2
        for c in binmsg:
            crc = crc8.docrc8(crc, c)
            if c == 0x7e or c == 0x7d:
                self.cur_buf[pos] = 0x7d
                self.cur_buf[pos + 1] = c ^ 0x20
                pos += 2
            else:
                self.cur_buf[pos] = c
                pos += 1
        if crc == 0x7e or crc == 0x7d:
            self.cur_buf[pos] = 0x7d
            self.cur_buf[pos + 1] = crc ^ 0x20
            pos += 2
        else:
            self.cur_buf[pos] = crc
            pos += 1

        self.cur_buf[pos] = 0x7e
        sndbuf = self.cur_buf[:pos + 1]  # .partition(.slice(0, pos + 1)

        self.port.write(sndbuf)
        self.port.flush()
        #//    var timerId = setTimeout( (key)=>{ var prom = that.transactions.get(key);
        #// that.transactions.delete(key); prom.err("timeout"); }, 2000, key);

    def read_thread(self):
        """read thread"""
        while True:
            byte = self.port.read()  # Читаем один байт
            # print("{0:02X}".format(ord(byte))) # Строка для отладки
            if byte:
                # Принят байт
                self.income(byte)

    def queueSize(self):
        return len(self.msgqueue)
