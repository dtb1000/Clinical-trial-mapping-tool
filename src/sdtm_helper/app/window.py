"""The SDTM Helper desktop window: a SAS editor and log on the left, the guide on the right."""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPointF, QRectF, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QKeySequence, QPainter, QPen, QSyntaxHighlighter,
                           QTextCharFormat)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                               QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QToolBar,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import __version__
from ..checks.engine import ERROR, NOTICE, WARNING, CheckReport
from ..guidance.engine import DomainGuide
from ..settings import CONNECTIONS, ODA_REGIONS, AppSettings, load_settings, save_settings
from ..sas.session import ColumnInfo, TableInfo
from .follow import FollowedTable, FollowResult
from .workspace import Preview, Workspace, available_domains

STATUS_COLOURS = {"done": "#2e7d32", "missing": "#c62828", "empty": "#c62828",
                  "partly empty": "#ef6c00", "optional": "#757575"}
SEVERITY_COLOURS = {ERROR: "#c62828", WARNING: "#ef6c00", NOTICE: "#1565c0"}
CORE_NAMES = {"Req": "Required", "Exp": "Expected", "Perm": "Permissible"}


# -- background work ------------------------------------------------------

class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    """Run a slow call (anything that talks to SAS) off the UI thread."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Signals()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as err:  # shown to the user, never swallowed
            self.signals.failed.emit(f"{type(err).__name__}: {err}")
        else:
            self.signals.done.emit(result)


# -- SAS editor -------------------------------------------------------------

class SasHighlighter(QSyntaxHighlighter):
    KEYWORDS = ("data set merge by if then else do end run quit proc sql select from where group order "
                "create table as left join on retain length format informat keep drop rename output "
                "libname filename %macro %mend %let %put %if %then %else %do %end label array by "
                "first last call symput input put upcase strip catx compress substr scan coalescec "
                "case when and or not in is null missing").split()

    def __init__(self, document):
        super().__init__(document)
        self.keyword = QTextCharFormat()
        self.keyword.setForeground(QColor("#1a4fa0"))
        self.keyword.setFontWeight(QFont.Bold)
        self.string = QTextCharFormat()
        self.string.setForeground(QColor("#8a2be2"))
        self.comment = QTextCharFormat()
        self.comment.setForeground(QColor("#2e7d32"))
        self.comment.setFontItalic(True)
        words = "|".join(re.escape(k) for k in self.KEYWORDS)
        self.word_re = re.compile(rf"(?<![\w%])({words})\b", re.IGNORECASE)

    def highlightBlock(self, text):
        for m in self.word_re.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.keyword)
        for m in re.finditer(r"'[^']*'|\"[^\"]*\"", text):
            self.setFormat(m.start(), m.end() - m.start(), self.string)
        for m in re.finditer(r"^\s*\*.*?;", text):
            self.setFormat(m.start(), m.end() - m.start(), self.comment)
        # /* ... */ comments, which may span lines
        self.setCurrentBlockState(0)
        start = 0 if self.previousBlockState() == 1 else text.find("/*")
        while start >= 0:
            end = text.find("*/", start + (0 if self.previousBlockState() == 1 and start == 0 else 2))
            if end < 0:
                self.setCurrentBlockState(1)
                length = len(text) - start
            else:
                length = end - start + 2
            self.setFormat(start, length, self.comment)
            start = text.find("/*", start + length)


def monospace() -> QFont:
    font = QFont("Consolas")
    font.setStyleHint(QFont.Monospace)
    font.setPointSize(10)
    return font


# -- table preview ------------------------------------------------------------

MARK = {"keep": "#dbe8f6", "rename": "#dbe8f6", "new": "#f1e4f5", "removed": "#f8dcd0"}
MARK_TEXT = {"keep": "#1565c0", "rename": "#1565c0", "new": "#7b1fa2", "drop": "#9e9e9e", "removed": "#a23a12"}
DATE_FORMATS = ("DATE", "YYMMDD", "E8601", "IS8601", "DATETIME", "DDMMYY", "MMDDYY", "TIME")


def _empty(value) -> bool:
    return value is None or (isinstance(value, float) and value != value) or str(value).strip() in ("", "<NA>", "nan", "NaT")


class DataFrameModel(QAbstractTableModel):
    """Shows the first rows of a SAS table. SDTM columns get their label and Core in the tooltip;
    empty values in Required columns are shaded so they stand out.

    When it shows a table the step under the cursor reads (a FollowedTable), it also marks what
    the step does, like SQLens: blue columns reach the output, grey ones are dropped, purple ones
    are new and already filled in, and struck-through rows are removed by WHERE or IF."""

    def __init__(self):
        super().__init__()
        self.df = None
        self.spec = None
        self.labels: dict[str, str] = {}
        self.followed: FollowedTable | None = None

    def set_data(self, df, spec, labels, followed: FollowedTable | None = None):
        self.beginResetModel()
        self.df, self.spec, self.labels, self.followed = df, spec, labels, followed
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if self.df is None else len(self.df)

    def columnCount(self, parent=QModelIndex()):
        return 0 if self.df is None else len(self.df.columns)

    def _var(self, col):
        return self.spec.variable(str(self.df.columns[col])) if self.spec else None

    def _status(self, col) -> str:
        return self.followed.status.get(str(self.df.columns[col]).upper(), "") if self.followed else ""

    def _removed(self, row) -> bool:
        f = self.followed
        return f is not None and f.kept_rows is not None and row not in f.kept_rows

    def data(self, index, role=Qt.DisplayRole):
        if self.df is None or not index.isValid():
            return None
        value = self.df.iat[index.row(), index.column()]
        empty = _empty(value)
        removed, status = self._removed(index.row()), self._status(index.column())
        if role == Qt.DisplayRole:
            if empty:
                return ""
            if isinstance(value, float) and value.is_integer():
                return str(int(value))
            return str(value)
        if role == Qt.BackgroundRole:
            if removed:
                return QColor(MARK["removed"])
            if empty and (self.followed is None or self.followed.role == "output"):
                var = self._var(index.column())
                if var is not None and var.core == "Req":
                    return QColor("#ffcdd2")
            if status in MARK:
                return QColor(MARK[status])
        if role == Qt.ForegroundRole:
            if removed:
                return QColor(MARK_TEXT["removed"])
            if status == "drop":
                return QColor(MARK_TEXT["drop"])
        if role == Qt.FontRole and removed:
            font = monospace()
            font.setStrikeOut(True)
            return font
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if self.df is None:
            return None
        if orientation == Qt.Vertical:
            if role == Qt.DisplayRole:
                return f"✕ {section + 1}" if self._removed(section) else str(section + 1)
            if role == Qt.ForegroundRole and self._removed(section):
                return QColor(MARK_TEXT["removed"])
            if role == Qt.ToolTipRole and self.followed and self.followed.kept_rows is not None:
                return "Removed by your WHERE or IF" if self._removed(section) else "Reaches the output"
            return None
        name = str(self.df.columns[section])
        var = self._var(section)
        words = self.followed.words.get(name.upper(), []) if self.followed else []
        status = self._status(section)
        if role == Qt.DisplayRole:
            return name + ("\n" + " · ".join(words) if words else "")
        if role == Qt.ToolTipRole:
            label = self.labels.get(name.upper(), "")
            if var is None:
                text = f"{name} {('– ' + label) if label else ''}\nNot a {self.spec.code} variable" if self.spec else name
            else:
                text = f"{name} – {var.label}\n{CORE_NAMES.get(var.core, var.core)}, {var.datatype}"
            formula = self.followed.formulas.get(name.upper()) if self.followed else None
            return (text + ("\nYour step: " + ", ".join(words) if words else "")
                    + (f"\n{name} = {formula}" if formula else ""))
        if role == Qt.ForegroundRole:
            if status in MARK_TEXT:
                return QColor(MARK_TEXT[status])
            if self.followed is None or self.followed.role == "output":
                if var is None:
                    return QColor("#9e9e9e")
                return QColor("#c62828") if var.core == "Req" else None
        if role == Qt.BackgroundRole and status in MARK:
            return QColor(MARK[status])
        return None


def holds(col: ColumnInfo) -> str:
    """A column's type in plain words, as SQLens's Details view does."""
    if col.type.lower().startswith("char"):
        return f"text, up to {col.length} character{'s' if col.length != 1 else ''}"
    fmt = (col.format or "").upper()
    if fmt.startswith(DATE_FORMATS):
        return f"a SAS date or time (a number shown with {col.format}); SDTM needs ISO 8601 text"
    return "number"


def sdtm_note(col: ColumnInfo, spec) -> str:
    var = spec.variable(col.name) if spec else None
    if var is None:
        return f"Not a {spec.code} variable" if spec else ""
    notes = [CORE_NAMES.get(var.core, var.core)]
    wants_text = var.datatype.lower().startswith("char")
    if wants_text and not col.type.lower().startswith("char"):
        notes.append("should be text")
    if not wants_text and col.type.lower().startswith("char"):
        notes.append("should be a number")
    if col.label and col.label.strip().lower() != var.label.lower():
        notes.append(f"label should be '{var.label}'")
    elif not col.label:
        notes.append(f"no label yet ('{var.label}')")
    return "; ".join(notes)


class TablePreview(QWidget):
    """The tables beside the SAS code. With Follow my code ticked it shows the tables the step
    under the cursor reads and makes, marked the way SQLens marks a query; otherwise any table."""
    table_changed = Signal(str)

    LEGEND = (f'<span style="background:{MARK["keep"]};color:{MARK_TEXT["keep"]}">&nbsp;SEX&nbsp;</span> reaches the output'
              f' &nbsp; <span style="color:{MARK_TEXT["drop"]}">&nbsp;AGE&nbsp;</span> dropped'
              f' &nbsp; <span style="background:{MARK["new"]};color:{MARK_TEXT["new"]}">&nbsp;USUBJID&nbsp;</span> new column you are building'
              f' &nbsp; <span style="background:{MARK["removed"]};color:{MARK_TEXT["removed"]}"><s>&nbsp;002&nbsp;</s></span> row removed by WHERE or IF')

    def __init__(self):
        super().__init__()
        self.followed: list[FollowedTable] = []
        self.spec = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        row.addWidget(QLabel("<b>Tables</b>"))
        self.follow = QCheckBox("Follow my code")
        self.follow.setChecked(True)
        self.follow.setToolTip("Show the tables the step under your cursor reads and makes, a moment after you stop typing.\n"
                               "A copy of your step runs on the first rows in WORK; your own tables are never changed.")
        row.addWidget(self.follow)
        row.addStretch(1)
        row.addWidget(QLabel("Show"))
        self.rows = QComboBox()
        for n in (100, 200, 500, 1000):
            self.rows.addItem(f"{n} rows", n)
        self.rows.setCurrentIndex(1)
        row.addWidget(self.rows)
        row.addWidget(QLabel(" Any table"))
        self.picker = QComboBox()
        self.picker.setEditable(True)
        self.picker.setMinimumWidth(150)
        self.picker.lineEdit().returnPressed.connect(lambda: self.table_changed.emit(self.picker.currentText()))
        self.picker.activated.connect(lambda _i: self.table_changed.emit(self.picker.currentText()))
        row.addWidget(self.picker, 1)
        lay.addLayout(row)
        self.title = QLabel()
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.info = QLabel("Connect to SAS to see your tables here.")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)

        from PySide6.QtWidgets import QTableView
        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.setMinimumWidth(150)
        self.list.setMaximumWidth(170)
        self.list.currentRowChanged.connect(self._show_followed)
        split.addWidget(self.list)
        self.tabs = QTabWidget()
        self.view = QTableView()
        self.model = DataFrameModel()
        self.view.setModel(self.model)
        self.view.setFont(monospace())
        self.view.horizontalHeader().setDefaultSectionSize(110)
        self.view.verticalHeader().setDefaultSectionSize(20)
        self.tabs.addTab(self.view, "Rows")
        self.details = QTableWidget(0, 6)
        self.details.setHorizontalHeaderLabels(["Variable", "What it holds", "Length", "Label", "Format", "SDTMIG"])
        self.details.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.details.verticalHeader().setVisible(False)
        self.details.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabs.addTab(self.details, "Details")
        split.addWidget(self.tabs)
        split.setSizes([160, 640])
        lay.addWidget(split, 1)
        self.legend = QLabel(self.LEGEND)
        self.legend.setWordWrap(True)
        lay.addWidget(self.legend)

    def set_tables(self, tables: list[str], current: str):
        self.picker.blockSignals(True)
        self.picker.clear()
        self.picker.addItems(tables)
        self.picker.setCurrentText(current)
        self.picker.blockSignals(False)

    # one table, not following
    def show_preview(self, preview: Preview | None, spec, table: str):
        self.spec = spec
        self.followed = []
        self.list.clear()
        self.list.hide()
        self.legend.hide()
        self.title.setText(f"<b>{html.escape(table or '')}</b>")
        if preview is None:
            self.model.set_data(None, spec, {})
            self.details.setRowCount(0)
            self.info.setText(f"{table or 'The table'} doesn't exist yet. Run your program to create it.")
            return
        labels = {c.name.upper(): c.label for c in preview.info.columns}
        self.model.set_data(preview.rows, spec, labels)
        self._fill_details(preview.info)
        shown = f"first {preview.shown} of " if preview.shown < preview.info.nobs else ""
        self.info.setText(f"Showing {shown}{preview.info.nobs} rows, "
                          f"{len(preview.info.columns)} variables. Red headers are Required; "
                          "shaded cells are empty Required values; grey headers aren't in the domain.")
        self.view.resizeColumnsToContents()

    # following the step under the cursor
    def show_message(self, text: str, error: bool = False):
        colour = "#a23a12" if error else "#616161"
        self.info.setText(f'<span style="color:{colour}">{html.escape(text)}</span>')

    def show_follow(self, result: FollowResult, spec):
        self.spec = spec
        self.title.setText(f"<b>{html.escape(result.title)}</b>" if result.title else "")
        if result.message:              # keep the last good tables on screen, as SQLens does
            self.show_message(result.message, result.error)
            return
        keep = self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None
        self.followed = result.tables
        self.list.blockSignals(True)
        self.list.clear()
        for t in result.tables:
            note = "read by this step" if t.role == "input" else "made by this step (preview)"
            item = QListWidgetItem(f"{t.name}\n  {note}")
            item.setData(Qt.UserRole, (t.role, t.name))
            if t.role == "output":
                item.setForeground(QColor(MARK_TEXT["new"]))
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.list.show()
        self.legend.show()
        index = next((i for i, t in enumerate(result.tables) if (t.role, t.name) == keep), 0)
        self.list.setCurrentRow(index)
        self._show_followed(index)

    def _show_followed(self, index: int):
        if not (0 <= index < len(self.followed)):
            return
        t = self.followed[index]
        labels = {c.name.upper(): c.label for c in t.info.columns} if t.info else {}
        self.model.set_data(t.rows, self.spec, labels, t)
        colours = {"removed": MARK_TEXT["removed"], "kept": "#2e7d32", "keep": MARK_TEXT["keep"], "new": MARK_TEXT["new"]}
        parts = []
        for text, mark in t.summary:
            if mark in colours:
                parts.append(f'<span style="text-decoration:underline;text-decoration-color:{colours[mark]};'
                             f'color:{colours[mark]}">{html.escape(text)}</span>')
            else:
                parts.append(html.escape(text))
        self.info.setText("".join(parts))
        if t.info:
            self._fill_details(t.info)
        self.view.resizeColumnsToContents()
        for c in range(self.model.columnCount()):       # long notes are in the tooltip
            self.view.setColumnWidth(c, min(self.view.columnWidth(c), 140))

    def _fill_details(self, info: TableInfo):
        self.details.setRowCount(len(info.columns))
        for r, col in enumerate(info.columns):
            name = col.name if not col.name.lower().startswith("_sdtmh_") else ""
            cells = [col.name, holds(col), str(col.length), col.label, col.format, sdtm_note(col, self.spec)]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 5 and ("should" in text or text.startswith("Not a")):
                    item.setForeground(QColor("#ef6c00"))
                self.details.setItem(r, c, item)
            self.details.setRowHidden(r, not name)
        self.details.resizeColumnsToContents()


# -- workflow chart -----------------------------------------------------------

class WorkflowChart(QWidget):
    """The domain's workflow as boxes and arrows. Click a box to mark the step done or not done."""
    toggled = Signal(str, bool)

    BOX_W, BOX_H, GAP_X, GAP_Y = 190, 46, 24, 30

    def __init__(self):
        super().__init__()
        self.guide: DomainGuide | None = None
        self.done: set[str] = set()
        self.boxes: dict[str, QRectF] = {}
        self.setMinimumHeight(200)

    def set_guide(self, guide: DomainGuide, done: set[str]):
        self.guide, self.done = guide, set(done)
        self._layout()
        self.update()

    def _layout(self):
        self.boxes.clear()
        if not self.guide:
            return
        depth: dict[str, int] = {}
        for step in self.guide.workflow:          # steps are listed in dependency order
            depth[step.id] = max([depth.get(p, 0) + 1 for p in step.after] or [0])
        levels: dict[int, list[str]] = {}
        for sid, d in depth.items():
            levels.setdefault(d, []).append(sid)
        width = max(len(v) for v in levels.values()) * (self.BOX_W + self.GAP_X)
        for d, ids in levels.items():
            row_w = len(ids) * (self.BOX_W + self.GAP_X) - self.GAP_X
            x0 = (width - row_w) / 2 + 10
            for i, sid in enumerate(ids):
                self.boxes[sid] = QRectF(x0 + i * (self.BOX_W + self.GAP_X), 10 + d * (self.BOX_H + self.GAP_Y),
                                         self.BOX_W, self.BOX_H)
        self.setMinimumSize(int(width + 20), int(20 + len(levels) * (self.BOX_H + self.GAP_Y)))

    def paintEvent(self, _event):
        if not self.guide:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        nxt = {s.id for s in self.guide.next_steps(self.done)}
        p.setPen(QPen(QColor("#90a4ae"), 1.5))
        for step in self.guide.workflow:
            for parent in step.after:
                a, b = self.boxes[parent], self.boxes[step.id]
                start, end = QPointF(a.center().x(), a.bottom()), QPointF(b.center().x(), b.top())
                p.drawLine(start, end)
                p.drawLine(end, end + QPointF(-4, -7))
                p.drawLine(end, end + QPointF(4, -7))
        for i, step in enumerate(self.guide.workflow, 1):
            r = self.boxes[step.id]
            if step.id in self.done:
                fill, border = QColor("#e8f5e9"), QColor("#2e7d32")
            elif step.id in nxt:
                fill, border = QColor("#e3f2fd"), QColor("#1565c0")
            else:
                fill, border = QColor("#fafafa"), QColor("#b0bec5")
            p.setBrush(fill)
            p.setPen(QPen(border, 2 if step.id in nxt else 1.2))
            p.drawRoundedRect(r, 8, 8)
            p.setPen(QColor("#212121"))
            mark = "✓ " if step.id in self.done else ""
            p.drawText(r.adjusted(8, 0, -8, 0), Qt.AlignCenter | Qt.TextWordWrap, f"{mark}{i}. {step.title}")

    def mousePressEvent(self, event):
        for sid, rect in self.boxes.items():
            if rect.contains(event.position()):
                self.toggled.emit(sid, sid not in self.done)
                return


