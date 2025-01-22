import sys
import hid
import psutil

# Device identifiers
VENDOR_ID = 0xA743  # Replace with your device's VID
PRODUCT_ID = 0x0260  # Replace with your device's PID
USAGE_PAGE = 0xFF60
USAGE = 0x61
REPORT_LENGTH = 32  # HID report length

def get_raw_hid_interface():
    device_interfaces = hid.enumerate(VENDOR_ID, PRODUCT_ID)
    raw_hid_interfaces = [
        i for i in device_interfaces
        if i['usage_page'] == USAGE_PAGE and i['usage'] == USAGE
    ]

    if not raw_hid_interfaces:
        return None

    interface = hid.Device(path=raw_hid_interfaces[0]['path'])
    print(f"Manufacturer: {interface.manufacturer}")
    print(f"Product: {interface.product}")
    return interface

# Send a HID report
def send_raw_report(data):
    interface = get_raw_hid_interface()

    if interface is None:
        print("No device found")
        sys.exit(1)

    # Ensure data length matches the report length
    request_data = [0x00] * (REPORT_LENGTH + 1)  # Report ID + Data
    request_data[1:len(data) + 1] = data  # Insert data into the report
    request_report = bytes(request_data)

    print("Request:")
    print(" ".join(f"0x{byte:02X}" for byte in request_report))  # Print in hex format

    try:
        interface.write(request_report)

        response_report = interface.read(REPORT_LENGTH, timeout=1000)
        print("Response:")
        print(" ".join(f"0x{byte:02X}" for byte in response_report))  # Print in hex format
    finally:
        interface.close()

# Gather system metrics
def get_system_metrics():
    cpu = int(psutil.cpu_percent(interval=1))  # CPU usage percentage
    ram = int(psutil.virtual_memory().percent)  # RAM usage percentage
    return cpu, ram

# Construct the correct data format
def construct_data():
    cpu, ram = get_system_metrics()
    # Command byte + CPU + RAM values
    data = [0x01, cpu & 0xFF, ram & 0xFF]  # Ensure values are single-byte (0-255)
    return data

# Main function to send metrics
def send_system_metrics():
    data = construct_data()
    print(f"Constructed Data: {' '.join(f'0x{byte:02X}' for byte in data)}")
    send_raw_report(data)

if __name__ == '__main__':
    print("Sending system metrics to the keyboard...")
    send_system_metrics()
