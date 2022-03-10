import serial

ports = list(serial.tools.list_ports.grep('ACM'))
if len(ports) == 0:
    print('Cannot find UART port, exiting...')
    exit(-1)

UART_PORT = ports[0].device
BAUD_RATE = 9600

ser = serial.Serial(port=UART_PORT, baudrate=BAUD_RATE)
# Read from UART and print line-by-line
try:
    while(True):
        print(str(ser.readline(), 'utf8'), end='')

except KeyboardInterrupt:
    print('Closing')

finally:
    ser.close()