import time
from adafruit_servokit import ServoKit

kit = ServoKit(channels=16)

'''
kit.servo[0].angle = 170
time.sleep(1)
kit.servo[0].angle = 0
time.sleep(1)

kit.servo[2].angle = 180
time.sleep(1) 
kit.servo[2].angle = 0
time.sleep(1)
'''
'''
kit.servo[0].set_pulse_width_range(400, 2600)
kit.servo[0].angle = 90
time.sleep(1)
kit.servo[0].angle = 0
time.sleep(1)
kit.servo[0].angle = 90
time.sleep(1)
kit.servo[0].angle = 180
time.sleep(1)
kit.servo[0].angle = 90
'''
'''
kit.servo[2].set_pulse_width_range(400, 2600)
kit.servo[2].angle = 90
time.sleep(1)
kit.servo[2].angle = 0
time.sleep(1)
kit.servo[2].angle = 90
time.sleep(1)    
kit.servo[2].angle = 180
time.sleep(1)
kit.servo[2].angle = 90

kit.servo[0].set_pulse_width_range(400, 2600)
kit.servo[0].angle = 90
time.sleep(1)
kit.servo[0].angle = 0
time.sleep(1)
kit.servo[0].angle = 90 
kit.servo[0].angle = 180
time.sleep(1)
kit.servo[0].angle = 90
time.sleep(1)`````````````````````````````````````````````````````````````````````````````
'''

'''
import time
from adafruit_servokit import ServoKit

kit = ServoKit(channels=16)

def set_arm_position(kit, angle):
    if angle < 0 or angle > 180:
        raise ValueError("Angle must be between 0 and 180 degrees.")

    kit.servo[2].angle = angle
    kit.servo[3].angle = 180 - angle 

kit.servo[0].set_pulse_width_range(400, 2600)
kit.servo[2].set_pulse_width_range(400, 2600)
kit.servo[3].set_pulse_width_range(400, 2600)

set_arm_position(kit, 90)
kit.servo[0].angle = 90
time.sleep(1)

set_arm_position(kit, 180)
time.sleep(1)

set_arm_position(kit, 90)
time.sleep(1)

set_arm_position(kit, 0)
time.sleep(1)

set_arm_position(kit, 90)
time.sleep(1)

kit.servo[0].angle = 0
time.sleep(1)

kit.servo[0].angle = 90
time.sleep(1)

kit.servo[0].angle = 180
time.sleep(1)

kit.servo[0].angle = 90
'''

kit.servo[0].set_pulse_width_range(400, 2600)
kit.servo[1].set_pulse_width_range(400, 2600)
kit.servo[2].set_pulse_width_range(400, 2600)
kit.servo[3].set_pulse_width_range(400, 2600)

def set_arm_position(kit, angle):
    if angle < 0 or angle > 180:
        raise ValueError("Angle must be between 0 and 180 degrees.")

    kit.servo[3].angle = angle
    kit.servo[2].angle = 180 - angle 

set_arm_position(kit, 90)

kit.servo[0].angle = 90
kit.servo[1].angle = 95