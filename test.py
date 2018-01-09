import time
import crc8
import PyItmp
import serial.tools.list_ports
import PyItmpSerial
import mot823

ports = PyItmpSerial.portList()
print(ports)

for port in ports:
    print(port.device, port.description, port.hwid, port.manufacturer, port.serial_number)


itmp = PyItmp.ITMP()
itmp.addLink(PyItmpSerial.ITMPSerialLink("com", "COM7"))

mot = mot823.mot823(itmp,"com/1")

itmp.start()
stat = mot.describe("")
print(stat)
while True:
    stat = mot.stat()
    print(stat)
    stat = mot.setpower(-10,-10)
    print(stat)
    time.sleep(1)
'''
stat = itmp.call("com/2", "sta", None)
print(stat)

stat = itmp.call("com/2", "", None)
print(stat)
'''
