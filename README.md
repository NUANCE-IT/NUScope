# NUScope

NUScope is a platform for image analysis developed at NUANCE/Northwestern University. This tool provides capabilities for visualizing, analyzing, filtering, and exporting microscopy images from various instruments.

## Version 0.1.0

This initial release includes the following features:

- **Image Loading**: Support for multiple microscopy image formats:
  - Generic image files (TIFF, PNG, JPG)
  - Hitachi SEM images
  - JEOL SEM images
  - FEI Quanta SEM images
  - Bruker AFM images
  - Gatan images (DM3, DM4)

- **Image Visualization**: Basic image display with zooming and panning capabilities

- **Metadata Handling**: Extraction and display of metadata from supported formats

- **Image Filtering**: Basic image processing filters
  - Gaussian filter
  - Median filter

- **Export Options**: Export processed images in publication-ready formats
  - PNG export
  - TIFF export
  - PDF export

- **Data Management**: Save and load session data using HDF5 format

## Getting Started

### Prerequisites

- Python 3.6+
- Required packages: PyQt5, matplotlib, numpy, h5py, scikit-image, pySPM

### Installation

```bash
pip install -r requirements.txt
```

### Running the Application

```bash
python main.py
```

## Usage

1. Launch the application
2. Use File > Load File to open an image
3. View metadata in the right panel
4. Apply filters using the Tools > Filters menu
5. Export processed images using File > Export

## Future Development

Planned features for upcoming releases:

- Advanced image analysis tools
- Batch processing capabilities
- Custom measurement tools
- Enhanced export options with scale bars and annotations
- 3D visualization for compatible data formats

## Contributors

- Nathaniel Kabat (Original author)
- Roberto Reis (Original Author/Current maintainer)

## License

This project is licensed under the terms specified in the LICENSE file.
