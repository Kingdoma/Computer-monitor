import sys
import os
import psutil
import hid
import win32pdh  # For Windows Performance Counters
from PySide6.QtWidgets import QApplication, QDialog, QSystemTrayIcon, QMenu, QMessageBox
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Slot, QTimer, Qt
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

        # Dynamically load the icon path
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, "monitoring.png")

        # Set the application window icon
        self.setWindowIcon(QIcon(icon_path))

        # Set the application window title
        self.setWindowTitle("computer monitor")

        # Enable minimize and close buttons
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)

        self.hid_interface = None

        # Initialize Windows Performance Counter for CPU
        self.cpu_query_handle = None
        self.cpu_counter_handle = None
        self.is_first_sample = True  # Equivalent to m_first_get_CPU_utility in C++
        self.initialize_cpu_counter()

        # Set up the timer for sending metrics every second
        self.timer = QTimer(self)
        self.timer.setInterval(1000)  # 1000 ms = 1 second
        self.timer.timeout.connect(self.send_system_metrics)

        # Connect UI buttons
        self.ui.connectBtm.clicked.connect(self.handle_connect)
        self.ui.disconnectBtm.clicked.connect(self.handle_disconnect)

        # Add tray icon and menu
        self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self)
        self.tray_menu = QMenu(self)

        self.show_action = QAction("Show", self)
        self.exit_action = QAction("Exit", self)

        self.show_action.triggered.connect(self.show_window)
        self.exit_action.triggered.connect(self.handle_exit)

        self.tray_menu.addAction(self.show_action)
        self.tray_menu.addAction(self.exit_action)
        self.tray_icon.setContextMenu(self.tray_menu)

        self.tray_icon.show()

        # Auto-connect on startup
        self.handle_connect()

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
        win32pdh.CollectQueryData(self.cpu_query_handle)
        _, formatted_value = win32pdh.GetFormattedCounterValue(
            self.cpu_counter_handle, win32pdh.PDH_FMT_DOUBLE
        )
        if self.is_first_sample:
            self.is_first_sample = False
            return 0
        return round(formatted_value)

    def get_hid_interface(self):
        device_interfaces = hid.enumerate(VENDOR_ID, PRODUCT_ID)
        raw_hid_interfaces = [
            i for i in device_interfaces
            if i["usage_page"] == USAGE_PAGE and i["usage"] == USAGE
        ]
        if not raw_hid_interfaces:
            return None
        return hid.Device(path=raw_hid_interfaces[0]["path"])

    @Slot()
    def handle_connect(self):
        """Handle connection to HID device."""
        if self.hid_interface is not None:
            self.log_status("Already connected.")
            return

        self.hid_interface = self.get_hid_interface()
        if self.hid_interface:
            self.log_status(f"Connected to device: {self.hid_interface.manufacturer} {self.hid_interface.product}")
            self.timer.start()
        else:
            self.log_status("No device found. Check if device is plugged in and correct VID/PID/usage values.")

    @Slot()
    def handle_disconnect(self):
        """Handle disconnection from HID device."""
        if self.hid_interface:
            self.timer.stop()
            self.hid_interface.close()
            self.hid_interface = None
            self.log_status("Disconnected from HID device.")
        else:
            self.log_status("No active connection to disconnect.")

    def get_system_metrics(self):
        """Fetch system metrics: CPU and RAM usage."""
        cpu_percent = self.get_cpu_usage()
        ram_percent = int(psutil.virtual_memory().percent)
        return cpu_percent, ram_percent

    def send_raw_report(self, data):
        """Send a HID report to the device and read the response."""
        if not self.hid_interface:
            self.log_status("Not connected to any device.")
            return

        request_data = [0x00] * (REPORT_LENGTH + 1)
        request_data[1 : len(data) + 1] = data
        request_report = bytes(request_data)
        self.hid_interface.write(request_report)
        response_report = self.hid_interface.read(REPORT_LENGTH, timeout=500)

        if response_report:
            res_hex = " ".join(f"0x{byte:02X}" for byte in response_report)
            self.log_status(f"Received: {res_hex}")
        else:
            self.log_status("No response received.")

    def send_system_metrics(self):
        """Send system metrics to the device."""
        if not self.hid_interface:
            return
        cpu, ram = self.get_system_metrics()
        data = [0x01, cpu & 0xFF, ram & 0xFF]
        self.send_raw_report(data)

    def show_window(self):
        """Show the main window."""
        self.show()
        self.raise_()

    def closeEvent(self, event):
        """Handle close button: minimize to tray or fully exit."""
        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            "Do you want to minimize to tray instead of exiting?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if reply == QMessageBox.Yes:
            # Minimize to tray
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Monitor",
                "Application minimized to tray. Use the tray menu to restore or exit.",
                QSystemTrayIcon.Information,
                3000,
            )
        else:
            # Fully close the application
            event.accept()
            self.handle_exit()

    @Slot()
    def handle_exit(self):
        """Exit the application."""
        self.tray_icon.hide()
        QApplication.quit()  # Cleanly exits the application



if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    dialog = MonitorDialog()
    dialog.show()
    sys.exit(app.exec())
