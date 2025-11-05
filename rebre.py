#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time

RECEPTOR_PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(RECEPTOR_PIN, GPIO.IN)

def read_nec_code(timeout=5):
    start_time = time.time()
    code = 0
    bit_count = 0

    last_state = GPIO.input(RECEPTOR_PIN)
    last_time = time.time()

    print("Esperando señal del mando...")

    while time.time() - start_time < timeout:
        current_state = GPIO.input(RECEPTOR_PIN)
        if current_state != last_state:
            # Tiempo que duró el pulso
            pulse_time = (time.time() - last_time) * 1_000  # ms
            last_time = time.time()

            # NEC: ~0.56ms = 0, ~1.69ms = 1 (aprox)
            if last_state == 1:  # MARK
                if 0.4 < pulse_time < 0.8:
                    code = (code << 1) | 0
                    bit_count += 1
                elif 1.2 < pulse_time < 2.0:
                    code = (code << 1) | 1
                    bit_count += 1

            last_state = current_state

        if bit_count >= 32:
            # Recibido un código completo de 32 bits
            return code

    return None

try:
    while True:
        code = read_nec_code(timeout=5)
        if code is not None:
            print(f"Código recibido: 0x{code:08X}")
        else:
            print("No se detectó código")
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nPrograma interrumpido por el usuario")

finally:
    GPIO.cleanup()