# -- dialogs ------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connection settings")
        self.settings = settings
        form = QFormLayout(self)
        self.connection = QComboBox()
        for key, label in CONNECTIONS.items():
            self.connection.addItem(label, key)
        self.connection.setCurrentIndex(list(CONNECTIONS).index(settings.connection))
        self.region = QComboBox()
        self.region.addItems(list(ODA_REGIONS))
        self.region.setCurrentText(settings.oda_region)
        self.user = QLineEdit(settings.oda_user)
        self.user.setPlaceholderText("Your ODA user ID or email")
        self.java = QLineEdit(settings.java_path)
        java_btn = QPushButton("Browse…")
        java_btn.clicked.connect(lambda: self._browse(self.java, "Java (java.exe)", "java*"))
        java_row = QHBoxLayout()
        java_row.addWidget(self.java)
        java_row.addWidget(java_btn)
        self.autoexec = QLineEdit(settings.autoexec)
        self.autoexec.setPlaceholderText("Optional: your libname program, run after connecting")
        auto_btn = QPushButton("Browse…")
        auto_btn.clicked.connect(lambda: self._browse(self.autoexec, "SAS programs", "*.sas"))
        auto_row = QHBoxLayout()
        auto_row.addWidget(self.autoexec)
        auto_row.addWidget(auto_btn)
        form.addRow("Connect to", self.connection)
        form.addRow("ODA home region", self.region)
        form.addRow("ODA user ID", self.user)
        form.addRow("Java", java_row)
        form.addRow("Run at start", auto_row)
        form.addRow(QLabel("Your ODA password is asked when you connect and is never saved."))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.connection.currentIndexChanged.connect(self._toggle_oda)
        self._toggle_oda()

    def _toggle_oda(self):
        oda = self.connection.currentData() == "oda"
        self.region.setEnabled(oda)
        self.user.setEnabled(oda)

    def _browse(self, field: QLineEdit, title: str, pattern: str):
        path, _ = QFileDialog.getOpenFileName(self, title, field.text(), f"{title} ({pattern});;All files (*)")
        if path:
            field.setText(path)

    def result_settings(self) -> AppSettings:
        s = self.settings
        s.connection = self.connection.currentData()
        s.oda_region = self.region.currentText()
        s.oda_user = self.user.text().strip()
        s.java_path = self.java.text().strip()
        s.autoexec = self.autoexec.text().strip()
        return s


