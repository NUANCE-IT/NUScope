# Metadata

Every reader fills the same schema, whatever the vendor. Missing values are simply absent.

| Section | Typical fields |
|---|---|
| `instrument` | `vendor`, `model`, `serial` |
| `technique` | `SEM`, `FIB`, `TEM`, `STEM`, `EELS`, ... |
| `beam` | `voltage_kV`, `current_nA`, `emission_current_uA`, `spot_size` |
| `optics` | `magnification`, `working_distance_mm`, `camera_length_mm`, `horizontal_field_width_um`, `mode` |
| `detector` | `name`, `mode` |
| `acquisition` | `datetime`, `dwell_us`, `frames_integrated`, `scan_rotation_deg`, `operator`, `software` |
| `sample` | `name`, `stage_x_mm`, `stage_y_mm`, `stage_z_mm`, `tilt_deg` |
| `facility` | NUANCE Center, Northwestern University |

```python
from nuscope import metadata as md
md.get(ds.metadata, "beam.voltage_kV")
md.summary(ds.metadata)      # short human-readable lines
```

The vendor's own block is kept, untouched, in `ds.original_metadata`; NUScope Studio shows it as a searchable
tree. Both travel inside every file NUScope saves, and both are covered by the file's
[seal](integrity.md).
