import json
import re
import serial
import serial.tools.list_ports

def parse_lora_packet(packet_str):
    map_message_ids = {
        'I': {
            'cast_func': int,
            'full_name': 'Device_ID'
        },
        'T': {
            'cast_func': float,
            'full_name': 'Temperature'
        },
        'A': {
            'cast_func': lambda accelData: {datum: float(val) for datum, val in zip(['x', 'y', 'z'], accelData.split(' '))},
            'full_name': 'Acceleration'
        }
    }
    # Goal is to split a string with letters and data into two lists to build
    # a dictionary from the packet. i.e. I08 T34.1 A1.16 -1.91 becomes
    # {'Device_Id': 08, 'Temperature': 34.1, 'Acceleration': 1.16, -1.91}

    # 'I08 T34.1 A1.16 -1.91' -> [('I', '08'), ('T', '34.1 '), ('A', '1.16 -1.91)]
    data_points = re.findall(r'([a-zA-Z])+([^(a-zA-Z\n)]*)', packet_str) 
    # Build a dictionary by mapping letters to full labels and casting data based on given cast_func in map above
    return {map_message_ids[label]['full_name']: map_message_ids[label]['cast_func'](data) for label, data in data_points}


ports = list(serial.tools.list_ports.grep('ACM'))
if len(ports) == 0:
    print('Cannot find UART port, exiting...')
    exit(-1)

UART_PORT = ports[0].device
BAUD_RATE = 115200

ser = serial.Serial(port=UART_PORT, baudrate=BAUD_RATE)
# Read from UART and print line-by-line
while(True):
    from_ser = str(ser.readline(), 'utf8')
    json_data = json.dumps(parse_lora_packet(from_ser))
    print(json_data, flush=True)