class PasswordDialog(QDialog):
    def __init__(self, user: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sign in to SAS OnDemand")
        form = QFormLayout(self)
        self.user = QLineEdit(user)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        form.addRow("User ID", self.user)
        form.addRow("Password", self.password)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


# -- main window ----------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"SDTM Helper {__version__}")
        self.resize(1600, 900)
        self.pool = QThreadPool.globalInstance()
        self.settings = load_settings()
        self.sas = None
        self.ws: Workspace | None = None
        self._build_toolbar()
        self._build_body()
        self.statusBar().showMessage("Not connected to SAS. Click Connect.")
        self.study.setText(self.settings.last_study or "MYSTUDY")
        idx = self.domain.findData(self.settings.last_domain or "DM")
        self.domain.setCurrentIndex(max(idx, 0))
        self.open_workspace()

    # layout
    def _build_toolbar(self):
        bar = QToolBar("Main")
        bar.setMovable(False)
        self.addToolBar(bar)
        bar.addWidget(QLabel(" Study "))
        self.study = QLineEdit()
        self.study.setFixedWidth(110)
        self.study.editingFinished.connect(self.open_workspace)
        bar.addWidget(self.study)
        bar.addWidget(QLabel("  Domain "))
        self.domain = QComboBox()
        for code, label in available_domains():
            self.domain.addItem(f"{code} – {label}", code)
        self.domain.setMinimumWidth(260)
        self.domain.currentIndexChanged.connect(self.open_workspace)
        bar.addWidget(self.domain)
        bar.addWidget(QLabel("  Building table "))
        self.table = QLineEdit()
        self.table.setPlaceholderText("e.g. FINAL.DM")
        self.table.setFixedWidth(130)
        bar.addWidget(self.table)
        bar.addSeparator()

        def action(text, slot, shortcut=None, tip=""):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setToolTip(tip or text)
            bar.addAction(a)
            return a

        self.connect_action = action("Connect", self.connect_sas, tip="Connect to SAS")
        action("Run ▶", self.run_program, "F3", "Submit the program (or the selected lines) to SAS  [F3]")
        action("Refresh checklist", self.refresh, "F5", "Compare your table with the domain  [F5]")
        action("Run checks", self.run_checks, "F6", "P21-lite checks on your table  [F6]")
        bar.addSeparator()
        action("Open .sas", self.open_file, "Ctrl+O")
        action("Export .sas", self.export_file)
        action("Save", self.save, "Ctrl+S", "Save your program and progress  [Ctrl+S]")
        action("Settings", self.edit_settings)
        bar.addSeparator()
        self.guide_toggle = action("Hide guide", self.toggle_guide, "F9", "Show or hide the guide panel  [F9]")

    def _build_body(self):
        left = QSplitter(Qt.Vertical)
        top = QSplitter(Qt.Horizontal)
        self.editor = QPlainTextEdit()
        self.editor.setFont(monospace())
        self.editor.setTabStopDistance(32)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.highlighter = SasHighlighter(self.editor.document())
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(monospace())
        self.log.setPlaceholderText("SAS log")
        self.preview = TablePreview()
        self.preview.table_changed.connect(self._pick_table)
        self.preview.follow.toggled.connect(self._follow_toggled)
        self.preview.rows.currentIndexChanged.connect(lambda _i: self.follow_now())
        self.follow_timer = QTimer(self)
        self.follow_timer.setSingleShot(True)
        self.follow_timer.setInterval(1200)
        self.follow_timer.timeout.connect(self.follow_now)
        self.editor.textChanged.connect(self._editor_changed)
        self.editor.cursorPositionChanged.connect(self._cursor_moved)
        self.busy = False
        self.following = False      # a follow run is in progress
        self.follow_again = False
        self.followed_step = (-1, -1)
        top.addWidget(self._titled("Your SAS program", self.editor))
        top.addWidget(self.preview)
        top.setSizes([520, 680])
        left.addWidget(top)
        left.addWidget(self._titled("Log", self.log))
        left.setSizes([600, 220])

        self.tabs = QTabWidget()
        # Guide tab
        guide = QWidget()
        g = QVBoxLayout(guide)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.variables = QListWidget()
        self.variables.currentItemChanged.connect(self.show_variable)
        self.explain = QTextBrowser()
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.variables)
        split.addWidget(self.explain)
        split.setSizes([300, 260])
        g.addWidget(self.summary)
        g.addWidget(split)
        self.tabs.addTab(guide, "Guide")
        # Checklist tab
        check = QWidget()
        c = QVBoxLayout(check)
        self.checklist_summary = QLabel()
        self.show_perm = QCheckBox("Show permissible variables")
        self.show_perm.toggled.connect(self.fill_checklist)
        self.checklist = QTableWidget(0, 4)
        self.checklist.setHorizontalHeaderLabels(["Status", "Variable", "Core", "What to do"])
        self.checklist.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.checklist.verticalHeader().setVisible(False)
        self.checklist.setEditTriggers(QTableWidget.NoEditTriggers)
        self.checklist.cellDoubleClicked.connect(self._checklist_to_guide)
        c.addWidget(self.checklist_summary)
        c.addWidget(self.show_perm)
        c.addWidget(self.checklist)
        self.tabs.addTab(check, "Checklist")
        # Workflow tab
        flow = QWidget()
        f = QVBoxLayout(flow)
        self.next_step = QLabel()
        self.next_step.setWordWrap(True)
        self.chart = WorkflowChart()
        self.chart.toggled.connect(self.toggle_step)
        f.addWidget(QLabel("Click a step to mark it done. Blue = do next, green = done."))
        f.addWidget(self.chart, 1)
        f.addWidget(self.next_step)
        self.tabs.addTab(flow, "Workflow")
        # Checks tab
        checks = QWidget()
        k = QVBoxLayout(checks)
        self.checks_summary = QLabel("Run the checks (F6) when the domain is finished.")
        self.checks_summary.setWordWrap(True)
        self.dm_table = QLineEdit()
        self.dm_table.setPlaceholderText("Your DM table for cross-domain checks, e.g. FINAL.DM")
        self.findings = QTreeWidget()
        self.findings.setHeaderLabels(["Severity", "Check", "Message"])
        self.findings.header().setSectionResizeMode(2, QHeaderView.Stretch)
        k.addWidget(self.checks_summary)
        k.addWidget(self.dm_table)
        k.addWidget(self.findings)
        self.tabs.addTab(checks, "Checks")

        body = QSplitter(Qt.Horizontal)
        body.addWidget(left)
        body.addWidget(self.tabs)
        body.setSizes([1080, 480])
        self.setCentralWidget(body)

    @staticmethod
    def _titled(title: str, widget: QWidget) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)
        label = QLabel(f"<b>{title}</b>")
        lay.addWidget(label)
        lay.addWidget(widget)
        return box

    # workspace
    def open_workspace(self):
        study = self.study.text().strip() or "MYSTUDY"
        domain = self.domain.currentData() or "DM"
        if self.ws and (self.ws.study, self.ws.domain) == (study, domain):
            return
        if self.ws:
            self.ws.save(self.editor.toPlainText(), self.table.text())
        self.ws = Workspace(study, domain, sas=self.sas)
        self.editor.setPlainText(self.ws.program)
        self.table.setText(self.ws.state.target_table or f"FINAL.{domain}")
        self.preview.picker.setCurrentText(self.table.text())
        if self.sas is not None:
            self.update_tables()
        else:
            self.follow_now()
        self.settings.last_study, self.settings.last_domain = study, domain
        save_settings(self.settings)
        self.findings.clear()
        self.checks_summary.setText("Run the checks (F6) when the domain is finished.")
        self.show_guide(self.ws.guide)

    def show_guide(self, guide: DomainGuide):
        spec = self.ws.spec
        self.summary.setText(f"<b>{spec.code} – {spec.label}</b> ({spec.structure}). {html.escape(guide.summary)}")
        self.variables.clear()
        for v in spec.variables:
            item = QListWidgetItem(f"{v.name:<9} {CORE_NAMES.get(v.core, v.core):<12} {v.label}")
            item.setFont(monospace())
            item.setData(Qt.UserRole, v.name)
            if v.core == "Req":
                item.setForeground(QColor("#c62828"))
            elif v.core == "Perm":
                item.setForeground(QColor("#757575"))
            self.variables.addItem(item)
        self.variables.setCurrentRow(0)
        self.fill_checklist()
        self.chart.set_guide(guide, self.ws.done)
        self.update_next_step()

    def show_variable(self, item):
        if not item or not self.ws:
            return
        text = self.ws.guide.explain(item.data(Qt.UserRole), self.ws.spec)
        lines = text.split("\n")
        body = "".join(f"<p>{html.escape(l)}</p>" for l in lines[1:])
        self.explain.setHtml(f"<h3>{html.escape(lines[0])}</h3>{body}")

    def _checklist_to_guide(self, row, _col):
        name = self.checklist.item(row, 1).text()
        for i in range(self.variables.count()):
            if self.variables.item(i).data(Qt.UserRole) == name:
                self.variables.setCurrentRow(i)
                self.tabs.setCurrentIndex(0)
                return

    def fill_checklist(self):
        if not self.ws:
            return
        items = [i for i in self.ws.guide.checklist if self.show_perm.isChecked() or i.status != "optional"]
        self.checklist.setRowCount(len(items))
        for row, item in enumerate(items):
            status = QTableWidgetItem(item.status)
            status.setForeground(QColor(STATUS_COLOURS[item.status]))
            self.checklist.setItem(row, 0, status)
            self.checklist.setItem(row, 1, QTableWidgetItem(item.variable))
            self.checklist.setItem(row, 2, QTableWidgetItem(item.core))
            self.checklist.setItem(row, 3, QTableWidgetItem(item.detail or item.label))
        self.checklist.resizeColumnsToContents()
        todo = sum(1 for i in self.ws.guide.checklist if i.needs_action)
        self.checklist_summary.setText(f"{todo} item(s) need action. Double-click a row to read about the variable.")

    def update_next_step(self):
        nxt = self.ws.guide.next_steps(self.ws.done)
        if nxt:
            vars_ = f" Variables: {', '.join(nxt[0].variables)}." if nxt[0].variables else ""
            self.next_step.setText(f"<b>Next: {html.escape(nxt[0].title)}.</b> {html.escape(nxt[0].detail)}{vars_}")
        else:
            self.next_step.setText("<b>All steps done.</b>")

    def toggle_step(self, step_id: str, done: bool):
        self.ws.toggle_step(step_id, done)
        self.chart.set_guide(self.ws.guide, self.ws.done)
        self.update_next_step()

    # SAS
    def _background(self, fn, on_done, message: str, *args):
        self.statusBar().showMessage(message)
        QApplication.setOverrideCursor(Qt.BusyCursor)
        task = Task(fn, *args)

        def finish(result):
            QApplication.restoreOverrideCursor()
            on_done(result)

        def fail(err):
            self.busy = False
            QApplication.restoreOverrideCursor()
            self.statusBar().showMessage("Failed.")
            QMessageBox.warning(self, "SDTM Helper", err)

        task.signals.done.connect(finish)
        task.signals.failed.connect(fail)
        self.pool.start(task)

    def connect_sas(self):
        if not self.settings.java_path and self.settings.connection == "oda":
            QMessageBox.information(self, "SDTM Helper", "First tell the app where Java is, in Settings.")
            self.edit_settings()
            return
        save_settings(self.settings)
        login = {}
        if self.settings.connection == "oda" and not _has_authinfo():
            dlg = PasswordDialog(self.settings.oda_user, self)
            if dlg.exec() != QDialog.Accepted:
                return
            login = {"omruser": dlg.user.text().strip(), "omrpw": dlg.password.text()}

        def work():
            from ..sas.session import SasConnection
            sas = SasConnection(cfgname=self.settings.connection, cfgfile=str(self.settings.cfgfile), **login)
            log = sas.run_file(self.settings.autoexec) if self.settings.autoexec else ""
            return sas, log

        def done(result):
            self.sas, log = result
            self.ws.sas = self.sas
            if log:
                self.show_log(log)
            self.statusBar().showMessage(f"Connected to SAS {self.sas.version} ({CONNECTIONS[self.settings.connection]}).")
            self.connect_action.setText("Connected")
            self.refresh()
            self.update_tables()

        self._background(work, done, "Connecting to SAS…")

    def run_program(self):
        if not self._need_sas():
            return
        cursor = self.editor.textCursor()
        code = cursor.selectedText().replace(" ", "\n") or self.editor.toPlainText()
        self.ws.save(self.editor.toPlainText(), self.table.text())

        def done(log):
            self.busy = False
            self.show_log(log)
            self.statusBar().showMessage("Program finished. Refreshing the table and checklist…")
            self.refresh()
            self.update_tables()

        self.busy = True
        self._background(self.ws.submit, done, "Running your program in SAS…", code)

    # live table preview
    def load_preview(self, table: str | None = None):
        if self.sas is None or not self.ws:
            return
        table = (table or self.preview.picker.currentText() or self.table.text()).strip()

        def work():
            return self.ws.tables(("WORK",)), self.ws.preview(table)

        def done(result):
            tables, preview = result
            if table.upper() not in tables and "." in table:
                tables = [table.upper(), *tables]
            self.preview.set_tables(tables, table.upper())
            self.preview.show_preview(preview, self.ws.spec, table.upper())

        self._background(work, done, f"Reading {table}…")

    def update_tables(self):
        """After connecting or running: follow the code, or reload the table being shown."""
        if self.preview.follow.isChecked():
            self.follow_now()
            self._list_tables()
        else:
            self.load_preview()

    def _list_tables(self):
        if self.sas is None or not self.ws:
            return
        current = self.preview.picker.currentText() or self.table.text()
        self._quiet(lambda: self.ws.tables(("WORK",)), lambda tables: self.preview.set_tables(tables, current))

    def _pick_table(self, table: str):
        self.preview.follow.blockSignals(True)
        self.preview.follow.setChecked(False)
        self.preview.follow.blockSignals(False)
        self._mark_step(None)
        self.load_preview(table)

    def _follow_toggled(self, on: bool):
        if on:
            self.follow_now()
        else:
            self._mark_step(None)
            self.load_preview()

    def _editor_changed(self):
        if self.preview.follow.isChecked() and self.sas is not None:
            self.follow_timer.start()

    def _cursor_moved(self):
        """Moving into another step follows that step straight away (typing waits for a pause)."""
        if not self.preview.follow.isChecked() or self.sas is None or self.follow_timer.isActive():
            return
        from ..sas.program import step_at
        step = step_at(self.editor.toPlainText(), self.editor.textCursor().position())
        if step is not None and (step.start, step.end) != self.followed_step:
            self.follow_timer.start(300)

    def follow_now(self):
        if not self.ws or not self.preview.follow.isChecked():
            return
        if self.sas is None:
            self.preview.show_message("Connect to SAS to follow your code: the tables your step reads and makes "
                                      "will show here as you type.")
            return
        if self.following or self.busy:
            self.follow_again = True
            return
        self.follow_timer.setInterval(1200)
        program, pos = self.editor.toPlainText(), self.editor.textCursor().position()
        rows = self.preview.rows.currentData() or 200
        self.following = True
        self.preview.show_message("Following your step…")

        def done(result):
            self.following = False
            self.preview.show_follow(result, self.ws.spec)
            self._mark_step(result if not result.message or result.error else None)
            if self.follow_again:
                self.follow_again = False
                self.follow_now()

        def failed(err):
            self.following = False
            self.preview.show_message(f"Couldn't follow this step: {err.splitlines()[-1] if err else ''}", True)

        self._quiet(lambda: self.ws.follow(program, pos, rows), done, failed)

    def _mark_step(self, result):
        """Shade the step being followed in the editor."""
        from PySide6.QtGui import QTextCursor
        from PySide6.QtWidgets import QTextEdit
        if result is None or result.step_start < 0:
            self.followed_step = (-1, -1)
            self.editor.setExtraSelections([])
            return
        self.followed_step = (result.step_start, result.step_end)
        sel = QTextEdit.ExtraSelection()
        cursor = QTextCursor(self.editor.document())
        text = self.editor.toPlainText()
        start = result.step_start + (len(text[result.step_start:result.step_end])
                                     - len(text[result.step_start:result.step_end].lstrip()))
        cursor.setPosition(min(start, len(text)))
        cursor.setPosition(min(result.step_end, len(text)), QTextCursor.KeepAnchor)
        sel.cursor = cursor
        sel.format.setBackground(QColor("#f2f7fd"))
        self.editor.setExtraSelections([sel])

    def _quiet(self, fn, on_done, on_fail=None):
        """Background work with no busy cursor or pop-ups, for things that happen while you type."""
        task = Task(fn)
        task.signals.done.connect(on_done)
        task.signals.failed.connect(on_fail or (lambda _e: None))
        self.pool.start(task)

    def toggle_guide(self):
        visible = not self.tabs.isVisible()
        self.tabs.setVisible(visible)
        self.guide_toggle.setText("Hide guide" if visible else "Show guide")

    def show_log(self, log: str):
        self.log.clear()
        for line in log.splitlines():
            colour = ("#c62828" if line.startswith("ERROR") else "#1b5e20" if line.startswith("WARNING")
                      else "#1565c0" if line.startswith("NOTE") else "#212121")
            self.log.appendHtml(f'<span style="color:{colour}">{html.escape(line) or "&nbsp;"}</span>')
        errors = sum(1 for l in log.splitlines() if l.startswith("ERROR"))
        if errors:
            self.statusBar().showMessage(f"The log has {errors} ERROR line(s).")

    def refresh(self):
        if not self.ws:
            return
        if self.sas is None:
            self.show_guide(self.ws.guide)
            return

        def done(guide):
            self.show_guide(guide)
            self.statusBar().showMessage("Checklist updated.")

        self._background(self.ws.refresh, done, "Reading your table…", self.table.text())

    def run_checks(self):
        if not self._need_sas():
            return
        self.ws.save(self.editor.toPlainText(), self.table.text())
        self._background(self.ws.run_checks, self.show_report, "Running P21-lite checks…",
                         self.table.text(), self.dm_table.text() or None)

    def show_report(self, report: CheckReport):
        self.tabs.setCurrentIndex(3)
        self.findings.clear()
        for f in report.findings:
            row = QTreeWidgetItem([f.severity, f.check, f.message])
            row.setForeground(0, QColor(SEVERITY_COLOURS[f.severity]))
            for extra in ([f"e.g. {'; '.join(f.examples)}"] if f.examples else []) + ([f"Fix: {f.fix}"] if f.fix else []):
                row.addChild(QTreeWidgetItem(["", "", extra]))
            self.findings.addTopLevelItem(row)
        self.findings.expandAll()
        e, w, n = (len(report.by_severity(s)) for s in (ERROR, WARNING, NOTICE))
        verdict = ("No errors: ready to export to XPT, then run Pinnacle 21." if report.passed
                   else "Fix the errors and run the checks again.")
        self.checks_summary.setText(f"<b>{report.domain}, {report.nobs} records: {e} error(s), {w} warning(s), "
                                    f"{n} notice(s).</b> {verdict}")
        self.chart.set_guide(self.ws.guide, self.ws.done)
        self.update_next_step()
        self.statusBar().showMessage("Checks finished.")

    def _need_sas(self) -> bool:
        if self.sas is None:
            QMessageBox.information(self, "SDTM Helper", "Connect to SAS first.")
            return False
        return True

    # files and settings
    def save(self):
        self.ws.save(self.editor.toPlainText(), self.table.text())
        self.statusBar().showMessage("Saved. Your program and progress will be here next time.")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open SAS program", "", "SAS programs (*.sas);;All files (*)")
        if path:
            self.editor.setPlainText(Path(path).read_text(encoding="utf-8", errors="replace"))

    def export_file(self):
        default = f"{self.ws.domain.lower()}.sas"
        path, _ = QFileDialog.getSaveFileName(self, "Export SAS program", default, "SAS programs (*.sas)")
        if path:
            Path(path).write_text(self.editor.toPlainText(), encoding="utf-8")
            self.statusBar().showMessage(f"Exported to {path}")

    def edit_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == QDialog.Accepted:
            self.settings = dlg.result_settings()
            save_settings(self.settings)
            self.statusBar().showMessage("Settings saved. Connect again to use them.")

    def closeEvent(self, event):
        if self.ws:
            self.ws.save(self.editor.toPlainText(), self.table.text())
        if self.sas is not None:
            try:
                self.sas.close()
            except Exception:
                pass
        event.accept()


def _has_authinfo() -> bool:
    home = Path.home()
    return (home / "_authinfo").exists() or (home / ".authinfo").exists()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SDTM Helper")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
