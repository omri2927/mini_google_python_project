from PyQt6.QtWidgets import QApplication
from ui import main_window

# Create QApplication, show MainWindow, exec().
def main() -> None:
    app = QApplication([])
    window = main_window.MainWindow()

    window.show()
    app.exec()

if __name__ == "__main__":
    main()