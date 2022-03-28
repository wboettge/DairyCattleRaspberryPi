import serial
import serial.tools.list_ports

ports = list(serial.tools.list_ports.grep('ACM'))
if len(ports) == 0:
    print('Cannot find UART port, exiting...')
    exit(-1)

UART_PORT = ports[0].device
BAUD_RATE = 115200

ser = serial.Serial(port=UART_PORT, baudrate=BAUD_RATE)
# Read from UART and print line-by-line
while(True):
    print(str(ser.readline(), 'utf8'), end='')
