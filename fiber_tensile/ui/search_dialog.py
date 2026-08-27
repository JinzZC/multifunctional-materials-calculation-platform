"""全局搜索对话框。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..data.search import search_all


class GlobalSearchDialog(QDialog):
    navigate_requested = Signal(int)

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._results = []
        self.setWindowTitle("全局搜索")
        self.resize(820, 500)
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("输入样品名、批次名、备注或计算类型…")
        button = QPushButton("搜索")
        row.addWidget(self._query, 1)
        row.addWidget(button)
        root.addLayout(row)
        self._status = QLabel("可搜索纤维批次、接触角、单丝曲线和复合材料历史记录。")
        root.addWidget(self._status)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["模块", "名称", "说明", "创建时间"])
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        root.addWidget(self._table, 1)
        hint = QLabel("双击结果可切换到对应功能模块。")
        hint.setStyleSheet("color: #526579;")
        root.addWidget(hint)
        button.clicked.connect(self._search)
        self._query.returnPressed.connect(self._search)
        self._table.cellDoubleClicked.connect(self._open_result)
        self._query.setFocus()

    def _search(self) -> None:
        self._results = search_all(self._conn, self._query.text())
        self._table.setRowCount(len(self._results))
        for row, result in enumerate(self._results):
            for column, value in enumerate((
                    result.module, result.title, result.detail, result.created_at)):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, result.module_index)
                self._table.setItem(row, column, item)
        self._status.setText(f"找到 {len(self._results)} 条结果。")

    def _open_result(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._results):
            self.navigate_requested.emit(self._results[row].module_index)
            self.accept()
