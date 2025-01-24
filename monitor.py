import sys
import psutil
import hid
import win32pdh  # For Windows Performance Counters
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Slot, QTimer
from monitor_ui import Ui_Dialog

# Replace with your device-specific values
VENDOR_ID = 0xA743  # Your device's Vendor ID
PRODUCT_ID = 0x0260  # Your device's Product ID
USAGE_PAGE = 0xFF60
USAGE = 0x61
REPORT_LENGTH = 32

class MonitorDialog(QDialog):
    def __init__(self, parent=None):
        super(MonitorDialog, self).__init__(parent)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

        self.hid_interface = None

        # Initialize Windows Performance Counter for CPU
        self.cpu_query_handle = None
        self.cpu_counter_handle = None
        self.last_raw_data = None
        self.is_first_sample = True  # Equivalent to m_first_get_CPU_utility in C++
        self.initialize_cpu_counter()

        # Set up the timer for sending metrics every second
        self.timer = QTimer(self)
        self.timer.setInterval(1000)  # 1000 ms = 1 second
        self.timer.timeout.connect(self.send_system_metrics)

        self.ui.connectBtm.clicked.connect(self.handle_connect)
        self.ui.disconnectBtm.clicked.connect(self.handle_disconnect)

    def log_status(self, message: str):
        """Append a status message to the QTextBrowser."""
        self.ui.statusBar.append(message)

    def initialize_cpu_counter(self):
        """Initialize performance counter for CPU usage."""
        self.cpu_query_handle = win32pdh.OpenQuery()
        windows_version = sys.getwindowsversion().major
        if windows_version >= 10:
            query_str = "\\Processor Information(_Total)\\% Processor Utility"
        else:
            query_str = "\\Processor Information(_Total)\\% Processor Time"
        self.cpu_counter_handle = win32pdh.AddCounter(
            self.cpu_query_handle, query_str
        )
        # Collect initial data to establish a baseline
        win32pdh.CollectQueryData(self.cpu_query_handle)

    def get_cpu_usage(self):
        """Fetch CPU usage using two-point calculation logic."""
        # Collect current data
        win32pdh.CollectQueryData(self.cpu_query_handle)

        # Get formatted counter value
        _, formatted_value = win32pdh.GetFormattedCounterValue(
            self.cpu_counter_handle, win32pdh.PDH_FMT_DOUBLE
        )

        if self.is_first_sample:
            self.is_first_sample = False
            self.last_raw_data = formatted_value  # Store the current value as baseline
            return 0  # Return 0 for the first sample since no prior data exists

        # Return the formatted value (no raw counter needed for formatted calculation)
        return round(formatted_value)

    def get_hid_interface(self):
        device_interfaces = hid.enumerate(VENDOR_ID, PRODUCT_ID)
        raw_hid_interfaces = [
            i for i in device_interfaces
            if i['usage_page'] == USAGE_PAGE and i['usage'] == USAGE
        ]

        if not raw_hid_interfaces:
            return None

        interface = hid.Device(path=raw_hid_interfaces[0]['path'])
        return interface

    @Slot()
    def handle_connect(self):
        """Handle the user clicking the Connect button."""
        if self.hid_interface is not None:
            self.log_status("Already connected.")
            return

        self.hid_interface = self.get_hid_interface()

        if self.hid_interface:
            self.log_status(f"Connected to device: {self.hid_interface.manufacturer} {self.hid_interface.product}")
            # Start sending metrics every second
            self.timer.start()
        else:
            self.log_status("No device found. Check if device is plugged in and correct VID/PID/usage values.")

    @Slot()
    def handle_disconnect(self):
        """Handle the user clicking the Disconnect button."""
        if self.hid_interface:
            self.timer.stop()  # Stop sending metrics
            self.hid_interface.close()
            self.hid_interface = None
            self.log_status("Disconnected from HID device.")
        else:
            self.log_status("No active connection to disconnect.")

    def get_system_metrics(self):
        """Fetch system metrics: CPU and RAM usage."""
        # Get CPU usage
        cpu_percent = self.get_cpu_usage()

        # Get RAM usage
        mem_info = psutil.virtual_memory()
        ram_percent = int(mem_info.percent)

        return cpu_percent, ram_percent

    def send_raw_report(self, data):
        """Send a HID report to the device and read the response."""
        if not self.hid_interface:
            self.log_status("Not connected to any device.")
            return

        request_data = [0x00] * (REPORT_LENGTH + 1)
        request_data[1:len(data)+1] = data
        request_report = bytes(request_data)

        # Log what we're sending in hex format
        req_hex = " ".join(f"0x{byte:02X}" for byte in request_report)
        self.log_status(f"Sending: {req_hex}\n")

        self.hid_interface.write(request_report)
        response_report = self.hid_interface.read(REPORT_LENGTH, timeout=500)

        if response_report:
            res_hex = " ".join(f"0x{byte:02X}" for byte in response_report)
            self.log_status(f"Received: {res_hex}\n")
        else:
            self.log_status("No response received.")

    def send_system_metrics(self):
        """Send system metrics to the device."""
        if not self.hid_interface:
            return  # If disconnected, do nothing

        cpu, ram = self.get_system_metrics()
        data = [0x01, cpu & 0xFF, ram & 0xFF]

        # Log constructed data
        data_hex = " ".join(f"0x{byte:02X}" for byte in data)
        self.log_status(f"Constructed Data: {data_hex}")

        self.send_raw_report(data)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dialog = MonitorDialog()
    dialog.show()
    sys.exit(app.exec())
