"""Shared button states for the two desktop applications."""
from pathlib import Path


BUTTON_STYLES = """
    QPushButton, QToolButton#workflowButton, QToolBar QToolButton {
        background: #ffffff; color: #172b4d; border: 1px solid #94a3b8;
        border-radius: 6px; padding: 7px 12px;
    }
    QPushButton:hover, QToolButton#workflowButton:hover, QToolBar QToolButton:hover {
        background: #dbeafe; border-color: #2563eb;
    }
    QPushButton:pressed, QToolButton#workflowButton:pressed, QToolBar QToolButton:pressed {
        background: #bfdbfe; border-color: #1d4ed8;
    }
    QPushButton:focus, QToolButton#workflowButton:focus, QToolBar QToolButton:focus {
        border: 2px solid #2563eb;
    }
    QPushButton:disabled, QToolButton#workflowButton:disabled, QToolBar QToolButton:disabled {
        background: #edf1f5; color: #64748b; border-color: #d6dee8;
    }
    QPushButton#primaryButton { font-weight: 600; padding: 9px 16px; }
    QPushButton#primaryButton:enabled {
        background: #2563eb; color: #ffffff; border: 1px solid #2563eb;
    }
    QPushButton#primaryButton:hover:enabled { background: #1d4ed8; }
    QPushButton#primaryButton:pressed:enabled { background: #1e40af; }
    QPushButton#primaryButton:focus:enabled { border: 2px solid #172b4d; }
"""


def review_checkbox_style():
    check = (Path(__file__).parent / "assets" / "check.svg").as_posix()
    return """
        QCheckBox#reviewedCheckBox { spacing: 10px; padding: 6px 0; font-weight: 600; }
        QCheckBox#reviewedCheckBox::indicator {
            width: 22px; height: 22px; border: 2px solid #475569;
            border-radius: 4px; background: #ffffff;
        }
        QCheckBox#reviewedCheckBox::indicator:hover { border-color: #2563eb; }
        QCheckBox#reviewedCheckBox::indicator:checked {
            background: #2563eb; border-color: #1d4ed8; image: url("%s");
        }
        QCheckBox#reviewedCheckBox::indicator:disabled {
            background: #edf1f5; border-color: #94a3b8;
        }
    """ % check
