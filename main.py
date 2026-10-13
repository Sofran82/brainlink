from brainlink import BrainLinkDataParser
from brainlink import BrainLinkSerial



def on_data(data):
    """Print BrainLink values safely, even when fields are missing."""

    def show(value, width=6):
        if value is None:
            return f"{'--':>{width}}"
        return f"{value:>{width}}"

    print(
        f"RAW={show(data.raw)} "
        f"Signal={show(data.signal, 3)} "
        f"Attention={show(data.attention, 3)} "
        f"Meditation={show(data.meditation, 3)} "
        f"Delta={show(data.delta)} "
        f"Theta={show(data.theta)}"
    )


def main():

    print("Available COM ports:")
    print()

    ports = BrainLinkSerial.list_ports()

    for port in ports:
        print(
            f"{port['device']:8} "
            f"{port['description']}"
        )

    print()

    port_name = input(
        "Enter BrainLink COM port: "
    ).strip()

    parser = BrainLinkDataParser(
        data_callback=on_data
    )

    serial = BrainLinkSerial(
        data_callback=parser.parse
    )

    try:

        serial.connect(port_name)

        print()
        print("Receiving BrainLink data...")
        print("Press Ctrl+C to stop.")
        print()

        while serial.running:
            pass

    except KeyboardInterrupt:

        print()
        print("Stopping...")

    finally:

        serial.disconnect()


if __name__ == "__main__":
    main()