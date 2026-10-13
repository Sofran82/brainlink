import threading
import time

import serial
from serial.tools import list_ports


class BrainLinkSerial:
    """
    Handles the Windows Bluetooth virtual COM port.

    The BrainLink parser does NOT open the COM port itself.
    pyserial provides the byte stream.
    """

    BAUD_RATE = 115200

    def __init__(self, data_callback=None):
        self.data_callback = data_callback

        self.serial = None

        self.running = False
        self.thread = None

    # ---------------------------------------------------------
    # COM port discovery
    # ---------------------------------------------------------

    @staticmethod
    def list_ports():
        """
        Return available serial ports.
        """

        ports = []

        for port in list_ports.comports():
            ports.append({
                "device": port.device,
                "description": port.description,
                "manufacturer": port.manufacturer,
            })

        return ports

    # ---------------------------------------------------------
    # Connection
    # ---------------------------------------------------------

    def connect(self, port: str):
        if self.running:
            return

        print(f"Opening BrainLink on {port}")

        self.serial = serial.Serial(
            port=port,
            baudrate=self.BAUD_RATE,
            timeout=0.1,
        )

        self.running = True

        self.thread = threading.Thread(
            target=self._read_loop,
            daemon=True,
        )

        self.thread.start()

        print("BrainLink connected.")

    # ---------------------------------------------------------
    # Reader
    # ---------------------------------------------------------

    def _read_loop(self):

        while self.running:

            try:

                if self.serial is None:
                    break

                waiting = self.serial.in_waiting

                if waiting:
                    data = self.serial.read(waiting)

                    if self.data_callback:
                        self.data_callback(data)

                else:
                    time.sleep(0.001)

            except serial.SerialException as exc:

                print(f"Serial error: {exc}")

                self.running = False
                break

    # ---------------------------------------------------------
    # Disconnect
    # ---------------------------------------------------------

    def disconnect(self):

        self.running = False

        if self.thread:
            self.thread.join(timeout=1.0)

        if self.serial:
            try:
                self.serial.close()
            except serial.SerialException:
                pass

        self.serial = None

        print("BrainLink disconnected.")