'''
TomoPy UI version designed for APS 13BM.
User interface written by B.M. Gibson with significant help from Matt Newville and Doga Gursoy.
Version 1.0 (October 9, 2018)

Updates:
    Version 1.0.1 (October 9, 2018) B.M.Gibson
        - Updated title and commented code.
    Version 1.0.2 (October 11, 2018) B.M.Gibson
        - Updated zinger removal to artifact removal
        - Scaled data correctly during data export
        - Allowed user to chose number of cores and chunks for TomoPy
        - Allowed TomoPy to work in memory when possible and not duplicate arrays
    Version 1.0.3 (October 16, 2018) B.M.Gibson
        - Movie button
    Version 1.0.4 (October 23, 2018) B.M.Gibson
        - Movie start and stop button
        - Fixed a bug in reading in data from folder with multiple datasets
        - Allow user to turn off normalizing to edge air from background
        - Allow user to upconvert raw data to float32 and save
    Version 1.0.5 (October 24, 2018) B.M.Gibson
        - Added intensities to data visualization area

'''
## Importing packages.
import wx
import sys
import os
import glob
import gc
import time
from optparse import OptionParser
import scipy
import skimage

from netCDF4 import Dataset

import dxchange as dx
import tomopy as tp
import numpy as np

is_wxPhoenix = 'phoenix' in wx.PlatformInfo
if is_wxPhoenix:
    PyDeadObjectError = RuntimeError
else:
    from wx._core import PyDeadObjectError
from wxmplot.imageframe import ImageFrame


