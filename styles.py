#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Styles for NUScope application
"""

# Northwestern University colors
NU_PURPLE = "#4E2A84"  # Primary purple
NU_PURPLE_DARK = "#401F68"  # Darker purple for hover states
NU_LIGHT_PURPLE = "#836EAA"  # Light purple for accents
NU_BLACK = "#342F2E"  # Northwestern black
NU_GRAY = "#716C6B"  # Northwestern gray
NU_LIGHT_GRAY = "#D8D6D6"  # Light gray for backgrounds
NU_WHITE = "#FFFFFF"  # White

# Menu bar style
MENU_STYLE = f"""
background-color: {NU_PURPLE};
color: {NU_WHITE};
font-weight: bold;
padding: 2px;
"""

# Status bar style
STATUSBAR_STYLE = f"""
background-color: {NU_PURPLE};
color: {NU_WHITE};
padding: 3px;
font-weight: bold;
"""

# Application stylesheet
STYLESHEET = f"""
QMainWindow, QDialog {{
    background-color: {NU_WHITE};
}}

QMenuBar {{
    {MENU_STYLE}
}}

QMenuBar::item {{
    background-color: {NU_PURPLE};
    color: {NU_WHITE};
    padding: 4px 10px;
}}

QMenuBar::item:selected {{
    background-color: {NU_PURPLE_DARK};
}}

QMenu {{
    background-color: {NU_WHITE};
    color: {NU_BLACK};
    border: 1px solid {NU_LIGHT_GRAY};
}}

QMenu::item:selected {{
    background-color: {NU_LIGHT_PURPLE};
    color: {NU_WHITE};
}}

QPushButton {{
    background-color: {NU_PURPLE};
    color: {NU_WHITE};
    border: none;
    padding: 5px 15px;
    border-radius: 3px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: {NU_PURPLE_DARK};
}}

QPushButton:pressed {{
    background-color: {NU_LIGHT_PURPLE};
}}

QLabel {{
    color: {NU_BLACK};
    font-weight: bold;
}}

QTableWidget {{
    border: 1px solid {NU_LIGHT_GRAY};
    gridline-color: {NU_LIGHT_GRAY};
}}

QTableWidget::item:selected {{
    background-color: {NU_LIGHT_PURPLE};
    color: {NU_WHITE};
}}

QHeaderView::section {{
    background-color: {NU_PURPLE};
    color: {NU_WHITE};
    padding: 4px;
    font-weight: bold;
    border: 1px solid {NU_PURPLE_DARK};
}}

QTextBrowser {{
    border: 1px solid {NU_LIGHT_GRAY};
    background-color: {NU_WHITE};
}}

QStatusBar {{
    {STATUSBAR_STYLE}
}}
"""
