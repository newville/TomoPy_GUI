# TomoPy_GUI
Graphic user interface for TomoPy.
TomoPy can be found at https://github.com/tomopy/tomopy.
Currently, GUI is optimized for APS 13BM datasets.

Known issues include: 
- Movie has not been implemented, so button does not function.
- Data export is slow due to data conversions before saving. 16 bit signed integer data is particularly slow, and signed data are required for netcdf3. Float32 export does export at a reasonable rate because no conversions occur after reconstruction.
