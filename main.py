#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NUScope - Image Analysis Platform
"""

import sys
from PyQt5 import QtWidgets
from NUScopeGUI_v0 import Window

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    mainWindow = Window()
    mainWindow.show()
    sys.exit(app.exec_())
