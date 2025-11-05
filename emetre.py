import RPi.GPIO as GPIO
import time

LASER_PIN = 4


GPIO.setmode(GPIO.BCM)
GPIO.setup(LASER_PIN, GPIO.OUT)

try:
    print("Encendiendo láser...")
    GPIO.output(LASER_PIN, GPIO.HIGH)
    time.sleep(5)

    print("Apagando láser...")
    GPIO.output(LASER_PIN, GPIO.LOW)
    time.sleep(2)


except KeyboardInterrupt:
    print("Interrumpido por el usuario")
finally:
    GPIO.cleanup()