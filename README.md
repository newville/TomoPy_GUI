# TomoPy_GUI
Written by B.M.Gibson and Matt Newville.  
A simple user interface for TomoPy.  
TomoPy can be found at https://github.com/tomopy/tomopy.  
Currently, GUI is optimized for APS 13BM datasets. Future iterations will expand to other data formats.

Known issues include: 
- Some features slow (movie, data conversion, TomoPy algorithms other than gridrec).
- Single slice reconstruction with padded array and no background air normalization causes artifacts that are not apparent in full volume reconstruction.
