#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed May  6 15:31:55 2020
@author: Nathaniel Kabat

"""

import sys
import os 
from PyQt5 import QtWidgets,QtCore
from PyQt5.QtWidgets import QDialog, QApplication, QComboBox, QLabel, QPushButton, QMessageBox, QHBoxLayout, QVBoxLayout, QMainWindow, QFileDialog, QWidget, QGridLayout, QTextBrowser, QTableWidget, QTableWidgetItem, qApp, QMenu, QAction, QActionGroup, QSplashScreen, QStatusBar, QDialogButtonBox, QSpinBox, QDoubleSpinBox
from PyQt5.QtGui import QIcon, QPixmap, QFont, QPalette, QColor
from PyQt5.QtCore import Qt
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.patches as patches
import numpy as np
import h5py
import time
from scipy.ndimage import gaussian_filter, median_filter
from ImageLoadLibraries_v0 import *
from styles import STYLESHEET, MENU_STYLE, STATUSBAR_STYLE  # Import the styles
# from ImageFilteringLibraries_v0 import *
# matplotlib.use('Qt5Agg')
progname = os.path.basename(sys.argv[0])
progversion = "0.1.0"   
mpl.rc('image',cmap='gray') 
            

        
class Window(QMainWindow):
    def __init__(self, *args,**kwargs):
        super(Window, self).__init__(*args,**kwargs)
        self.setWindowTitle(f"NUScope Image Analysis (v{progversion})")
        self.setGeometry(300,250,1250,600)
        self.setStyleSheet(STYLESHEET)  # Apply the stylesheet
        
        # Initialize properties for colormap and scale bar
        self.current_colormap = 'viridis'  # Default colormap
        self.show_scale_bar = False  # Default scale bar state
        self.scale_bar_length = 100  # Default scale bar length in pixels
        self.scale_bar_unit = 'nm'  # Default scale bar unit
        self.scale_bar_position = 'lower right'  # Default scale bar position
        self.pixel_size = 1.0  # Default pixel size in scale bar units
        
        # Initialize properties for intensity transformations
        self.intensity_transform = 'linear'  # Default transformation
        self.power_value = 2.0  # Default power value for power law transformation
        self.show_colorbar = False  # Default colorbar state
        
        # Store original image data for transformations
        self.original_imdata = None
        
        # Set application icon
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'logo.svg')))
        
        # Create status bar
        self.statusBarObj = QStatusBar()
        self.setStatusBar(self.statusBarObj)
        self.statusBarObj.showMessage("Ready")
        
        mainw = QWidget()
        self.setCentralWidget(mainw)
        mainw.setLayout(QHBoxLayout())
        
        #Initalize hf backend to save data
        #has to remove file if file exists (HDF storage issue)
        global tempHF
        self.hdf5name = "TempHDF5File.hdf5"
        try:
            os.remove(self.hdf5name)
        except:
            pass
        tempHF = h5py.File(self.hdf5name,"a")
      
        #Create widget for figure plotting
        self.figwidget = QWidget()
        figwidget = self.figwidget
        figwidget.resize(600, 600)
        figwidget.setLayout(QVBoxLayout())
        figwidget.figure = Figure()
        figwidget.canvas = FigureCanvas(figwidget.figure)
        figwidget.setSizePolicy(QtWidgets.QSizePolicy.Expanding,QtWidgets.QSizePolicy.Expanding)
        figwidget.setMinimumSize(200,200)
        figwidget.canvas.updateGeometry()           
        #self.ax = self.figure.add_subplot(111)
        figwidget.toolbar = NavigationToolbar(figwidget.canvas, figwidget)
        figwidget.layout().addWidget(figwidget.toolbar)
        figwidget.layout().addWidget(figwidget.canvas)

        #Create widget for metadata:
        self.metawidget =QWidget()
        metawidget = self.metawidget
        metawidget.resize(150,600)
        metawidget.setSizePolicy(QtWidgets.QSizePolicy.Expanding,QtWidgets.QSizePolicy.Expanding)
        metawidget.setMinimumSize(350,50)               
        metawidget.setLayout(QVBoxLayout())
        metawidget.table = QTableWidget()
        metawidget.table.setColumnCount(1)
        metawidget.table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)        
        metawidget.layout().addWidget(QtWidgets.QLabel("Metadata Table"))
        metawidget.layout().addWidget(metawidget.table)         
        
        #Create widget for log file show
        self.logwidget = QWidget()
        logwidget = self.logwidget
        logwidget.resize(250,600)
        logwidget.setSizePolicy(QtWidgets.QSizePolicy.Expanding,QtWidgets.QSizePolicy.Expanding)
        logwidget.setMinimumSize(150,50)
        logwidget.setLayout(QVBoxLayout())
        logwidget.textw = QTextBrowser()
        logwidget.layout().addWidget(QtWidgets.QLabel("Log File"))
        logwidget.layout().addWidget(logwidget.textw)

        # Create the menu bar
        menubar = self.menuBar()
        menubar.setNativeMenuBar(False)  # Ensure menu appears in the window
        menubar.setStyleSheet(MENU_STYLE)  # Apply the menu style
        
        # File menu
        fileMenu = menubar.addMenu('&File')
        
        # Open file action
        openAct = QAction(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'open.svg')), '&Load File', self)
        openAct.setShortcut('Ctrl+O')
        openAct.setStatusTip('Open an image file')
        openAct.triggered.connect(self.clickedFilewMetaDataLoad)
        fileMenu.addAction(openAct)
        
        # Save HDF5 action
        saveAct = QAction(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'save.svg')), '&Save HDF5 File', self)
        saveAct.setShortcut('Ctrl+S')
        saveAct.setStatusTip('Save data to HDF5 file')
        saveAct.triggered.connect(lambda: self.saveHDFFile("NUScope_data.h5"))
        fileMenu.addAction(saveAct)
        
        # Save log action
        saveLogAct = QAction('Save &Log File', self)
        saveLogAct.setStatusTip('Save log to text file')
        saveLogAct.triggered.connect(self.saveLogFile)
        fileMenu.addAction(saveLogAct)
        
        # Export submenu
        exportMenu = fileMenu.addMenu(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'export.svg')), 'E&xport')
        
        # Export as PNG action
        exportPNGAct = QAction('Export as &PNG', self)
        exportPNGAct.setStatusTip('Export current image as PNG')
        exportPNGAct.triggered.connect(lambda: self.exportAsPNG())
        exportMenu.addAction(exportPNGAct)
        
        # Export as TIFF action
        exportTIFFAct = QAction('Export as &TIFF', self)
        exportTIFFAct.setStatusTip('Export current image as TIFF')
        exportTIFFAct.triggered.connect(lambda: self.exportAsTIFF())
        exportMenu.addAction(exportTIFFAct)
        
        # Export as PDF action
        exportPDFAct = QAction('Export as P&DF', self)
        exportPDFAct.setStatusTip('Export current image as PDF')
        exportPDFAct.triggered.connect(lambda: self.exportAsPDF())
        exportMenu.addAction(exportPDFAct)
        
        fileMenu.addSeparator()
        
        # Exit action
        exitAct = QAction(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'exit.svg')), 'E&xit', self)
        exitAct.setShortcut('Ctrl+Q')
        exitAct.setStatusTip('Exit application')
        exitAct.triggered.connect(self.close)
        fileMenu.addAction(exitAct)
        
        # Tools menu
        toolsMenu = menubar.addMenu('&Tools')
        
        # Filters submenu
        filtersubMenu = toolsMenu.addMenu(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'filter.svg')), '&Filters')
        
        # Gaussian filter action
        gaussAct = QAction('Basic &Gaussian', self)
        gaussAct.triggered.connect(self.applyGaussianFilter)
        filtersubMenu.addAction(gaussAct)
        
        # Median filter action
        medianAct = QAction('&Median Filter', self)
        medianAct.triggered.connect(self.applyMedianFilter)
        filtersubMenu.addAction(medianAct)
        
        # Clear filters action
        clearAct = QAction('&Clear All Filters', self)
        clearAct.triggered.connect(self.clearFilters)
        filtersubMenu.addAction(clearAct)
        
        # Visualization submenu
        visualMenu = toolsMenu.addMenu('&Visualization')
        
        # Colormap submenu
        colormapMenu = visualMenu.addMenu('&Colormap')
        
        # Add colormap options
        colormaps = ['viridis', 'plasma', 'inferno', 'magma', 'cividis', 'gray', 'hot', 'cool', 'jet', 'rainbow']
        colormapGroup = QActionGroup(self)
        colormapGroup.setExclusive(True)
        
        for cmap in colormaps:
            cmapAction = QAction(cmap, self, checkable=True)
            if cmap == self.current_colormap:
                cmapAction.setChecked(True)
            cmapAction.triggered.connect(lambda checked, cm=cmap: self.changeColormap(cm))
            colormapGroup.addAction(cmapAction)
            colormapMenu.addAction(cmapAction)
        
        # Scale bar submenu
        scaleBarMenu = visualMenu.addMenu('&Scale Bar')
        
        # Toggle scale bar action
        toggleScaleBarAct = QAction('&Show Scale Bar', self, checkable=True)
        toggleScaleBarAct.setChecked(self.show_scale_bar)
        toggleScaleBarAct.triggered.connect(self.toggleScaleBar)
        scaleBarMenu.addAction(toggleScaleBarAct)
        
        # Configure scale bar action
        configScaleBarAct = QAction('&Configure Scale Bar...', self)
        configScaleBarAct.triggered.connect(self.configureScaleBar)
        scaleBarMenu.addAction(configScaleBarAct)
        
        # Intensity transformation submenu
        intensityMenu = visualMenu.addMenu('&Intensity Transformation')
        
        # Linear transformation action
        linearAct = QAction('&Linear', self, checkable=True)
        linearAct.setChecked(self.intensity_transform == 'linear')
        linearAct.triggered.connect(lambda: self.changeIntensityTransform('linear'))
        intensityMenu.addAction(linearAct)
        
        # Power law transformation action
        powerAct = QAction('&Power Law', self, checkable=True)
        powerAct.setChecked(self.intensity_transform == 'power')
        powerAct.triggered.connect(lambda: self.changeIntensityTransform('power'))
        intensityMenu.addAction(powerAct)
        
        # Logarithmic transformation action
        logAct = QAction('&Logarithmic', self, checkable=True)
        logAct.setChecked(self.intensity_transform == 'log')
        logAct.triggered.connect(lambda: self.changeIntensityTransform('log'))
        intensityMenu.addAction(logAct)
        
        # Power law configuration action
        powerConfigAct = QAction('&Configure Power Law...', self)
        powerConfigAct.triggered.connect(self.configurePowerLaw)
        intensityMenu.addAction(powerConfigAct)
        
        # Colorbar submenu
        colorbarMenu = visualMenu.addMenu('&Colorbar')
        
        # Toggle colorbar action
        toggleColorbarAct = QAction('&Show Colorbar', self, checkable=True)
        toggleColorbarAct.setChecked(self.show_colorbar)
        toggleColorbarAct.triggered.connect(self.toggleColorbar)
        colorbarMenu.addAction(toggleColorbarAct)
        
        # Help menu
        helpMenu = menubar.addMenu('&Help')
        
        # About action
        aboutAct = QAction(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'help.svg')), '&About', self)
        aboutAct.triggered.connect(self.openAboutPopup)
        helpMenu.addAction(aboutAct)
        
        # Status bar
        self.statusBarObj = self.statusBar()
        self.statusBarObj.setStyleSheet(STATUSBAR_STYLE)  # Apply the status bar style
        self.statusBarObj.showMessage('Ready')
        
        # set the layout
        mainw.layout().addWidget(figwidget,0)
        mainw.layout().addWidget(metawidget,1)
        mainw.layout().addWidget(logwidget,2)
        
        # Add welcome message
        self.logwidget.textw.append(f"Welcome to NUScope v{progversion}\n")
        self.logwidget.textw.append("Northwestern University / NUANCE Center\n")
        self.logwidget.textw.append("Use File > Load File to open an image\n")

    def openAboutPopup(self):
        abtwin = QMessageBox()
        abtwin.setWindowTitle("About")
        abtwin.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'logo.svg')))
        abtwin.setText("NUScope - Image Analysis Platform")
        abtwin.setInformativeText(f"Northwestern University / NUANCE Center. 2020-2025.\nVersion {progversion}\n\nDeveloped by:\nNathaniel Kabat\nRoberto Reis")
        abtwin.button = QPushButton('Okay')
        abtwin.button.clicked.connect(abtwin.close)
        abtwin.setDefaultButton(abtwin.button)        
        abtwin.exec_()
        
    def saveLogFile(self):
        logfname, _ = QFileDialog.getSaveFileName(self, "Save Log File", "", "Text Files (*.txt);;All Files (*)")
        if logfname:
            if not logfname.endswith('.txt'):
                logfname += '.txt'
            try:
                np.savetxt(logfname,[self.logwidget.textw.toPlainText()], fmt='%s',encoding='utf-8')
                self.logwidget.textw.append(f"Saved log to file: {logfname}\n")
            except Exception as e:
                self.logwidget.textw.append(f"Error saving log: {str(e)}\n")
        
    def clickedFilewMetaDataLoad(self):
        try:
            self.dlg = QFileDialog()
            #filters = "Hitachi SEM Image (*.tif *.tiff);;JEOL SEM Image (*.tif *.tiff);;FEI Quanta SEM Image (*.tif *.tiff)"
            filters = "Generic Image File (*.tiff *.tif *.png *.jpg *.jpeg);; Hitachi SEM Image (*.tif *.tiff);;JEOL SEM Image (*.tif *.tiff);;FEI Quanta SEM Image (*.tif *.tiff);; Bruker AFM (*.spm);; Gatan (*.dm3 *.dm4)"
            self.fname, self.filterChoice = self.dlg.getOpenFileName(self, "Select an Image file...",filter=filters,options=QFileDialog.DontUseNativeDialog)            
            
            if not self.fname:  # User canceled the dialog
                return
                
            #select correct image loading function based on choice from file menu
            try:
                if "Hitachi" in self.filterChoice:
                    self.metafname, _ = self.dlg.getOpenFileName(self, "Select an Image file...",filter="Text File (*.txt)",options=QFileDialog.DontUseNativeDialog)                            
                    if not self.metafname:  # User canceled the metadata dialog
                        return
                    self.imdata,self.metadata = HitachiSEMImageLoad(self.fname,self.metafname)          
                elif "Quanta" in self.filterChoice:
                    self.metafname, _ = self.dlg.getOpenFileName(self, "Select an Image file...",filter="Text File (*.txt)",options=QFileDialog.DontUseNativeDialog)                            
                    if not self.metafname:  # User canceled the metadata dialog
                        return
                    self.imdata,self.metadata = QuantaSEMImageLoad(self.fname,self.metafname)                
                elif "JEOL" in self.filterChoice:
                    self.metafname, _ = self.dlg.getOpenFileName(self, "Select an Image file...",filter="Text File (*.txt)",options=QFileDialog.DontUseNativeDialog)                            
                    if not self.metafname:  # User canceled the metadata dialog
                        return
                    self.imdata,self.metadata = JEOL7900SEMImageLoad(self.fname,self.metafname)
                elif "Generic Image" in self.filterChoice:
                    try:
                        self.imdata,self.metadata = GenericImageOpenTIFF(self.fname)
                    except ImportError as e:
                        if 'imagecodecs' in str(e):
                            self.handleMissingDependency("imagecodecs", str(e))
                            return
                        else:
                            raise
                elif "Bruker" in self.filterChoice:
                    try:
                        self.imdata,self.metadata = BrukerAFMImageLoad(self.fname)
                    except ImportError as e:
                        self.handleMissingDependency("pySPM", str(e))
                        return
                elif "Gatan" in self.filterChoice:
                    try:
                        self.imdata,self.metadata = dmImageLoad(self.fname)
                    except ImportError as e:
                        self.handleMissingDependency("ncempy", str(e))
                        return
                else:
                    # Fallback to generic image loader
                    self.logwidget.textw.append(f"Using generic image loader for {self.filterChoice}\n")
                    self.imdata,self.metadata = GenericImageOpenTIFF(self.fname)
            except ImportError as e:
                if 'imagecodecs' in str(e):
                    self.handleMissingDependency("imagecodecs", str(e))
                else:
                    self.logwidget.textw.append(f"Error: {str(e)}\n")
                return
            except Exception as e:
                self.logwidget.textw.append(f"Error loading image: {str(e)}\n")
                return
            
            # Store original image data for transformations
            self.original_imdata = self.imdata.copy()
            
            global tempHF
            nhdfkeys = len(tempHF.keys())
            tempHF.close()
            if nhdfkeys != 0:
                os.remove(self.hdf5name)
                
            tempHF = h5py.File(self.hdf5name,"a")            
            #Save data/metadata into HF backend
            tempHF['filename'] = self.fname
            #tempHF['RawIm']= self.imdata
            tempHF['Im'] = self.imdata
            grp = tempHF.create_group("MetadataGroup")
            for item in self.metadata.items():
                grp[item[0]] = item[1]     
            
            #convert metadata to table
            vertHeaders = []
            #print(self.metadata.keys())
            self.metawidget.table.setRowCount(len(self.metadata))
            for n,key in enumerate(self.metadata.keys()):
                vertHeaders.append(key)
                newitem = QTableWidgetItem(self.metadata[key])
                self.metawidget.table.setVerticalHeaderLabels(vertHeaders)
                self.metawidget.table.setItem(0, n, newitem)
                self.metawidget.table.resizeColumnsToContents()
                self.metawidget.table.resizeRowsToContents()

            
            self.logwidget.textw.append(f"Opened file: {self.fname} \n")                      
            self.logwidget.textw.append(f"File Type Selected: {self.filterChoice} \n")
            

            self.updateImageDisplay()
            self.statusBarObj.showMessage(f"Loaded: {os.path.basename(self.fname)}")
        except Exception as e:
            self.logwidget.textw.append(f"Error loading file: {str(e)}\n")
            self.statusBarObj.showMessage("Error loading file")
        
    def saveHDFFile(self,defaultFileName):
        def saveFile():
            try:
                self.dlg = QFileDialog()
                savename,_ = self.dlg.getSaveFileName(self,"Save HDF5 File", "", "HDF5 Files (*.hdf5);;All Files (*)",options=QFileDialog.DontUseNativeDialog)
                if not savename:
                    return
                    
                if savename[-5:] != ".hdf5":
                    savename += ".hdf5"
                else:
                    pass         
                if os.path.exists(savename) == True:
                    os.remove(savename)
                else:
                    pass

                with h5py.File(savename,"a") as hfsave:
                    for item in tempHF.keys():                    
                        tempHF.copy(item,hfsave) 
                self.logwidget.textw.append(f"Saved data as HDF5 File: {savename}\n")
            except Exception as e:
                self.logwidget.textw.append(f"Error saving HDF5 file: {str(e)}\n")
        return saveFile
        
    def exportImage(self, format_type):
        """Export the current image with colormap and scale bar"""
        try:
            if not hasattr(self, 'imdata'):
                self.logwidget.textw.append("No image loaded. Please load an image first.\n")
                return
                
            # Get file path from user
            file_filters = {
                'png': "PNG Files (*.png)",
                'tiff': "TIFF Files (*.tiff *.tif)",
                'pdf': "PDF Files (*.pdf)"
            }
            
            dlg = QFileDialog()
            export_path, _ = dlg.getSaveFileName(
                self, f"Export as {format_type.upper()}", 
                "", 
                file_filters.get(format_type, "All Files (*)"),
                options=QFileDialog.DontUseNativeDialog
            )
            
            if not export_path:  # User canceled
                return
                
            # Make sure the file has the correct extension
            if format_type == 'png' and not export_path.lower().endswith('.png'):
                export_path += '.png'
            elif format_type == 'tiff' and not (export_path.lower().endswith('.tiff') or export_path.lower().endswith('.tif')):
                export_path += '.tiff'
            elif format_type == 'pdf' and not export_path.lower().endswith('.pdf'):
                export_path += '.pdf'
            
            # Create a new figure with the same settings as the display
            fig = plt.figure(figsize=(8, 6), dpi=300)  # High resolution for publication
            ax = fig.add_subplot(111)
            
            # Apply the same intensity transformation as in the display
            if self.intensity_transform == 'linear':
                display_data = self.imdata
            elif self.intensity_transform == 'power':
                # Ensure data is positive for power transform
                min_val = np.min(self.imdata)
                if min_val < 0:
                    normalized_data = self.imdata - min_val  # Shift to make all values positive
                else:
                    normalized_data = self.imdata
                # Apply power law transform
                display_data = normalized_data ** self.power_value
            elif self.intensity_transform == 'log':
                # Ensure data is positive for log transform
                min_val = np.min(self.imdata)
                if min_val <= 0:
                    normalized_data = self.imdata - min_val + 1e-6  # Shift and add small value to avoid log(0)
                else:
                    normalized_data = self.imdata
                # Apply log transform
                display_data = np.log(normalized_data)
            else:
                display_data = self.imdata
            
            # Plot the transformed data with the current colormap
            im = ax.imshow(display_data, cmap=self.current_colormap)
            ax.axis('off')
            
            # Add colorbar if enabled
            if self.show_colorbar:
                cbar = fig.colorbar(im, ax=ax)
                if self.intensity_transform == 'linear':
                    cbar.set_label('Intensity')
                elif self.intensity_transform == 'power':
                    cbar.set_label(f'Intensity^{self.power_value}')
                elif self.intensity_transform == 'log':
                    cbar.set_label('log(Intensity)')
            
            # Add scale bar if enabled
            if self.show_scale_bar:
                # Get image dimensions
                height, width = self.imdata.shape[:2]
                
                # Calculate scale bar position
                margin = 20  # pixels from the edge
                bar_height = 5  # pixels
                
                if 'lower' in self.scale_bar_position:
                    y_pos = height - margin - bar_height
                else:  # 'upper'
                    y_pos = margin
                    
                if 'left' in self.scale_bar_position:
                    x_pos = margin
                else:  # 'right'
                    x_pos = width - margin - self.scale_bar_length
                
                # Draw the scale bar
                rect = plt.Rectangle((x_pos, y_pos), self.scale_bar_length, bar_height, 
                                   color='white', fill=True)
                ax.add_patch(rect)
                
                # Add the scale text
                scale_value = self.scale_bar_length * self.pixel_size
                scale_text = f"{scale_value} {self.scale_bar_unit}"
                
                text_y = y_pos - 15 if 'lower' in self.scale_bar_position else y_pos + 15
                ax.text(x_pos + self.scale_bar_length/2, text_y, scale_text, 
                        color='white', fontsize=10, ha='center', 
                        bbox=dict(facecolor='black', alpha=0.5, pad=2))
            
            # Save the figure with tight layout and no padding
            fig.tight_layout(pad=0)
            plt.savefig(export_path, dpi=300, bbox_inches='tight', pad_inches=0)
            plt.close(fig)
            
            self.logwidget.textw.append(f"Exported image as {format_type.upper()} to {export_path}\n")
            self.statusBarObj.showMessage(f"Exported as {format_type.upper()}: {os.path.basename(export_path)}")
        except Exception as e:
            self.logwidget.textw.append(f"Error exporting image: {str(e)}\n")
            self.statusBarObj.showMessage("Error exporting image")
    
    def exportAsPNG(self):
        """Export the current image as PNG"""
        self.exportImage('png')
    
    def exportAsTIFF(self):
        """Export the current image as TIFF"""
        self.exportImage('tiff')
    
    def exportAsPDF(self):
        """Export the current image as PDF"""
        self.exportImage('pdf')
            
    def applyGaussianFilter(self, sigma=6):
        try:
            if not hasattr(self, 'imdata'):
                self.logwidget.textw.append("No image loaded. Please load an image first.\n")
                return
                
            # Apply filter to original image data
            self.imdata = gaussian_filter(self.original_imdata, sigma)
            self.updateImageDisplay()
            self.logwidget.textw.append(f"Applied Gaussian Filter with \u03C3 = {sigma}\n")
        except Exception as e:
            self.logwidget.textw.append(f"Error applying Gaussian filter: {str(e)}\n")
    
    def applyMedianFilter(self, size=5):
        try:
            if not hasattr(self, 'imdata'):
                self.logwidget.textw.append("No image loaded. Please load an image first.\n")
                return
                
            # Apply filter to original image data
            self.imdata = median_filter(self.original_imdata, size=size)
            self.updateImageDisplay()
            self.logwidget.textw.append(f"Applied Median Filter with size = {size}\n")
        except Exception as e:
            self.logwidget.textw.append(f"Error applying Median filter: {str(e)}\n")
    
    def clearFilters(self):
        try:
            if not hasattr(self, 'imdata'):
                self.logwidget.textw.append("No image loaded. Please load an image first.\n")
                return
            
            # Restore original image data
            if hasattr(self, 'original_imdata'):
                self.imdata = self.original_imdata.copy()
                self.updateImageDisplay()
                self.logwidget.textw.append(f"Reset figure to raw data \n")        
        except Exception as e:
            self.logwidget.textw.append(f"Error clearing filters: {str(e)}\n")
            
    def handleMissingDependency(self, package_name, error_message):
        """Display a dialog for missing dependencies and offer to install them"""
        msgBox = QMessageBox()
        msgBox.setWindowTitle("Missing Dependency")
        msgBox.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'logo.svg')))
        msgBox.setText(f"Missing required package: {package_name}")
        msgBox.setInformativeText(f"{error_message}\n\nWould you like to install it now?")
        msgBox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msgBox.setDefaultButton(QMessageBox.Yes)
        
        ret = msgBox.exec_()
        
        if ret == QMessageBox.Yes:
            self.statusBarObj.showMessage(f"Installing {package_name}...")
            self.logwidget.textw.append(f"Installing {package_name}...\n")
            
            try:
                import subprocess
                process = subprocess.Popen(
                    [sys.executable, "-m", "pip", "install", package_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                stdout, stderr = process.communicate()
                
                if process.returncode == 0:
                    self.statusBarObj.showMessage(f"Successfully installed {package_name}")
                    self.logwidget.textw.append(f"Successfully installed {package_name}. Please restart the application.\n")
                    
                    restartMsg = QMessageBox()
                    restartMsg.setWindowTitle("Restart Required")
                    restartMsg.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'logo.svg')))
                    restartMsg.setText("Installation successful")
                    restartMsg.setInformativeText("Please restart the application for the changes to take effect.")
                    restartMsg.setStandardButtons(QMessageBox.Ok)
                    restartMsg.exec_()
                else:
                    self.statusBarObj.showMessage(f"Failed to install {package_name}")
                    self.logwidget.textw.append(f"Failed to install {package_name}. Error: {stderr}\n")
            except Exception as e:
                self.statusBarObj.showMessage(f"Error installing {package_name}")
                self.logwidget.textw.append(f"Error installing {package_name}: {str(e)}\n")
        else:
            self.statusBarObj.showMessage("Ready")
            
    def changeColormap(self, cmap):
        self.current_colormap = cmap
        self.updateImageDisplay()
        self.logwidget.textw.append(f"Changed colormap to {cmap}\n")
        
    def toggleScaleBar(self):
        self.show_scale_bar = not self.show_scale_bar
        self.updateImageDisplay()
        if self.show_scale_bar:
            self.logwidget.textw.append(f"Scale bar toggled on\n")
        else:
            self.logwidget.textw.append(f"Scale bar toggled off\n")
        
    def configureScaleBar(self):
        # Create a dialog to configure the scale bar
        configDlg = QDialog(self)
        configDlg.setWindowTitle("Configure Scale Bar")
        configDlg.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'logo.svg')))
        
        # Create a layout for the dialog
        layout = QGridLayout()
        configDlg.setLayout(layout)
        
        # Add a label and spin box for the scale bar length
        layout.addWidget(QLabel("Scale Bar Length (pixels):"), 0, 0)
        lengthSpinBox = QSpinBox()
        lengthSpinBox.setValue(self.scale_bar_length)
        layout.addWidget(lengthSpinBox, 0, 1)
        
        # Add a label and combo box for the scale bar unit
        layout.addWidget(QLabel("Scale Bar Unit:"), 1, 0)
        unitComboBox = QComboBox()
        unitComboBox.addItems(["nm", "μm", "mm", "cm", "m"])
        unitComboBox.setCurrentText(self.scale_bar_unit)
        layout.addWidget(unitComboBox, 1, 1)
        
        # Add a label and combo box for the scale bar position
        layout.addWidget(QLabel("Scale Bar Position:"), 2, 0)
        positionComboBox = QComboBox()
        positionComboBox.addItems(["lower left", "lower right", "upper left", "upper right"])
        positionComboBox.setCurrentText(self.scale_bar_position)
        layout.addWidget(positionComboBox, 2, 1)
        
        # Add a label and spin box for the pixel size
        layout.addWidget(QLabel("Pixel Size (unit/pixel):"), 3, 0)
        pixelSizeSpinBox = QDoubleSpinBox()
        pixelSizeSpinBox.setValue(self.pixel_size)
        layout.addWidget(pixelSizeSpinBox, 3, 1)
        
        # Add a button box to the dialog
        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttonBox, 4, 0, 1, 2)
        
        # Connect the button box to the dialog
        buttonBox.accepted.connect(configDlg.accept)
        buttonBox.rejected.connect(configDlg.reject)
        
        # Show the dialog and get the result
        if configDlg.exec_() == QDialog.Accepted:
            self.scale_bar_length = lengthSpinBox.value()
            self.scale_bar_unit = unitComboBox.currentText()
            self.scale_bar_position = positionComboBox.currentText()
            self.pixel_size = pixelSizeSpinBox.value()
            self.updateImageDisplay()
            self.logwidget.textw.append(f"Scale bar configured: length={self.scale_bar_length} pixels, unit={self.scale_bar_unit}, position={self.scale_bar_position}, pixel size={self.pixel_size} unit/pixel\n")
        
    def changeIntensityTransform(self, transform):
        self.intensity_transform = transform
        self.updateImageDisplay()
        self.logwidget.textw.append(f"Intensity transformation changed to {transform}\n")
        
    def toggleColorbar(self):
        self.show_colorbar = not self.show_colorbar
        self.updateImageDisplay()
        if self.show_colorbar:
            self.logwidget.textw.append(f"Colorbar toggled on\n")
        else:
            self.logwidget.textw.append(f"Colorbar toggled off\n")
        
    def configurePowerLaw(self):
        # Create a dialog to configure the power law transformation
        configDlg = QDialog(self)
        configDlg.setWindowTitle("Configure Power Law Transformation")
        configDlg.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'logo.svg')))
        
        # Create a layout for the dialog
        layout = QGridLayout()
        configDlg.setLayout(layout)
        
        # Add a label and spin box for the power value
        layout.addWidget(QLabel("Power Value:"), 0, 0)
        powerSpinBox = QDoubleSpinBox()
        powerSpinBox.setValue(self.power_value)
        layout.addWidget(powerSpinBox, 0, 1)
        
        # Add a button box to the dialog
        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttonBox, 1, 0, 1, 2)
        
        # Connect the button box to the dialog
        buttonBox.accepted.connect(configDlg.accept)
        buttonBox.rejected.connect(configDlg.reject)
        
        # Show the dialog and get the result
        if configDlg.exec_() == QDialog.Accepted:
            self.power_value = powerSpinBox.value()
            self.updateImageDisplay()
            self.logwidget.textw.append(f"Power law transformation configured: power value={self.power_value}\n")
        
    def updateImageDisplay(self):
        """Update the image display with current settings"""
        if not hasattr(self, 'imdata'):
            return
            
        self.figwidget.figure.clear() #clear figure
        self.ax = self.figwidget.figure.add_subplot(111) # create an axis
        
        # Apply intensity transformation
        try:
            if self.intensity_transform == 'linear':
                display_data = self.imdata
            elif self.intensity_transform == 'power':
                # Ensure data is positive for power transform
                min_val = np.min(self.imdata)
                if min_val < 0:
                    normalized_data = self.imdata - min_val  # Shift to make all values positive
                else:
                    normalized_data = self.imdata
                # Apply power law transform
                display_data = normalized_data ** self.power_value
            elif self.intensity_transform == 'log':
                # Ensure data is positive for log transform
                min_val = np.min(self.imdata)
                if min_val <= 0:
                    normalized_data = self.imdata - min_val + 1e-6  # Shift and add small value to avoid log(0)
                else:
                    normalized_data = self.imdata
                # Apply log transform
                display_data = np.log(normalized_data)
            else:
                display_data = self.imdata
                
            # Plot the transformed data
            im = self.ax.imshow(display_data, cmap=self.current_colormap)
            
            # Add colorbar if enabled
            if self.show_colorbar:
                cbar = self.figwidget.figure.colorbar(im, ax=self.ax)
                if self.intensity_transform == 'linear':
                    cbar.set_label('Intensity')
                elif self.intensity_transform == 'power':
                    cbar.set_label(f'Intensity^{self.power_value}')
                elif self.intensity_transform == 'log':
                    cbar.set_label('log(Intensity)')
            
            # Add scale bar if enabled
            if self.show_scale_bar:
                self.addScaleBar()
            else:
                self.ax.axis("off")
                
            self.figwidget.figure.tight_layout()
            self.figwidget.canvas.draw() # refresh canvas
        except Exception as e:
            self.logwidget.textw.append(f"Error updating display: {str(e)}\n")
        
    def addScaleBar(self):
        """Add a scale bar to the current plot"""
        if not hasattr(self, 'imdata') or not self.show_scale_bar:
            return
            
        # Get image dimensions
        height, width = self.imdata.shape[:2]
        
        # Calculate scale bar position
        margin = 20  # pixels from the edge
        bar_height = 5  # pixels
        
        if 'lower' in self.scale_bar_position:
            y_pos = height - margin - bar_height
        else:  # 'upper'
            y_pos = margin
            
        if 'left' in self.scale_bar_position:
            x_pos = margin
        else:  # 'right'
            x_pos = width - margin - self.scale_bar_length
        
        # Draw the scale bar
        rect = plt.Rectangle((x_pos, y_pos), self.scale_bar_length, bar_height, 
                           color='white', fill=True)
        self.ax.add_patch(rect)
        
        # Add the scale text
        scale_value = self.scale_bar_length * self.pixel_size
        scale_text = f"{scale_value} {self.scale_bar_unit}"
        
        text_y = y_pos - 15 if 'lower' in self.scale_bar_position else y_pos + 15
        self.ax.text(x_pos + self.scale_bar_length/2, text_y, scale_text, 
                    color='white', fontsize=10, ha='center', 
                    bbox=dict(facecolor='black', alpha=0.5, pad=2))
        
        # Turn off axis but keep the scale bar
        self.ax.axis("off")
        
    def closeEvent(self,*args,**kwargs):
        super(QMainWindow,self).closeEvent(*args,**kwargs)
        #print("Close main window and close hdf file(s)")
        tempHF.close()

def main():
    app = QApplication(sys.argv)
    mainWindow = Window()
    mainWindow.show()
    sys.exit(app.exec_())
        
        
        
if __name__ == "__main__":
    main()
