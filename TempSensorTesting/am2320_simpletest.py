# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

import time
import board
import adafruit_am2320

# create the I2C shared bus
i2c = board.I2C()  # uses board.SCL and board.SDA
am = adafruit_am2320.AM2320(i2c)

while True:
    try:
        print("Temperature: ", am.temperature)
        time.sleep(5)
    except Exception:
        continue
