import PyItmp
from struct import *

class itmpnode:
    def __init__(self, itmp, addr):
        self.itmp = itmp
        self.addr = addr
    def describe(self, name):
        return self.itmp.describe(self.addr, name)

class mot823 (itmpnode):
    def __init__(self, itmp, addr):
        itmpnode.__init__(self, itmp, addr)
        self.leftpos = 0
        self.rightpos = 0
        self.lastread = 0
        self.bumper = False
        self.distance = 0

    def processstatus(self, data):
        s = unpack('iiii', data)
        [self.leftpos, self.rightpos, self.lastread, dist] = s
        if dist >= 100500:
            self.bumper = True
            dist -= 100500
        else:
            self.bumper = False
        self.distance = dist
        return {'l': self.leftpos, 'r': self.rightpos, 't': self.lastread, 'd': self.distance, 'b': self.bumper}

    def goto(self, left, right, speed, acc, speedright, accright):
        param = pack('ii', left, right)
        #param = pack('iiii', left,right, speed, acc)
        #param = pack('iiii', left,right, speed, acc, speedright, accright)
        data = self.itmp.call(self.addr, 'to', [param])
        self.processstatus(data)

    def setspeed(self, left, right, acc, accright):
        param = pack('ii', left, right)
        #param = pack('iiii', left, right, acc)
        #param = pack('iiii', left, right, acc, accright)
        if self.itmp.queueSize(self.addr) < 1:
            data = self.itmp.call(self.addr, 'sp', [param])
            self.processstatus(data)

    def setpower(self, left, right):
        param = pack('hh', left, right)
        if self.itmp.queueSize(self.addr) < 1:
            data = self.itmp.call(self.addr, 'go', [param])
            return self.processstatus(data)
        return None

    def setservo(self, first, second):
        param = pack('hh', first, second)
        if self.itmp.queueSize(self.addr) < 1:
            data = self.itmp.call(self.addr, 'set', [param])
            self.processstatus(data)

    def call(self, name, param):
        return self.itmp.call(self.addr, name, param)

    def stat(self):
        o = pack('b', 0)
        data = self.itmp.call(self.addr, 'stat', [o])
        param = unpack('hb', data)
        return {'v': param[0] / 1000, 'flag': param[1]}

    def pos(self):
        ret = self.itmp.call(self.addr, 'to', None)
        return self.processstatus(ret)
