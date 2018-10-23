# TomoPy_GUI
Written by B.M.Gibson and Matt Newville.  
A simple user interface for TomoPy.  
TomoPy can be found at https://github.com/tomopy/tomopy.  
Currently, GUI is optimized for APS 13BM datasets. Future iterations will expand to other data formats.

Known issues include: 
- Movie has been implemented, but image update is slower.
- Data exports can be slow due to data conversions before saving. 16 bit signed integer data is particularly slow, and signed data are required for netcdf3. Float32 export does export at a reasonable rate because no conversions occur after reconstruction.
- Most reconstruction algorithms are inherently much slower than gridrec. Filtered Back Projection also waiting on TomoPy to update for a filter to be implemented.
- Centering algorithm currently only finds the center at the two user specified slices, and then averages those for the reconstruction. Future update will interpolate center between those two slices and extrapolate further.
- Single slice reconstruction with padded array and no background air normalization causes artifacts that are not apparent in full volume reconstruction.
