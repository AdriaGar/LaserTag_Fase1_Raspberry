#!/usr/bin/env python3
import pigpio
import time

GPIO_IR = 18        # GPIO del KY-005 (recomendado: 18 tiene hardware PWM)
CARRIER_FREQ = 38000
DUTY_CYCLE = 0.5    # 50%

# Ajustes NEC
MARK = 560e-6       # 560 µs
ONE_SPACE = 1690e-6
ZERO_SPACE = 560e-6
HEADER_MARK = 9000e-6
HEADER_SPACE = 4500e-6
TRAILER_MARK = 560e-6

pi = pigpio.pi()
if not pi.connected:
    print("No se pudo conectar con pigpio")
    exit()

def send_mark(duration):
    pi.hardware_PWM(GPIO_IR, CARRIER_FREQ, int(DUTY_CYCLE * 1e6))
    time.sleep(duration)
    pi.hardware_PWM(GPIO_IR, 0, 0)

def send_space(duration):
    pi.hardware_PWM(GPIO_IR, 0, 0)
    time.sleep(duration)

def send_nec(code):
    # Encabezado
    send_mark(HEADER_MARK)
    send_space(HEADER_SPACE)

    # 32 bits
    for i in range(32):
        send_mark(MARK)
        if code & (1 << (31 - i)):
            send_space(ONE_SPACE)
        else:
            send_space(ZERO_SPACE)

    # Bit de fin
    send_mark(TRAILER_MARK)
    send_space(0)

try:
    while True:
        hex_code = input("Introduce código hexadecimal NEC a emitir (ej: 0x20DF10EF): ")
        try:
            code = int(hex_code, 16)
            print(f"Enviando código 0x{code:08X}...")
            send_nec(code)
            print("Código enviado.\n")
        except ValueError:
            print("Formato inválido. Usa 0xXXXXXXXX")

except KeyboardInterrupt:
    print("\nPrograma interrumpido por el usuario.")

finally:
    pi.hardware_PWM(GPIO_IR, 0, 0)
    pi.stop()