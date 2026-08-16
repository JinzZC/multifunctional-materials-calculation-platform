"""可复用控件。"""

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDateEdit, QHBoxLayout, QPushButton, QWidget


class DateEditWithToday(QWidget):
    """测试日期输入框 + 「今天」快捷按钮（一键定位到今天）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.btn_today = QPushButton("今天")
        self.btn_today.setFixedWidth(52)
        self.btn_today.clicked.connect(
            lambda: self.date_edit.setDate(QDate.currentDate()))
        layout.addWidget(self.date_edit, 1)
        layout.addWidget(self.btn_today)

    # 兼容 QDateEdit 的常用接口
    def date(self) -> QDate:
        return self.date_edit.date()

    def setDate(self, d: QDate) -> None:
        self.date_edit.setDate(d)
