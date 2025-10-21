# NUScope User Guide

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Getting Started](#getting-started)
4. [Features](#features)
5. [Image Loading](#image-loading)
6. [Image Processing](#image-processing)
7. [Exporting Images](#exporting-images)
8. [Data Management](#data-management)
9. [Troubleshooting](#troubleshooting)
10. [Development Guide](#development-guide)

## Introduction

NUScope is an image analysis platform developed at the Northwestern University NUANCE Center. It provides a user-friendly interface for visualizing, analyzing, and creating publication-ready images from various microscopy data formats. This guide will help you install, use, and extend NUScope.

## Installation

### Prerequisites

NUScope requires Python 3.6 or later and several dependencies. The following packages are required:

- PyQt5 (GUI framework)
- matplotlib (plotting library)
- numpy (numerical computing)
- h5py (HDF5 file handling)
- scikit-image (image processing)
- scipy (scientific computing)

Optional dependencies for specialized file formats:

- pySPM (for Bruker AFM files)
- ncempy (for Gatan DM3/DM4 files)

### Installation Steps

1. **Clone the repository**

   ```bash
   git clone https://github.com/nuance-center/NUScope.git
   cd NUScope
   ```

2. **Create a virtual environment (recommended)**

   ```bash
   # Using venv
   python -m venv nuscope-env
   
   # Activate the environment
   # On Windows
   nuscope-env\Scripts\activate
   # On macOS/Linux
   source nuscope-env/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Install optional dependencies (if needed)**

   ```bash
   # For Bruker AFM support
   pip install pySPM
   
   # For Gatan DM3/DM4 support
   pip install ncempy
   ```

## Getting Started

### Running NUScope

To start NUScope, navigate to the NUScope directory and run:

```bash
python main.py
```

This will launch the NUScope application with the main interface.

### Basic Workflow

1. **Load an image**: Use File > Load File to open an image file
2. **View metadata**: Examine the metadata in the right panel
3. **Apply filters**: Use Tools > Filters to apply image processing filters
4. **Export results**: Use File > Export to save processed images in various formats

## Features

NUScope provides the following key features:

- **Multi-format support**: Load images from various microscopy instruments
- **Metadata extraction**: View and analyze metadata from supported file formats
- **Image processing**: Apply filters and transformations to enhance images
- **Visualization options**: Change colormaps and add scale bars to images
- **Publication-ready exports**: Save images in high-quality formats for publications
- **Session management**: Save and restore analysis sessions using HDF5 format

## Image Loading

NUScope supports multiple image formats:

- **Generic image files**: TIFF, PNG, JPEG
- **SEM images**: Hitachi, JEOL, FEI Quanta
- **AFM images**: Bruker (requires pySPM)
- **TEM images**: Gatan DM3/DM4 (requires ncempy)

To load an image:

1. Click on File > Load File
2. Select the appropriate file type from the dropdown menu
3. Browse and select your image file
4. For certain formats (e.g., SEM images), you may need to select a metadata file

## Image Processing

NUScope provides several image processing tools:

### Filters

- **Gaussian Filter**: Smooths the image by applying a Gaussian blur
  - Access via: Tools > Filters > Basic Gaussian
  - Use for: Noise reduction, smoothing

- **Median Filter**: Applies a median filter to reduce noise while preserving edges
  - Access via: Tools > Filters > Median Filter
  - Use for: Salt-and-pepper noise removal, edge preservation

### Resetting Filters

To revert to the original image:

- Click on Tools > Filters > Clear All Filters

### Visualization Options

#### Changing Colormaps

NUScope allows you to change the colormap used to display your images:

1. Go to Tools > Visualization > Colormap
2. Select from various options including:
   - viridis (default)
   - plasma
   - inferno
   - magma
   - gray
   - hot
   - jet
   - and more...

The colormap selection will be applied immediately to the current image and will be included in any exported images.

#### Adding Scale Bars

You can add scale bars to your images for accurate measurements:

1. Go to Tools > Visualization > Scale Bar
2. Toggle "Show Scale Bar" to display or hide the scale bar
3. Use "Configure Scale Bar..." to set:
   - Scale bar length (in pixels)
   - Unit (nm, μm, mm, etc.)
   - Position (lower right, lower left, upper right, upper left)
   - Pixel size (the physical size that each pixel represents)

Scale bars will be included in exported images when enabled.

#### Intensity Transformations

NUScope provides several intensity transformations to enhance image contrast and visibility:

1. Go to Tools > Visualization > Intensity Transformation
2. Select from the following options:
   - Linear (default): No transformation, displays raw intensity values
   - Power Law: Raises intensity values to a specified power (I^γ)
   - Logarithmic: Applies logarithmic transformation (log(I))

3. For Power Law transformation, you can configure the power value:
   - Go to Tools > Visualization > Intensity Transformation > Configure Power Law...
   - Set the desired power value (default is 2.0)

These transformations are useful for enhancing contrast in different types of microscopy images.

#### Adding a Colorbar

You can add a colorbar to your images to show the intensity scale:

1. Go to Tools > Visualization > Colorbar
2. Toggle "Show Colorbar" to display or hide the colorbar

The colorbar will display the appropriate scale based on the selected intensity transformation.

All visualization settings (colormap, scale bar, intensity transformation, and colorbar) will be included in exported images.

## Exporting Images

NUScope allows you to export processed images in various formats:

- **PNG**: Lossless compression, good for web and presentations
  - Access via: File > Export > Export as PNG

- **TIFF**: High-quality format with metadata support
  - Access via: File > Export > Export as TIFF

- **PDF**: Vector-based format for publications
  - Access via: File > Export > Export as PDF

All exports are saved at 300 DPI resolution with proper margins for publication-ready quality.

## Data Management

### Saving Log Files

The log panel records all operations performed during your session. To save this log:

1. Click on File > Save Log File
2. Choose a location and filename
3. Click Save

### Saving HDF5 Files

NUScope can save your session data (including images and metadata) in HDF5 format:

1. Click on File > Save HDF5 File
2. Choose a location and filename
3. Click Save

## Troubleshooting

### Common Issues

#### Missing Dependencies

**Problem**: Error message about missing modules (e.g., pySPM, ncempy)

**Solution**: Install the required optional dependencies:

```bash
pip install pySPM ncempy
```

#### Image Loading Errors

**Problem**: Unable to load specific image formats

**Solution**: 
- Ensure you have the correct dependencies installed
- Check that the file format is supported
- For SEM images, make sure you have the corresponding metadata file

#### Display Issues

**Problem**: GUI elements not displaying correctly

**Solution**: 
- Ensure PyQt5 is properly installed
- Try updating your graphics drivers
- Restart the application

## Development Guide

### Project Structure

```
NUScope/
├── main.py                 # Application entry point
├── NUScopeGUI_v0.py        # Main GUI implementation
├── ImageLoadLibraries_v0.py # Image loading functions
├── styles.py               # UI styling definitions
├── icons/                  # Application icons
├── requirements.txt        # Dependencies
├── README.md               # Project overview
└── GUIDE.md                # This user guide
```

### Adding New Features

#### Adding a New Filter

1. Add a new method to the `Window` class in `NUScopeGUI_v0.py`:

```python
def applyNewFilter(self, parameter=default_value):
    try:
        if not hasattr(self, 'imdata'):
            self.logwidget.textw.append("No image loaded. Please load an image first.\n")
            return
            
        imagedata = self.imdata
        # Apply your filter here
        fdata = your_filter_function(imagedata, parameter)
        
        self.figwidget.figure.clear() #clear figure
        self.ax = self.figwidget.figure.add_subplot(111) # create an axis
        self.ax.imshow(fdata)  #plot data
        self.ax.axis("off")
        self.figwidget.figure.tight_layout()
        self.figwidget.canvas.draw() # refresh canvas 
        self.logwidget.textw.append(f"Applied New Filter with parameter = {parameter}\n")
    except Exception as e:
        self.logwidget.textw.append(f"Error applying new filter: {str(e)}\n")
```

2. Add a menu action for the new filter:

```python
newFilterAct = QAction(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'filter.svg')), '&New Filter',self)
newFilterAct.triggered.connect(self.applyNewFilter)
filtersubMenu.addAction(newFilterAct)
```

#### Adding Support for a New File Format

1. Add a new function to `ImageLoadLibraries_v0.py`:

```python
def NewFormatImageLoad(filename):
    '''
    Documentation for the new format loader
    '''
    # Import any required libraries
    try:
        # Your code to load the image and extract metadata
        image_data = your_loading_function(filename)
        meta_data = extract_metadata(filename)
        return image_data, meta_data
    except Exception as e:
        print(f"Error loading file: {str(e)}")
        raise
```

2. Add the format to the file dialog filter in `NUScopeGUI_v0.py`:

```python
filters = "Generic Image File (*.tiff *.tif *.png *.jpg *.jpeg);; ... ;; New Format (*.ext)"
```

3. Add a condition to handle the new format in the `clickedFilewMetaDataLoad` method:

```python
elif "New Format" in self.filterChoice:
    try:
        self.imdata, self.metadata = NewFormatImageLoad(self.fname)
    except ImportError as e:
        self.logwidget.textw.append(f"Error: {str(e)}\n")
        self.logwidget.textw.append("Please install required dependencies for this format.\n")
        return
```

### Contributing

Contributions to NUScope are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Commit your changes (`git commit -m 'Add some amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

### Coding Standards

- Follow PEP 8 style guidelines
- Add docstrings to all functions and classes
- Write unit tests for new features
- Update documentation when adding new functionality