class APS_13BM(wx.Frame):
    '''
    Setting up the GUI frame.
    '''
    def __init__(self, parent=None, *args,**kwds):

        kwds["style"] = wx.DEFAULT_FRAME_STYLE|wx.RESIZE_BORDER|wx.TAB_TRAVERSAL

        wx.Frame.__init__(self, parent, wx.NewId(), '',
                         wx.DefaultPosition, wx.Size(-1,-1), **kwds)
        self.SetTitle(" TomoPy ")
        font = wx.SystemSettings.GetFont(wx.SYS_SYSTEM_FONT)
        font.SetPointSize(9)
        self.image_frame = None
        '''
        Making the menu
        '''
        menuBar = wx.MenuBar()
        menu = wx.Menu()
        ## Making menu buttons.
        menu_open = menu.Append(wx.NewId(), "Import Data", "Read in data files")
        menu_chdr = menu.Append(wx.NewId(), 'Change Directory', 'Change the Saving and Working Directory')
        menu_free = menu.Append(wx.NewId(), "Free Memory", "Release data from RAM")
        menu_exit = menu.Append(wx.NewId(),"Exit", "Terminate the program")
        ## Adding buttons to the File menu button of the bar.
        menuBar.Append(menu, "File");
        self.SetMenuBar(menuBar)
        ## Binding the menu commands to respective buttons.
        self.Bind(wx.EVT_MENU, self.client_read_nc, menu_open)
        self.Bind(wx.EVT_MENU, self.change_dir, menu_chdr)
        self.Bind(wx.EVT_MENU, self.client_free_mem, menu_free)
        self.Bind(wx.EVT_MENU, self.OnExit, menu_exit)
        self.Bind(wx.EVT_CLOSE, self.OnExit)
        self.panel = wx.Panel(self)
        title_label = wx.StaticText(self.panel, 1, label = 'TomoPy (optimized for APS 13-BM)')

        '''
        Info Panel (File) - Top Left
        '''
        ## Making the buttons.
        file_label = wx.StaticText(self.panel, -1, label = 'File: ', size = (-1,-1))
        self.file_ID = wx.StaticText(self.panel, 1, label = '')
        path_label = wx.StaticText(self.panel, -1, label = 'Path: ', size = (-1,-1))
        self.path_ID = wx.StaticText(self.panel, 1, label = '')
        status_label = wx.StaticText(self.panel, -1, label = 'Status: ')
        self.status_ID = wx.StaticText(self.panel, -1, label = '')

        '''
        Preprocessing Panel
        '''
        ## Making the buttons
        preprocess_label = wx.StaticText(self.panel, -1, label = 'Preprocessing', size = (-1,-1))
        dark_label = wx.StaticText(self.panel, -1, label = 'Dark Current:', size = (100,-1))
        self.dark_ID = wx.TextCtrl(self.panel, -1, value ='', size = (-1,-1))
        pad_size_opt = [
                'No Padding',
                '1024',
                '2048',
                '4096']
        ## Setting default pad size to 2048 because 13BM NX is 1920 and typically uses gridrec.
        self.pad_size = 2048
        ## Setting default npad to 0 allows the user to save without processing. This immediately gets changed
        ## during normalization or when pad size is changed on the GUI.
        self.npad = 0
        self.pad_size_combo = wx.ComboBox(self.panel, value = 'Auto Pad', choices = pad_size_opt)
        self.pad_size_combo.Bind(wx.EVT_COMBOBOX, self.pad_size_combo_recall)
        ## If value pixel value near edge is NOT air, need to turn off normalizing with those values.
        self.cb = True
        self.bg_cb = wx.CheckBox(self.panel, label = 'Additional Air Normalization', size = (-1,-1))
        self.bg_cb.Bind(wx.EVT_CHECKBOX, self.onChecked)
        self.bg_cb.SetValue(True)
        ## Allow user to specify kernel size for ring removal
        ring_width_label = wx.StaticText(self.panel, label = 'Ring Kernel Width: ', size = (-1,-1))
        self.ring_width_blank = wx.TextCtrl(self.panel, value = '9')
        self.ring_width = 9
        ## Allow user to specify zinger threshold
        zinger_diff_label = wx.StaticText(self.panel, label = 'Zinger difference: ')
        self.zinger_diff_blank = wx.TextCtrl(self.panel, value = 'Est: Median - Zing')
        zinger_kernel_size_label = wx.StaticText(self.panel, label = 'Kernel size:')
        self.zinger_kernel_size_blank = wx.TextCtrl(self.panel, value = '3')
        zinger_button = wx.Button(self.panel, -1, label = 'Remove Zingers', size = (-1,-1))
        zinger_button.Bind(wx.EVT_BUTTON, self.zinger_removal)
        preprocess_button = wx.Button(self.panel, -1, label ='Preprocess', size = (-1,-1))  # this is normalizing step.
        preprocess_button.Bind(wx.EVT_BUTTON, self.normalization)


        '''
        Centering Panel
        '''
        ## Initialization of labels, blanks, and buttons for single slice reconstruction.
        centering_label = wx.StaticText(self.panel, -1, label = 'Centering Parameters                                                                 ', size = (-1,-1))
        upper_slice_label = wx.StaticText(self.panel, -1, label = 'Upper slice:', size = (-1,-1))
        self.upper_rot_slice_blank = wx.TextCtrl(self.panel, value = '')
        self.upper_rot_center_blank = wx.TextCtrl(self.panel, value = '')
        upper_slice_recon_button = wx.Button(self.panel, -1, label = 'Reconstruct Slice', size = (-1,-1))
        upper_slice_recon_button.Bind(wx.EVT_BUTTON, self.up_recon_slice)
        lower_slice_label = wx.StaticText(self.panel, -1, label = 'Lower Slice:', size = (-1,-1))
        self.lower_rot_slice_blank = wx.TextCtrl(self.panel, value = '')
        self.lower_rot_center_blank = wx.TextCtrl(self.panel, value = '')
        lower_slice_recon_button = wx.Button(self.panel, -1, label = 'Reconstruct Slice', size = (-1,-1))
        lower_slice_recon_button.Bind(wx.EVT_BUTTON, self.lower_recon_slice)

        ## Initialization of centering parameters.
        rot_center_button = wx.Button(self.panel, -1, label = 'Optimize Center', size = (-1,-1))
        rot_center_button.Bind(wx.EVT_BUTTON, self.find_rot_center)
        center_method_title = wx.StaticText(self.panel, -1, label = 'Centering Method:', size = (-1,-1))
        self.find_center_type = 'Vghia Vo'
        find_center_list = [
                'Entropy',
				'Vghia Vo',
                '0-180']
        self.find_center_menu = wx.ComboBox(self.panel, value = 'Vghia Vo', choices = find_center_list)
        self.find_center_menu.Bind(wx.EVT_COMBOBOX, self.find_center_algo_type)
        tol_title = wx.StaticText(self.panel, -1, label = '       Tolerance: ')
        self.tol_blank = wx.TextCtrl(self.panel, value = '0.25', size = (100,-1))


        '''
        Reconstruction Panel
        '''
        recon_algo_title = wx.StaticText(self.panel, -1, label = 'Reconstruction')

        ## Drop down for reconstruction algorithm choices. Defaults to Gridrec (fastest).
        recon_type_label = wx.StaticText(self.panel, -1, label = "Algorithm: ", size = (-1,-1))
        self.recon_type = 'gridrec'
        recon_type_list = [
                'Algebraic',
                'Block Algebraic',
                'Filtered Back-projection',
                'Gridrec',
                'Max-likelihood Expectation',
                'Ordered-subset Expectation',
                'ospml_hybrid',
                'ospml_quad',
                'pml_hybrid',
                'pml_quad',
                'Simultaneous Algebraic',
                'Total Variation',
                'Gradient Descent'
                ]
        self.recon_menu = wx.ComboBox(self.panel, value = 'gridrec', choices = recon_type_list)
        self.recon_menu.Bind(wx.EVT_COMBOBOX, self.OnReconCombo)

        ## Filtering choice for during reconstruction.
        self.filter_type = 'hann'
        filter_label = wx.StaticText(self.panel, -1, label = '   Filter:   ', size = (-1,-1))
        filter_list = [
                'none',
                'shepp',
                'cosine',
                'hann',
                'hamming',
                'ramlak',
                'parzen',
                'butterworth'
                ]
        self.filter_menu = wx.ComboBox(self.panel, value = 'hann', choices = filter_list)
        self.filter_menu.Bind(wx.EVT_COMBOBOX, self.OnFilterCombo)

        ## Buttons for tilting and reconstructing
        tilt_button = wx.Button(self.panel, -1, label = "Tilt Correction", size = (-1,-1))
        tilt_button.Bind(wx.EVT_BUTTON, self.tilt_correction)
        recon_button = wx.Button(self.panel, -1, label = "Reconstruct", size = (-1,-1))
        recon_button.Bind(wx.EVT_BUTTON, self.reconstruct)


        '''
        Top Right (Visualize) Panel
        '''
        ## Initializes display for dimensions of dataset.
        dim_label = wx.StaticText(self.panel, label = "Data Dimensions ")
        sx_label = wx.StaticText(self.panel, label = 'NX: ')
        sy_label = wx.StaticText(self.panel, label = 'NY: ')
        sz_label = wx.StaticText(self.panel, label = 'NZ: ')
        self.sx_ID = wx.StaticText(self.panel, label ='')
        self.sy_ID = wx.StaticText(self.panel, label ='')
        self.sz_ID = wx.StaticText(self.panel, label ='')
        intensity_max = wx.StaticText(self.panel, label = 'Max Intensity: ')
        intensity_min = wx.StaticText(self.panel, label = 'Min Intesnity: ')
        self.data_min_ID = wx.StaticText(self.panel, label = '          ')
        self.data_max_ID = wx.StaticText(self.panel, label = '          ')

        ## Initializes data visualization parameters. Defaults to slice view.
        self.plot_type = 'Z Slice'
        plot_view_list = ['Z Slice','Y Sinogram', 'X Sinogram']
        self.visualization_box = wx.RadioBox(self.panel, label = 'Data Visuzalization', choices = plot_view_list, style = wx.RA_SPECIFY_COLS)
        self.visualization_box.Bind(wx.EVT_RADIOBOX, self.OnRadiobox)
        self.z_lble = wx.StaticText(self.panel, label = 'Slice to view: ')
        self.z_dlg = wx.TextCtrl(self.panel, value = 'Enter Slice')
        self.z = self.z_dlg.GetValue()
        plot_button = wx.Button(self.panel, -1, label ='Plot Image', size = (-1,-1))
        plot_button.Bind(wx.EVT_BUTTON, self.plotData)
        start_movie = wx.Button(self.panel, -1, label = 'Display Movie', size = (-1,-1))
        start_movie.Bind(wx.EVT_BUTTON, self.movie_maker)

        self.stop_movie = wx.Button(self.panel, -1, label = 'End Movie', size = (-1,-1))
        self.stop_movie.Bind(wx.EVT_BUTTON, self.onStop)
        self.stop_movie.Disable()

        ## Initializes post processing filter choices. These are not automatically applied.
        pp_label = wx.StaticText(self.panel, label = "Post Processing")  #needs to be on own Sizer.
        pp_filter_label = wx.StaticText(self.panel, -1, label = 'Post Processing Filter: ', size = (-1,-1))
        pp_filter_list = [
                'gaussian_filter',
                'median_filter',
                'sobel_filter'
                ]
        self.pp_filter_menu = wx.ComboBox(self.panel, value = 'none', choices = pp_filter_list)
        self.pp_filter_menu.Bind(wx.EVT_COMBOBOX, self.OnppFilterCombo)
        self.pp_filter_button = wx.Button(self.panel, -1, label = 'Filter', size = (-1,-1))
        self.pp_filter_button.Bind(wx.EVT_BUTTON, self.filter_pp_data)
        ring_remove_button = wx.Button(self.panel, -1, label = 'Remove Ring', size = (-1,-1))
        ring_remove_button.Bind(wx.EVT_BUTTON, self.remove_ring)

        ## Initializes data export choices.
        save_title = wx.StaticText(self.panel, label = 'Export Data')
        self.save_dtype = 'f4'
        self.save_dtype_list = [
                '8 bit unsigned', #u1
                '16 bit signed', #i2
                '16 bit unsigned', #u2
                '32 bit float'#f4
                ]
        self.save_dtype_menu = wx.ComboBox(self.panel, value = '32 bit float', choices = self.save_dtype_list)
        self.save_dtype_menu.Bind(wx.EVT_COMBOBOX, self.OnSaveDtypeCombo)
        self.save_data_type = '.vol'
        self.save_data_list = [
                '.tif',
                '.vol'
                ]
        self.save_data_type_menu = wx.ComboBox(self.panel, value = '.vol', choices = self.save_data_list)
        self.save_data_type_menu.Bind(wx.EVT_COMBOBOX, self.OnSaveDataTypeCombo)

        save_recon_button = wx.Button(self.panel, -1, label = "Save Reconstruction", size = (-1,-1))
        save_recon_button.Bind(wx.EVT_BUTTON, self.save_recon)

        ## Computation Options panel
        comp_opt_title = wx.StaticText(self.panel, -1, label = 'Computation Options', size = (-1,-1))
        ncores_label = wx.StaticText(self.panel, -1, label = 'Number of Cores:', size = (-1,-1))
        self.ncore_blank = wx.TextCtrl(self.panel, value = '4')
        self.ncore = 4
        nchunks_label = wx.StaticText(self.panel, -1, label = '  Number of Chunks: ', size = (-1,-1))
        self.nchunk_blank = wx.TextCtrl(self.panel, -1, value = '128')
        self.nchunk = 128

        '''
        Setting up the GUI Sizers for layout of initialized widgets.
        '''
        ## Window is broken up into two columns.
        windowSizer = wx.BoxSizer(wx.HORIZONTAL)
        leftSizer = wx.BoxSizer(wx.VERTICAL)
        rightSizer = wx.BoxSizer(wx.VERTICAL)

        ## Creating Sizers for the left column.
        info_fname_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        info_path_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        info_status_Sizer = wx.BoxSizer(wx.HORIZONTAL)

        preprocessing_title_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        preprocessing_panel_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        preprocessing_pad_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        preprocessing_ring_width_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        preprocessing_zinger_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        preprocessing_preprocess_button_Sizer = wx.BoxSizer(wx.HORIZONTAL)

        centering_title_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        recon_upper_center_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        recon_lower_center_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        centering_method_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        centering_button_Sizer = wx.BoxSizer(wx.HORIZONTAL)

        recon_algo_title_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        recon_algo_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        recon_filter_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        recon_button_Sizer = wx.BoxSizer(wx.HORIZONTAL)


        ## Creating Sizers for the right column.
        dim_title_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        dim_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        data_int_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        viz_box_Sizer = wx.BoxSizer(wx.HORIZONTAL)

        slice_view_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        movie_Sizer = wx.BoxSizer(wx.HORIZONTAL)

        pp_label_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        pp_filter_Sizer = wx.BoxSizer(wx.HORIZONTAL)

        save_title_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        save_recon_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        comp_opt_title_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        comp_opt_cores_n_chunks_Sizer = wx.BoxSizer(wx.HORIZONTAL)
        '''
        Adding widgets to LEFT Sizer.
        '''
        ## Adding title to topSizer
        leftSizer.Add(title_label, 0, wx.ALL|wx.EXPAND, 5)
        ## Adding to info panel.
        info_fname_Sizer.Add(file_label, 0, wx.ALL|wx.EXPAND, 5)
        info_fname_Sizer.Add(self.file_ID, wx.ALL|wx.EXPAND, 5)
        info_path_Sizer.Add(path_label,  0, wx.ALL|wx.EXPAND, 5)
        info_path_Sizer.Add(self.path_ID, 0, wx.ALL|wx.EXPAND, 5)
        info_status_Sizer.Add(status_label, 0, wx.ALL|wx.EXPAND, 5)
        info_status_Sizer.Add(self.status_ID, 0, wx.ALL|wx.EXPAND, 5)
        ## Adding to Preprocessing panel.
        preprocessing_title_Sizer.Add(preprocess_label, wx.ALL, 5)
        preprocessing_panel_Sizer.Add(dark_label, -1, wx.ALL, 5)
        preprocessing_panel_Sizer.Add(self.dark_ID, wx.ALL, 5)
        preprocessing_panel_Sizer.Add(self.pad_size_combo, wx.ALL, 5)
        preprocessing_title_Sizer.Add(self.bg_cb, wx.ALL, 5)
        preprocessing_ring_width_Sizer.Add(ring_width_label, -1, wx.ALL|wx.ALIGN_CENTER, 5)
        preprocessing_ring_width_Sizer.Add(self.ring_width_blank, -1, wx.ALL|wx.ALIGN_CENTER, 5)
        preprocessing_ring_width_Sizer.Add(ring_remove_button, -1, wx.ALL|wx.EXPAND|wx.ALIGN_CENTER, 5)
        preprocessing_zinger_Sizer.Add(zinger_diff_label, 0, wx.ALL|wx.ALIGN_CENTER, 5)
        preprocessing_zinger_Sizer.Add(self.zinger_diff_blank, 0, wx.ALL|wx.EXPAND|wx.ALIGN_CENTER, 5)
        preprocessing_zinger_Sizer.Add(zinger_kernel_size_label, -1, wx.ALL|wx.ALIGN_CENTER, 5)
        preprocessing_zinger_Sizer.Add(self.zinger_kernel_size_blank, -1, wx.ALL|wx.ALIGN_CENTER, 5)
        preprocessing_preprocess_button_Sizer.Add(zinger_button, -1, wx.ALL, 5)
        preprocessing_preprocess_button_Sizer.Add(preprocess_button, -1, wx.ALL, 5)
        ## Adding to centering panel.
        centering_title_Sizer.Add(centering_label, 0, wx.ALL, 5)
        centering_title_Sizer.Add(rot_center_button, 0, wx.RIGHT|wx.EXPAND|wx.ALIGN_CENTER, 5)
        recon_upper_center_Sizer.Add(upper_slice_label, 0, wx.ALL, 5)
        recon_upper_center_Sizer.Add(self.upper_rot_slice_blank, 0, wx.ALL, 5)
        recon_upper_center_Sizer.Add(self.upper_rot_center_blank, 0, wx.ALL, 5)
        recon_upper_center_Sizer.Add(upper_slice_recon_button, 0, wx.ALL, 5)
        recon_lower_center_Sizer.Add(lower_slice_label, 0, wx.ALL, 5)
        recon_lower_center_Sizer.Add(self.lower_rot_slice_blank, 0, wx.ALL, 5)
        recon_lower_center_Sizer.Add(self.lower_rot_center_blank, 0, wx.ALL, 5)
        recon_lower_center_Sizer.Add(lower_slice_recon_button, 0, wx.ALL, 5)
        centering_method_Sizer.Add(center_method_title, 0, wx.ALL|wx.ALIGN_CENTER, 5)
        centering_method_Sizer.Add(self.find_center_menu, -1, wx.ALL, 5)
        centering_method_Sizer.Add(tol_title, -1, wx.ALL|wx.ALIGN_CENTER,5)
        centering_method_Sizer.Add(self.tol_blank, -1, wx.ALL, 5)

        ## Adding to reconstruction panel.
        recon_algo_title_Sizer.Add(recon_algo_title, 0, wx.ALL, 5)
        recon_algo_Sizer.Add(recon_type_label, 0, wx.ALL, 5)
        recon_algo_Sizer.Add(self.recon_menu, 0, wx.ALL, 5)
        recon_algo_Sizer.Add(filter_label, 0, wx.ALL, 5)
        recon_algo_Sizer.Add(self.filter_menu, 0, wx.ALL, 5)
        recon_button_Sizer.Add(tilt_button, -1, wx.ALL, 5)
        recon_button_Sizer.Add(recon_button, -1, wx.ALL, 5)

        '''
        Adding all widgets to the RIGHT Sizer.
        '''
        ## Dimensions panel
        dim_title_Sizer.Add(dim_label, 0, wx.ALL|wx.EXPAND, 5)
        dim_Sizer.Add(sx_label, -1, wx.ALL|wx.EXPAND, 5)
        dim_Sizer.Add(self.sx_ID, -1, wx.ALL|wx.EXPAND, 5)
        dim_Sizer.Add(sy_label, -1, wx.ALL|wx.EXPAND, 5)
        dim_Sizer.Add(self.sy_ID, -1, wx.ALL|wx.EXPAND, 5)
        dim_Sizer.Add(sz_label, -1, wx.ALL|wx.EXPAND, 5)
        dim_Sizer.Add(self.sz_ID, -1, wx.ALL|wx.EXPAND, 5)
        data_int_Sizer.Add(intensity_max, -1, wx.ALL|wx.EXPAND, 5)
        data_int_Sizer.Add(self.data_max_ID, -1, wx.ALL|wx.EXPAND, 5)
        data_int_Sizer.Add(intensity_min, -1, wx.ALL|wx.EXPAND, 5)
        data_int_Sizer.Add(self.data_min_ID, -1, wx.ALL|wx.EXPAND, 5)
        ## Data visualization panel.
        viz_box_Sizer.Add(self.visualization_box, wx.ALL|wx.EXPAND, 5)
        ## Slice and plotting panel.
        slice_view_Sizer.Add(self.z_lble, -1, wx.ALL|wx.ALIGN_CENTER, 5)
        slice_view_Sizer.Add(self.z_dlg, -1,wx.ALL|wx.EXPAND, 5)
        slice_view_Sizer.Add(plot_button, wx.ALL|wx.EXPAND, 5)
        movie_Sizer.Add(start_movie, wx.ALL|wx.EXPAND, 5)
        movie_Sizer.Add(self.stop_movie, wx.ALL|wx.EXPAND, 5)
        ## Post processing filters panel.
        pp_label_Sizer.Add(pp_label, wx.ALL|wx.EXPAND, 5)
        pp_filter_Sizer.Add(pp_filter_label, -1, wx.ALL, 5)
        pp_filter_Sizer.Add(self.pp_filter_menu, wx.ALL|wx.EXPAND, 5)
        pp_filter_Sizer.Add(self.pp_filter_button, wx.ALL|wx.EXPAND, 5)
        ## Data export panel.
        save_title_Sizer.Add(save_title, wx.ALL|wx.EXPAND, 5)
        save_recon_Sizer.Add(self.save_dtype_menu, wx.ALL|wx.EXPAND,5)
        save_recon_Sizer.Add(self.save_data_type_menu, wx.ALL|wx.EXPAND, 5)
        save_recon_Sizer.Add(save_recon_button, wx.ALL|wx.EXPAND, 5)
        ## Computation Options panel
        comp_opt_title_Sizer.Add(comp_opt_title, wx.ALL|wx.EXPAND, 5)
        comp_opt_cores_n_chunks_Sizer.Add(ncores_label, wx.ALL|wx.EXPAND, 5)
        comp_opt_cores_n_chunks_Sizer.Add(self.ncore_blank, wx.ALL|wx.EXPAND, 5)
        comp_opt_cores_n_chunks_Sizer.Add(nchunks_label, wx.ALL|wx.EXPAND, 5)
        comp_opt_cores_n_chunks_Sizer.Add(self.nchunk_blank, wx.ALL|wx.EXPAND, 5)

        '''
        Adding to leftSizer.
        '''
        ## Adding all subpanels to the topSizer panel. Allows overall aligment.
        leftSizer.Add(wx.StaticLine(self.panel), 0, wx.ALL|wx.EXPAND, 5)
        leftSizer.Add(info_fname_Sizer, 0, wx.EXPAND)
        leftSizer.Add(info_path_Sizer, 0, wx.EXPAND)
        leftSizer.Add(info_status_Sizer, 0, wx.EXPAND)
        leftSizer.Add(wx.StaticLine(self.panel),0,wx.ALL|wx.EXPAND, 5)
        leftSizer.Add(preprocessing_title_Sizer, 0, wx.ALL|wx.EXPAND,5)
        leftSizer.Add(preprocessing_panel_Sizer, 0, wx.EXPAND, 10)
        leftSizer.Add(preprocessing_pad_Sizer, 0, wx.EXPAND,5)
        leftSizer.Add(preprocessing_ring_width_Sizer, 0, wx.EXPAND, 5)
        leftSizer.Add(preprocessing_zinger_Sizer, 0, wx.EXPAND, 5)
        leftSizer.Add(preprocessing_preprocess_button_Sizer, 0, wx.EXPAND, 5)
        leftSizer.Add(wx.StaticLine(self.panel),0,wx.ALL|wx.EXPAND, 5)
        leftSizer.Add(centering_title_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        leftSizer.Add(recon_upper_center_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        leftSizer.Add(recon_lower_center_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        leftSizer.Add(centering_method_Sizer, 0, wx.ALL|wx.EXPAND)
        leftSizer.Add(centering_button_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        leftSizer.Add(wx.StaticLine(self.panel), 0, wx.ALL|wx.EXPAND,5)
        leftSizer.Add(recon_algo_title_Sizer, 0, wx.ALL|wx.EXPAND,5)
        leftSizer.Add(recon_algo_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        leftSizer.Add(recon_filter_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        leftSizer.Add(recon_button_Sizer, 0, wx.ALL|wx.EXPAND, 5)

        '''
        Adding to rightSizer.
        '''
        rightSizer.Add(dim_title_Sizer, 0, wx.ALL, 5)
        rightSizer.Add(dim_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(data_int_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(viz_box_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(slice_view_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(movie_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(wx.StaticLine(self.panel), 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(pp_label_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(pp_filter_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(wx.StaticLine(self.panel), 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(save_title_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(save_recon_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(wx.StaticLine(self.panel), 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(comp_opt_title_Sizer, 0, wx.ALL|wx.EXPAND, 5)
        rightSizer.Add(comp_opt_cores_n_chunks_Sizer, 0, wx.ALL|wx.EXPAND, 5)

        '''
        Adding left and right sizers to main sizer.
        '''
        windowSizer.Add(leftSizer, 0, wx.ALL|wx.EXPAND, 10)
        windowSizer.AddSpacer(60)
        windowSizer.Add(rightSizer, 0, wx.ALL|wx.EXPAND, 10)
        self.panel.SetSizer(windowSizer)
        windowSizer.Fit(self)

    '''
    Methods called by widgets from above. Organized by location.
    First set of methods are closely associated with the main menu bar.
    '''
    def client_read_nc(self, event):
        '''
        Reads in tomography data.
        '''
        with wx.FileDialog(self, "Select Data File", wildcard="Data files (*.nc; *.volume)|*.nc;*.volume",
                       style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST|wx.FD_CHANGE_DIR) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return     # for if the user changed their mind
            ## Setting up timestamp.
            t0 = time.time()
            ## Loading path and updating status label on GUI.
            path = fileDialog.GetPath()
            self.status_ID.SetLabel('Please wait. Reading in the data.')
            ## Loading in file that was just chosen by user.
            try:
                with open(path, 'r') as file:
                    fname = file
                    _path, _fname = os.path.split(path)
                    self.fname1 = file
                    if _fname.endswith('.nc'):
                        '''
                        Reading in .nc files. APS 13BM format.
                        Reads in 2 flats (.nc), .setup, and data (.nc).
                        '''
                        ## Gather list of all .nc files sharing same fname string.
                        fname = glob.glob(_fname[0:-5]+"*[1-3].nc")
                        ## Entries 1 and 3 of fname list are flat fields.
                        ## Read in second entry (fname[1]), which houses the data.
                        self.data = dx.exchange.read_aps_13bm(fname[1],format='netcdf4')
                        print('read in data', self.data.shape)
                        ## Read .setup file, convert lines to rows, identify dark current.
                        setup = glob.glob(_fname[0:-5]+"*.setup")
                        setup = open(setup[0], 'r')
                        setup_data = setup.readlines()
                        result = {}
                        for line in setup_data:
                            words = line[:-1].split(':',1)
                            result[words[0].lower()] = words[1]
                        self.dark = float(result['dark_current'])
                        ## Read in both flat field files.
                        self.flat1 = dx.exchange.read_aps_13bm(fname[0],format = 'netcdf4')
                        self.flat2 = dx.exchange.read_aps_13bm(fname[2],format = 'netcdf4')
                        ## Storing angles.
                        self.theta = tp.angles(self.data.shape[0])
                        ## Storing the dimensions for updating GUI.
                        self.sx = self.data.shape[2]
                        self.sy = self.data.shape[1]
                        self.sz = self.data.shape[0]
                        self.data_min = self.data.min()
                        self.data_max = self.data.max()
                        ## Updating the GUI.
                        self._fname = _fname[0:-5]
                        self.update_info(path=_path,
                                         fname=self._fname,
                                         sx=self.sx,
                                         sy=self.sy,
                                         sz=self.sz,
                                         dark=self.dark,
                                         data_max=self.data_max,
                                         data_min=self.data_min)
                        ## Updating the Centering Parameters Defaults for the dataset.
                        self.upper_rot_slice_blank.SetValue(str(int(self.sz-(self.sz/4))))
                        self.upper_rot_center_blank.SetValue(str(self.sx/2))
                        self.lower_rot_slice_blank.SetValue(str(int(self.sz-3*(self.sz/4))))
                        self.lower_rot_center_blank.SetValue(str(self.sx/2))
                        self.status_ID.SetLabel('Data Imported')
                        ## Time stamping.
                        t1 = time.time()
                        total = t1-t0
                        print('Time reading in files ', total)
                        setup.close()
                    if _fname.endswith('.volume'):
                        '''
                        Reads in .volume files generated from tomoRecon.
                        '''
                        data = Dataset(_fname,'r', format = 'NETCDF4')
                        self.data = data.variables['VOLUME'][:]
                        data.close()
                        # Storing angles.
                        self.theta = tp.angles(self.data.shape[0])
                        # Storing the dimensions for updating GUI.
                        self.sx = self.data.shape[2]
                        self.sy = self.data.shape[1]
                        self.sz = self.data.shape[0]
                        ## Updating the GUI.
                        self._fname = _fname[0:-5]
                        self.dark = 'NA'
                        self.data_min = self.data.min()
                        self.data_max = self.data.max()
                        self.update_info(path=_path, fname=self._fname, sx=self.sx, sy=self.sy, sz=self.sz, dark=self.dark, data_max=self.data_max, data_min=self.data_min)
                        self.status_ID.SetLabel('Data Imported')
                        ## Time stamping.
                        t1 = time.time()
                        total = t1-t0
                        print('Time reading in files ', total)
            except IOError:
                wx.LogError("Cannot open file '%s'." % newfile)

    def update_info(self, path=None, fname=None, sx=None, sy=None, sz=None, dark=None, data_max=None, data_min=None):
        '''
        Updates GUI info when files are imported
        as well as when files are adjusted later.
        '''
        if path is not None:
            self.path_ID.SetLabel(path)
        if sx is not None:
            self.sx_ID.SetLabel(str(self.sx))
        if sy is not None:
            self.sy_ID.SetLabel(str(self.sy))
        if sz is not None:
            self.sz_ID.SetLabel(str(self.sz))
        if fname is not None:
            self.file_ID.SetLabel(fname)
        if dark is not None:
            self.dark_ID.SetLabel(str(self.dark))
        if data_max is not None:
            self.data_max_ID.SetLabel(str(self.data_max))
        if data_min is not None:
            self.data_min_ID.SetLabel(str(self.data_min))

    def change_dir(self, event):
        '''
        Allows user to change directory where files will be saved.
        This does not automatically read in files within the newly
        specified directory.
        '''
        dlg =  wx.DirDialog(self, "Choose Directory","",
                           wx.DD_DEFAULT_STYLE|wx.DD_CHANGE_DIR)
        try:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return
            path = dlg.GetPath()
        except Exception:
            wx.LogError('Failed to open directory!')
            raise
        finally:
            dlg.Destroy()
        if len(path) > 0:
            self.path_ID.SetLabel(path)
            os.chdir(path)
        print('new dir', os.getcwd)

    def client_free_mem(self, event):
        '''
        Deletes stored variables from memory, and resets labels on GUI.
        '''
        if self.data is None:
            return
        else:
            del self.data
            self.path_ID.SetLabel('')
            self.file_ID.SetLabel('')
            self.status_ID.SetLabel('Memory Cleared')
            gc.collect()
            print('fname and path released')

    def OnExit(self, event):
        '''
        Closes the GUI program.
        '''
        try:
            if self.plotframe != None:  self.plotframe.onExit()
        except:
            pass
        self.Destroy()


    '''
    METHODS SPECIFIC TO WIDGETS ON UI.
    '''
    def onChecked(self, event = None):
        '''
        Allows user to not normalize to air at edge if sample takes up entire
        field of view.
        '''
        self.cb = event.GetEventObject()
        self.cb = self.cb.GetValue()
        print('Box checked ', self.cb)

    def pad_size_combo_recall (self, event = None):
        '''
        Sets sinogram pad size if user adjusts from default.
        '''
        new_pad = self.pad_size_combo.GetStringSelection()
        if new_pad == 'No Padding':
            self.pad_size = int(0)
            self.npad = int(0)
        else:
            self.pad_size = int(new_pad)

    def remove_ring(self, event=None):
        '''
        Removes ring artifact from reconstructed data.
        '''
        self.status_ID.SetLabel('Deringing')
        ## Setting up timestamp.
        t0 = time.time()
        ## Pull user specified processing power.
        self.nchunk = int(self.nchunk_blank.GetValue())
        self.ncore = int(self.ncore_blank.GetValue())
        ring_width = int(self.ring_width_blank.GetValue())
        ## If ring width is an even number, make odd.
        if ring_width % 2 == 0:
            ring_width = ring_width + 1
        ## Remove Ring
        print('kernel size is ', ring_width)
        self.data = tp.prep.stripe.remove_stripe_sf(self.data,
                                                    size = ring_width)
#                                                    ncore = self.ncore,
#                                                    nchunk = self.nchunk)
        t1 = time.time()
        print('made it through ring removal.', t1-t0)
        self.status_ID.SetLabel('Ring removed.')

    def zinger_removal(self, event):
        '''
        Remove zingers from raw data.
        '''
        self.status_ID.SetLabel('Correcting Zingers')
        t0 = time.time()
        ## Pull user specified processing power.
        self.nchunk = int(self.nchunk_blank.GetValue())
        self.ncore = int(self.ncore_blank.GetValue())
        zinger_kernel_size = int(self.zinger_kernel_size_blank.GetValue())
        if zinger_kernel_size % 2 == 0:
            zinger_kernel_size = zinger_kernel_size + 1
        try:
            self.zinger = float(self.zinger_diff_blank.GetValue())
        except:
            self.status_ID.SetLabel('Provide expected difference b/n zinger and median data value')
            return
        size = int(self.ring_width_blank.GetValue())
        self.data = tp.remove_outlier(self.data,
                                      dif = self.zinger,
                                      size = size,
                                      ncore = self.ncore,)
        t1 = time.time()
        print('Zingers removed: ', t1-t0)
        self.status_ID.SetLabel('Artifacts Removed.')

    def normalization(self, event):
        '''
        Normalizes the data (1) using the flat fields and dark current,
        then by using the air pixels on edge of sinogram.
        '''
        self.status_ID.SetLabel('Preprocessing')
        ## Setting up timestamp.
        t0 = time.time()
        ## Flats from APS 13BM are in seperate arrays. Average then delete.
        self.flat = np.concatenate((self.flat1, self.flat2),axis=0)
        del self.flat1
        del self.flat2
        self.data = self.data
        self.flat = self.flat
        ## Only single value is collected for dark current from APS 13BM.
        ## Create array of same size for normalizing.
        self.dark = float(self.dark_ID.GetValue())
        self.dark = self.flat*0+self.dark
        ## Pull user specified processing power.
        self.nchunk = int(self.nchunk_blank.GetValue())
        self.ncore = int(self.ncore_blank.GetValue())
        ## First normalization using flats and dark current.
        self.data = tp.normalize(self.data,
                                 flat=self.flat,
                                 dark=self.dark,
                                 ncore = self.ncore)
        ## Additional normalization using the 10 outter most air pixels.
        if self.cb == True:
            self.data = tp.normalize_bg(self.data,
                                        air = 10)
        ## Allows user to pad sinogram.
        if self.pad_size != 0:
            self.npad = 0
            if int(self.pad_size) < self.data.shape[2]:
                self.status_ID.SetLabel('Pad Size too small for dataset. Normalized but no padding.')
                return
            else:
                self.npad = int( (int(self.pad_size) - self.data.shape[2] ) / 2)
                self.data = tp.misc.morph.pad(self.data,
                                              axis = 2,
                                              npad =self.npad,
                                              mode = 'edge')
        ## Delete dark field array as we no longer need it.
        del self.dark
        ## Scale data for I0 as 0.
        tp.minus_log(self.data, out = self.data)
        self.data = tp.remove_nan(self.data,
                                  val = 0.,
                                  ncore = self.ncore)
        self.data_max = self.data.max()
        self.data_min = self.data.min()
        ## Updates GUI. Variables set to None don't update in self.update_info methods
        path = None
        dark = None
        fname = None
        self.update_info(path=path,
                         fname=fname,
                         sx=self.sx,
                         sy=self.sy,
                         sz=self.sz,
                         dark=dark,
                         data_max=self.data_max,
                         data_min=self.data_min)
        ## Set status update for user.
        self.status_ID.SetLabel('Preprocessing Complete')
        ## Timestamping.
        t1 = time.time()
        total = t1-t0
        print('data dimensions ',self.data.shape, type(self.data), self.data.dtype, 'min ', self.data.min(), 'max', self.data.max())
        print('Normalization time was ', total)

    def find_rot_center(self, event=None):
        '''
        Allows user to find rotation centers of two slices. Then displays the
        average of those centers.
        '''
        self.status_ID.SetLabel('Centering')
        print('Begin centering')
        ## Setting up timestamp.
        t0 = time.time()
        ## Tolerance used for TomoPy centering algorithms.
        tol = float(self.tol_blank.GetValue())
        upper_slice = int(self.upper_rot_slice_blank.GetValue())
        lower_slice = int(self.lower_rot_slice_blank.GetValue())
        upper_center = float(self.upper_rot_center_blank.GetValue())
        lower_center = float(self.lower_rot_center_blank.GetValue())
        if self.find_center_type == 'Entropy':
            self.upper_rot_center = float(tp.find_center(self.data[upper_slice:upper_slice+1,:,:],
                                                   self.theta,
                                                   ind = upper_slice,
                                                   init=upper_center,
                                                   tol=tol,
                                                   sinogram_order = False))
            self.lower_rot_center = float(tp.find_center(self.data[lower_slice:lower_slice+1,:,:],
                                                   self.theta,
                                                   ind = upper_slice,
                                                   init = lower_center,
                                                   tol = tol,
                                                   sinogram_order = False))
            self.rot_center = (self.upper_rot_center + self.lower_rot_center) / 2
        if self.find_center_type == '0-180':
            if upper_slice > self.data.shape[2]:
                self.status_ID.SetLabel('Upper slice out of range.')
                return
            if lower_slice > self.data.shape[2]:
                self.status_ID.SetLabel('Lower slice out of range.')
                return
            upper_proj1 = self.data[upper_slice,:,:]
            ## This finds the slice at 180 from the input slice.
            u_slice2 = (upper_slice + int(self.data.shape[0]/2)) % self.data.shape[0]
            upper_proj2 = self.data[u_slice2,:,:]
            self.upper_rot_center = tp.find_center_pc(upper_proj1,
                                                      upper_proj2,
                                                      tol = tol)
            lower_proj1 = self.data[lower_slice,:,:]
            l_slice2 = (lower_slice + int(self.data.shape[0]/2)) % self.data.shape[0]
            lower_proj2 = self.data[l_slice2,:,:]
            self.lower_rot_center = tp.find_center_pc(lower_proj1,
                                                      lower_proj2,
                                                      tol = tol)
            self.rot_center = (self.upper_rot_center + self.lower_rot_center) / 2
        ## Vghia Vo works very well with 13BM data.
        if self.find_center_type == 'Vghia Vo':
            self.upper_rot_center = tp.find_center_vo(self.data[:,upper_slice:upper_slice+1,:])
            self.lower_rot_center = tp.find_center_vo(self.data[:,lower_slice:lower_slice+1,:])
            self.rot_center = (self.upper_rot_center + self.lower_rot_center) / 2
        ## Timestamping.
        t1 = time.time()
        total = t1-t0
        print('Time to find center was ', total)
        self.status_ID.SetLabel('Rotation Center found.')
        print('success, rot center is ', self.rot_center)
        ## Updating the GUI for the calculated values.

        self.upper_rot_center_blank.SetLabel(str((self.upper_rot_center-self.npad)))
        self.lower_rot_center_blank.SetLabel(str((self.lower_rot_center-self.npad)))

    def up_recon_slice (self, event):
        '''
        Slice reconstruction methods.
        '''
        self.status_ID.SetLabel('Reconstructing slice.')
        t0 = time.time()
        upper_rot_center = float(self.upper_rot_center_blank.GetValue())
        ## Remember to remove this before syncing.
        if self.npad != 0:
            upper_rot_center = float(upper_rot_center+self.npad)
        start = int(self.upper_rot_slice_blank.GetValue())
        self.data_slice = self.data[:,start:start+1,:]
        self.data_slice = tp.recon(self.data_slice,
                                   self.theta,
                                   center = upper_rot_center,
                                   sinogram_order = False,
                                   algorithm = self.recon_type)
        t1 = time.time()
        print('Slice recon time ', t1-t0)
        self.status_ID.SetLabel('Slice Reconstructed.')
        self.plot_slice_data()

    def lower_recon_slice (self, event):
        '''
        Slice reconstruction methods.
        '''
        self.status_ID.SetLabel('Reconstructing slice.')
        t0 = time.time()
        lower_rot_center = float(self.lower_rot_center_blank.GetValue())
        if self.npad != 0:
            lower_rot_center = float(lower_rot_center+self.npad)
        start = int(self.lower_rot_slice_blank.GetValue())
        self.data_slice = self.data[:,start:start+1,:]
        self.data_slice = tp.recon(self.data_slice,
                                   self.theta,
                                   center = lower_rot_center,
                                   sinogram_order = False,
                                   algorithm = self.recon_type)
        t1 = time.time()
        print('Slice recon time ', t1-t0)
        self.status_ID.SetLabel('Slice Reconstructed.')
        self.plot_slice_data()

    def find_center_algo_type (self, event):
        '''
        Sets the user's choice for identifying center.
        '''
        self.find_center_type = self.find_center_menu.GetStringSelection()

    def OnReconCombo(self, event):
        '''
        Sets the reconstruction type if changed from default.
        '''
        self.recon_type = self.recon_menu.GetStringSelection()
        if self.recon_type == 'Algebraic':
            self.recon_type = 'art'
        if self.recon_type == 'Block Algebraic':
            self.recon_type = 'bart'
        if self.recon_type == 'Filtered Back-projection':
            self.recon_type = 'fbp'
        if self.recon_type == 'Gridrec':
            self.recon_type = 'gridrec'
        if self.recon_type == 'Max-likelihood Expectation':
            self.recon_type = 'mlem'
        if self.recon_type == 'Ordered-subset Expectation':
            self.recon_type = 'osem'
        if self.recon_type == 'ospml_hybrid':
            self.recon_type = 'ospml_hybrid'
        if self.recon_type == 'ospml_quad':
            self.recon_type = 'ospml_quad'
        if self.recon_type == 'pml_hybrid':
            self.recon_type = 'pml_hybrid'
        if self.recon_type == 'pml_quad':
            self.recon_type = 'pml_quad'
        if self.recon_type == 'Simultaneous Algebraic':
            self.recon_type = 'sirt'
        if self.recon_type == 'Total Variation':
            self.recon_type = 'tv',
        if self.recon_type == 'Gradient Descent':
            self.recon_type = 'grad'
        print('Recon algorithm is ', self.recon_type)

    def OnFilterCombo(self, event):
        '''
        Sets the reconstruction filter if adjusted from default.
        '''
        self.filter_type = self.filter_menu.GetStringSelection()

    def tilt_correction(self, event):
        '''
        Corrects raw data upper and lower centers do not match.
        Currently this needs to be fixed. Tilt corrected data
        unable to reconstruct after this step.
        '''
        ## This did not come from TomoPy because TomoPy has yet to implement.
        ## This also appears to be returning an array that plotting can't work with.
        self.status_ID.SetLabel('Correcting Tilt')
        ## Setting up timestamp.
        t0 = time.time()
        nangles = self.data.shape[0]
        top_center = float(self.upper_rot_center_blank.GetValue())
        bottom_center = float(self.lower_rot_center_blank.GetValue())
        top_slice = float(self.upper_rot_slice_blank.GetValue())
        bottom_slice = float(self.lower_rot_slice_blank.GetValue())
        angle = (top_center - bottom_center)/(bottom_slice - top_slice)
        print('angle is ', angle)
        for i in range(nangles-1):
            projection = self.data[i,:,:]
            r = scipy.ndimage.rotate(projection, angle)
            self.data[i,:,:] = r #might need to remove the float from here. Could be breaking it. Integer?
        t1 = time.time()
        print('Time to tilt ', t1-t0)
        print('New dimnsions are ', self.data.shape, 'Data type is', type(self.data), 'dtype is ', self.data.dtype)
        self.status_ID.SetLabel('Tilt Corrected')

    def reconstruct(self, event):
        '''
        Whole volume reconstruction method.
        '''
        self.status_ID.SetLabel('Reconstructing.')
        ## Setting up timestamp.
        t0 = time.time()
        ## Pull user specified processing power.
        self.nchunk = int(self.nchunk_blank.GetValue())
        self.ncore = int(self.ncore_blank.GetValue())
        print('original data dimensions are ', self.data.shape, type(self.data), self.data.dtype)
        ## Get rotation centers
        upper_rot_center = float(self.upper_rot_center_blank.GetValue())
        lower_rot_center = float(self.lower_rot_center_blank.GetValue())
        ## Need to add padding to center if padded.
        if self.npad != 0:
            upper_rot_center = float(upper_rot_center+self.npad)
            lower_rot_center = float(lower_rot_center+self.npad)
        ## Make array of centers to reduce artifacts during reconstruction.
        center_slope = (lower_rot_center - upper_rot_center) / float(self.data.shape[0])
        center_array = upper_rot_center + (np.arange(self.data.shape[0])*center_slope)
        ## Reconstruct the data.
        self.data = tp.recon(self.data,
                             self.theta,
                             center = center_array,
                             sinogram_order = False,
                             algorithm = self.recon_type,
                             filter_name = self.filter_type,
                             ncore = self.ncore,
                             nchunk = self.nchunk)
        self.data = tp.remove_nan(self.data)
        print('made it through recon.', self.data.shape, type(self.data), self.data.dtype)
        self.status_ID.SetLabel('Reconstruction Complete')
        t1 = time.time()
        total = t1-t0
        print('Reconstruction time was ', total)
        ## Updates new dimensions.
        self.sx = self.data.shape[2]-2*self.npad
        self.sy = self.data.shape[1]-2*self.npad
        self.sz = self.data.shape[0]
        self.data_max = self.data.max()
        self.data_min = self.data.min()
        ## Updates GUI. Variables set to None don't update in self.update_info methods
        path = None
        dark = None
        fname = None
        self.update_info(path=path,
                         fname=fname,
                         sx=self.sx,
                         sy=self.sy,
                         sz=self.sz,
                         dark=dark,
                         data_max=self.data_max,
                         data_min=self.data_min)

    def OnRadiobox(self, event):
        '''
        Adjusts what view the user wishes to see in plotting window.
        '''
        self.plot_type = self.visualization_box.GetStringSelection()
        print('Slice view from Radiobox is ', self.plot_type)

    def OnIntModeBox(self, event = None):
            self.int_mode = self.int_mode_menu.GetStringSelection()
            print('Int_mode is now ', self.int_mode)

    def OnppFilterCombo(self, event):
        '''
        Sets post processing filter type.
        '''
        self.pp_filter_type = self.pp_filter_menu.GetStringSelection()
        print('filter has been set ', self.pp_filter_type)

    def filter_pp_data(self, event):
        '''
        Post processing step. Filters the reconstruction data based on the above
        filter type selection. This is a secondary filter separate from the
        filtering during reconstruction.
        '''
        self.status_ID.SetLabel('Filtering')
        if self.pp_filter_type == 'gaussian_filter':
            print('gaussian')
            self.data = tp.misc.corr.gaussian_filter(self.data, sigma = 3)
            print('gaussian done')
        if self.pp_filter_type == 'median_filter':
            print('median')
            self.data = tp.misc.corr.median_filter(self.data)
            print('median done')
        if self.pp_filter_type == 'sobel_filter':
            print('sobel')
            self.data = tp.misc.corr.sobel_filter(self.data)
            print('sobel done')
        self.status_ID.SetLabel('Data Filtered')

    def OnSaveDtypeCombo (self, event):
        '''
        Data export parameters. All data are exported as intergers with choice of
        8 bit, 16 bit, or 32 bit.
        '''
        self.save_dtype = self.save_dtype_menu.GetStringSelection()
        if self.save_dtype == '8 bit unsigned':
            self.save_dtype = 'u1'
            print('data type changed to ', self.save_dtype)
        if self.save_dtype == '16 bit signed':
            self.save_dtype = 'i2'
            print('data type changed to ', self.save_dtype)
        if self.save_dtype == '16 bit unsigned':
            self.save_dtype = 'u2'
            print('data type changed to ', self.save_dtype)
        if self.save_dtype == '32 bit float':
            self.save_dtype = 'f4'
            print('data type changed to ', self.save_dtype)

    def OnSaveDataTypeCombo(self, event):
        '''
        Data export parameters. Specifies file extension to be used.
        '''
        self.save_data_type = self.save_data_type_menu.GetStringSelection()
        print('Data export type is ', self.save_data_type)

    def save_recon(self, event=None):
        '''
        Method for saving. Data are converted based on user specified options,
        then exported as tif stack or netcdf3 .volume file. Format conversions
        are very slow. Raw data usually saves quickly, but data that has been
        changed to float format is slow.
        '''
        self.status_ID.SetLabel('Saving')
        ## Setting up timestamp.
        t0 = time.time()
        ## Quick check to see if user is trying to save in unsupported formats.
        ## Eventually need to change u2 when converting to i2 is supported.
        if self.save_data_type == '.vol' and (self.save_dtype == 'u1' or self.save_dtype == 'u2'):
            self.status_ID.SetLabel('netCDF3 does not support unsigned images')
            return
        ## Setup copy of data to allow user to scale and save at different file
        ## types (e.g. 8 bit, 16 bit, etc.). Must check to see if data are padded.
        if self.npad == 0:
            save_data = self.data[:]
        ## Exporting data without padding.
        if self.npad != 0: #was padded.
            if self.data.shape [1] == self.data.shape[2]: #padded and reconstructed.
                save_data = self.data[:,self.npad:self.data.shape[1]-self.npad,self.npad:self.data.shape[2]-self.npad]
            if self.data.shape[1] != self.data.shape[2]: #padded and NOT reconstructed.
                save_data = self.data[:,:,self.npad:self.data.shape[2]-self.npad]
        print('starting data shape ', save_data.shape, 'type ', save_data.dtype, 'min', save_data.min(), 'max', save_data.max())
        ## Scales the data appropriately.
        ## This is extremely slow from float32 to other formats.
        a = float(save_data.min())
        b = float(save_data.max()) - a
        if self.save_dtype == 'u1':
            save_data = ((save_data - a) / b) * 255.
            save_data = save_data.astype(np.uint8)
        if self.save_dtype == 'u2':
            save_data = ((save_data - a) / b) * 65535.
            save_data = save_data.astype(np.uint16)
        ## This allows raw data to be saved as float32 if so desired.
        if self.save_dtype == 'f4' and self.data.dtype=='int16':
            print('converting int16 to float32')
            save_data = ((save_data - a) / b)
            save_data = save_data.astype(np.float32)
            print('float32 data are shape ', save_data.shape, 'type ', save_data.dtype,'min', save_data.min(), 'max', save_data.max())
        ## This allows processed data (float 32) be saved as signed integer (16 signed int) which is same as raw data.
        if self.save_dtype =='i2' and self.data.dtype=='float32':
            tt0 = time.time()
            save_data = ((save_data - a) / b)
            for i in range(save_data.shape[0]):
                save_data[i,:,:] = skimage.img_as_int(save_data[i,:,:])
            tt1 = time.time()
            print('Conversion to int16 time ', tt1-tt0)
        print('save data are ', save_data.shape, save_data.dtype, 'min', save_data.min(), 'max', save_data.max())
        '''
        Data exporting.
        '''
        ## Create tif stack within a temp folder in the current working directory.
        if self.save_data_type == '.tif':
            print('Beginning saving tiffs')
            dx.write_tiff_stack(save_data, fname = self._fname, dtype = self.save_dtype, overwrite=True)
        ## Create a .volume netCDF3 file.
        ## netndf3 does not support unsigned integers.
        if self.save_data_type == '.vol':
            print('Beginning saving .vol')
            ## Creates the empty file, and adds metadata.
            ncfile = Dataset(self._fname+'_tomopy_recon.volume', 'w', format = 'NETCDF3_64BIT', clobber = True) # Will overwrite if pre-existing file is found.
            ncfile.description = 'Tomography dataset'
            ncfile.source = 'APS GSECARS 13BM'
            ncfile.history = "Created "+time.ctime(time.time())
            ## Creates the correct dimensions for the file.
            NX = ncfile.createDimension('NX', save_data.shape[2])
            NY = ncfile.createDimension('NY', save_data.shape[1])
            NZ = ncfile.createDimension('NZ', save_data.shape[0])
            print('save_dtype is ', self.save_dtype)
            ## Creates variable for data based on previously constructed dimensions.
            volume = ncfile.createVariable('VOLUME',  self.save_dtype, ('NZ','NY','NX',))
            ## Copies data into empty file array.
            volume[:] = save_data
            print('volume ', volume.shape, type(volume), volume.dtype)
            ncfile.close()
        del save_data
        self.status_ID.SetLabel('Saving completed.')
        t1 = time.time()
        total = t1-t0
        print('Time saving data ', total)

    '''
    Plotting methods.
    '''
    def create_ImageFrame(self):
        '''
        Setups the plotting window.
        '''
        if self.image_frame is None:
            self.image_frame = ImageFrame(self)
            self.image_frame.Show()

    def plot_slice_data (self,event=None):

        if self.data_slice is None: # user forgot to enter a slice.
            return
        image_frame = ImageFrame(self)
        try:
            z = 0
        except ValueError:  # user forgot to enter slice or entered bad slice.
            self.status_ID.SetLabel('Please input an upper slice.')
        ## Plotting data.
        d_data = self.data_slice[z, ::-1, :]
        ## Setting up parameters and plotting.
        if d_data is not None:
            image_frame.panel.conf.interp = 'hanning'
            image_frame.display(1.0*d_data, auto_contrast=True, colormap='gist_gray_r')
            image_frame.Show()
            image_frame.Raise()
        else:
            print("cannot figure out how to get data from plot_type ", self.plot_type)

    def plotData(self, event):
        '''
        Plots when the 'Plot Image' button is pressed.
        Plot view depends on Data Visualization view option and slice.
        Defaults to an additional hanning filter.
        Defaults to gray scale reversed so that bright corresponds to higher
        density.
        '''
        if self.data is None:   # no data loaded by user.
            return
        ## Calls plotting frame.
        image_frame = ImageFrame(self)
        try:
            ## Look for slice to display.
            self.z = self.z_dlg.GetValue()
            z = int(self.z)
            print('read in z and plot_type.', self.z)

        except ValueError:
            print(" cannot read z from Entry ", self.z)
            self.status_ID.SetLabel('Please input a slice.')
            print(" cannot read plot_type from Entry ", self.plot_type)
        ## Plotting data
        d_data = None
        ## Plot an mask if reconstruction is not gridrec.
        if self.recon_type != 'gridrec':
                d_data = tp.circ_mask(d_data, axis = 0, ratio = 0.95)
        ## Plot according to the users input. Default is slice view.
        if self.plot_type.startswith('Z'): #  Slice':
            d_data = self.data[z, ::-1, :]
        if self.plot_type.startswith('Y'): #  Sinogram':
            d_data = self.data[::-1,  z, :]
        if self.plot_type.startswith('X'): #  Sinogram':
            d_data = self.data[::-1, :, z]
        ## Setting up parameters and plotting.
        if d_data is not None:
            image_frame.panel.conf.interp = 'hanning'
            image_frame.display(1.0*d_data, auto_contrast=True, colormap='gist_gray_r')
            image_frame.Show()
            image_frame.Raise()
        else:
            print("cannot figure out how to get data from plot_type ", self.plot_type)
        del d_data

    def onMovieFrame(self, event=None):
        '''
        Updates the image from to allow user to view movie.
        '''
        self.movie_index += 1
        nframes = self.data.shape[0]
        if self.movie_index >= nframes-1:
            self.movie_timer.Stop()
            print("Stop timer")
            return
        self.movie_iframe.panel.update_image(self.data[self.movie_index, ::-1, :])

    def movie_maker (self, event):
        '''
        Currently this is super slow.
        '''
        self.status_ID.SetLabel('Movie started.')
        self.stop_movie.Enable()
        self.movie_iframe = ImageFrame(self)
        d_data = self.data
        if d_data is not None:
            self.movie_iframe.panel.conf.interp = 'hanning'
            self.movie_iframe.display(1.0*d_data[0,::-1,:], contrast_level=0.5, colormap='gist_gray_r')
            self.movie_iframe.Show()
            self.movie_iframe.Raise()
            self.movie_index = 0
            self.movie_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self.onMovieFrame)
            print("Start Movie Timer")
            self.movie_timer.Start()
            del d_data
        self.status_ID.SetLabel('Movie finished.')

    def onStop(self, event = None):
        self.movie_timer.Stop()
        self.stop_movie.Disable()
        self.status_ID.SetLabel('Movie finished.')

def tomopy_13bmapp():
    "run APS13 BM TomoPy GUI"
    usage = "usage: %prog [options] file(s)"
    parser = OptionParser(usage=usage, prog="tomopy_13bmapp",  version="1.0")

    parser.add_option("-s", "--shortcut", dest="shortcut", action="store_true",
                      default=False, help="create desktop shortcut")
    (options, args) = parser.parse_args()

    # create desktop shortcut
    if options.shortcut:
        try:
            from pyshortcuts import make_shortcut
        except ImportError:
            print("cannot make desktop short with `pyshortcuts`")
            return

        icoext = 'icns' if sys.platform=='darwin' else 'ico'
        bindir = 'Scripts' if os.name=='win' else 'bin'

        script = os.path.join(sys.prefix, bindir, 'tomopy_13bmapp')

        thisfolder, _ = os.path.split(__file__)
        icon = os.path.join(thisfolder, 'icons', 'pie.%s' % icoext )
        make_shortcut(script, name='TomoPy_13BM', icon=icon, terminal=False)

    else:
        app = wx.App()
        f = APS_13BM(None, -1)
        f.Show(True)
        app.MainLoop()

if __name__ == '__main__':
    aps13bm_app()
