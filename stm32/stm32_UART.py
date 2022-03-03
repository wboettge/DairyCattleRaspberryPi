import serial

UART_PORT = '/dev/ttyACM0'
BAUD_RATE = 115200

ser = serial.Serial(port=UART_PORT, baudrate=115200)
try:
    while(True):
        print(str(ser.readline(), 'utf8'), end='')

except KeyboardInterrupt:
    print('Closing')

finally:
    ser.close()