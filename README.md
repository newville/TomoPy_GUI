# TomoPy_GUI
Written by B.M.Gibson with significant help from Matt Newville and Doga Gursoy.  
TomoPy_GUI is a simple interface for reconstructing synchrotron tomography datasets using TomoPy.  
Currently, this UI is optimized for APS 13-BM netcdf datasets, but future interations will expand to accommodate data formats.  
More information about TomoPy can be found at https://github.com/tomopy/tomopy.  

# Dependencies
Users will need to install the following packages.
- conda install -c dgursoy tomopy
- conda install -c gsecars wxmplot
- conda install -c conda-forge wx
- conda install -c conda-forge os
- conda install -c conda-forge glob
- conda install -c conda-forge time
- conda install -c conda-forge gc
- conda install -c conda-forge scipy
- conda install -c conda-forge skimage
- conda install -c conda-forge netCDF4
- conda install -c conda-forge dxchange
- conda install -c conda-forge numpy

# Known issues include: 
- Entropy centering method performs poorly for most datasets. Best to use default Vghia Vo centering method. Future updates to Entropy will come from either this UI or TomoPy.
- Some features slower than desired (movie, data conversion, TomoPy algorithms other than gridrec).

