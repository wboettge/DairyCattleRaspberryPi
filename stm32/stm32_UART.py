import serial

UART_PORT = '/dev/ttyACM0'
BAUD_RATE = 115200

ser = serial.Serial(port=UART_PORT, baudrate=115200)

try:
    while(True):
        print(ser.readLine())

except KeyboardInterrupt:
    print('Closing')
    
finally:
    ser.close()