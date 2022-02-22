nohup python3 publishFakeData.py --root-ca /etc/iot-certificates/root.ca.pem --cert /etc/iot-certificates/75969a21f7-certificate.pem.crt --key /etc/iot-certificates/75969a21f7-private.pem.key --endpoint a2q9slo0dyelxs-ats.iot.us-east-1.amazonaws.com --count 0 --timeout 30 &

rm nohup.out
