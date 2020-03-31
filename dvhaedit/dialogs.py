#!/usr/bin/env python
# -*- coding: utf-8 -*-

# dialogs.py
"""
Classes used to edit pydicom datasets
"""
# Copyright (c) 2020 Dan Cutright
# This file is part of DVHA DICOM Editor, released under a BSD license.
#    See the file LICENSE included with this distribution, also
#    available at https://github.com/cutright/DVHA-DICOM-Editor

import wx
from pubsub import pub
from queue import Queue
from threading import Thread
from time import sleep
from dvhaedit.data_table import DataTable
from dvhaedit.dicom_editor import TagSearch, DICOMEditor, save_dicom
from dvhaedit.dynamic_value import HELP_TEXT
from dvhaedit.paths import LICENSE_PATH
from dvhaedit.utilities import save_csv_to_file, get_window_size


class ErrorDialog:
    """This class allows error messages to be called with a one-liner else-where"""

    def __init__(self, parent, message, caption, flags=wx.ICON_ERROR | wx.OK | wx.OK_DEFAULT):
        """
        :param parent: wx parent object
        :param message: error message
        :param caption: error title
        :param flags: flags for wx.MessageDialog
        """
        self.dlg = wx.MessageDialog(parent, message, caption, flags)
        self.dlg.Center()
        self.dlg.ShowModal()
        self.dlg.Destroy()


class AskYesNo(wx.MessageDialog):
    """Simple Yes/No MessageDialog"""

    def __init__(self, parent, msg, caption="Are you sure?", flags=wx.ICON_WARNING | wx.YES | wx.NO | wx.NO_DEFAULT):
        wx.MessageDialog.__init__(self, parent, msg, caption, flags)

    @property
    def run(self):
        ans = self.ShowModal() == wx.YES
        self.Destroy()
        return ans


class ViewErrorLog(wx.Dialog):
    """Dialog to display the error log in a scrollable window"""
    def __init__(self, error_log):
        """
        :param error_log: error log text
        :type error_log: str
        """
        wx.Dialog.__init__(self, None, title='Error log')

        self.error_log = error_log
        self.button = {'dismiss': wx.Button(self, wx.ID_OK, "Dismiss"),
                       'save': wx.Button(self, wx.ID_ANY, "Save")}
        self.scrolled_window = wx.ScrolledWindow(self, wx.ID_ANY)
        self.text = wx.StaticText(self.scrolled_window, wx.ID_ANY,
                                  "The following errors occurred while editing DICOM tags...\n\n%s" % self.error_log)

        self.__set_properties()
        self.__do_bind()
        self.__do_layout()

        self.run()

    def __do_bind(self):
        self.Bind(wx.EVT_BUTTON, self.on_save, id=self.button['save'].GetId())

    def __set_properties(self):
        self.scrolled_window.SetScrollRate(20, 20)
        self.scrolled_window.SetBackgroundColour(wx.WHITE)

    def __do_layout(self):
        # Create sizers
        sizer_wrapper = wx.BoxSizer(wx.VERTICAL)
        sizer_text = wx.BoxSizer(wx.VERTICAL)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)

        # Add error log text
        sizer_text.Add(self.text, 0, wx.EXPAND | wx.ALL, 5)
        self.scrolled_window.SetSizer(sizer_text)
        sizer_wrapper.Add(self.scrolled_window, 1, wx.EXPAND, 0)

        # Add buttons
        sizer_buttons.Add(self.button['save'], 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        sizer_buttons.Add(self.button['dismiss'], 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        sizer_wrapper.Add(sizer_buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.SetSizer(sizer_wrapper)
        self.SetSize(get_window_size(0.4, 0.4))
        self.Center()

    def run(self):
        """Open dialog, close on Dismiss click"""
        self.ShowModal()
        self.Destroy()

    def on_save(self, *evt):
        """On save button click, create save window to save error log"""
        dlg = wx.FileDialog(self, "Save error log", "", wildcard='*.txt',
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            save_csv_to_file(self.error_log, dlg.GetPath())
        dlg.Destroy()


class TagSearchDialog(wx.Dialog):
    """A dialog consisting of a search bar and table of partial DICOM Tag matches"""
    def __init__(self, parent):
        """
        :param parent: main frame of DVHA DICOM Edit
        """
        wx.Dialog.__init__(self, parent, title='DICOM Tag Search')

        self.parent = parent

        # Create search bar and TagSearch class
        self.search_ctrl = wx.SearchCtrl(self, wx.ID_ANY, "")
        self.search_ctrl.ShowCancelButton(True)
        self.search = TagSearch()

        self.note = wx.StaticText(self, wx.ID_ANY, "NOTE: The loaded DICOM file(s) may not have the selected tag.")

        # Create table for search results
        columns = ['Keyword', 'Tag', 'VR']
        data = {c: [''] for c in columns}
        self.list_ctrl = wx.ListCtrl(self, wx.ID_ANY, style=wx.BORDER_SUNKEN | wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.data_table = DataTable(self.list_ctrl, data=data, columns=columns, widths=[-2, -2, -2])

        # Create buttons
        keys = {'select': wx.ID_OK, 'cancel': wx.ID_CANCEL}
        self.button = {key: wx.Button(self, id_, key.capitalize()) for key, id_ in keys.items()}

        self.__do_bind()
        self.__do_layout()

        self.run()

    def __do_bind(self):
        self.Bind(wx.EVT_TEXT, self.update, id=self.search_ctrl.GetId())
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_double_click, id=self.list_ctrl.GetId())
        self.Bind(wx.EVT_LIST_COL_CLICK, self.data_table.sort_table, self.list_ctrl)

    def __do_layout(self):
        # Create sizers
        sizer_wrapper = wx.BoxSizer(wx.VERTICAL)
        sizer_main = wx.BoxSizer(wx.VERTICAL)
        sizer_search = wx.BoxSizer(wx.VERTICAL)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)

        # Add search bar and results table
        sizer_search.Add(self.search_ctrl, 0, wx.EXPAND | wx.ALL, 5)
        sizer_search.Add(self.note, 0, wx.EXPAND | wx.ALL, 5)
        sizer_search.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        sizer_main.Add(sizer_search, 1, wx.EXPAND | wx.ALL, 5)

        # Add buttons
        sizer_buttons.Add(self.button['select'], 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        sizer_buttons.Add(self.button['cancel'], 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        sizer_main.Add(sizer_buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        # Add everything to window wrapper
        sizer_wrapper.Add(sizer_main, 1, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(sizer_wrapper)
        self.SetSize(get_window_size(0.4, 0.4))
        self.Center()

    def run(self):
        """Open dialog, perform action if Select button is clicked, then close"""
        self.update()
        res = self.ShowModal()
        if res == wx.ID_OK:  # if user clicks Select button
            self.set_tag_to_selection()
        self.Destroy()

    @property
    def data_dict(self):
        """Get the DICOM Tag table data with current search_ctrl value"""
        return self.search(self.search_ctrl.GetValue())

    @property
    def selected_tag(self):
        """Get the Tag of the currently selected/activated row in list_ctrl"""
        selected_data = self.data_table.selected_row_data
        if selected_data:
            return selected_data[0][1]

    def update(self, *evt):
        """Set the table date based on the current search_ctrl value"""
        self.data_table.set_data(**self.data_dict)

    def set_tag_to_selection(self):
        """Set the Group and Element list_ctrl values in the main app"""
        tag = self.selected_tag
        if tag:
            self.parent.input['tag_group'].SetValue(tag.group)
            self.parent.input['tag_element'].SetValue(tag.element)
            self.parent.update_init_value()
            self.parent.update_description()

    def on_double_click(self, evt):
        """Treat double-click the same as selecting a row then clicking Select"""
        self.set_tag_to_selection()
        self.Close()


class TextViewer(wx.Dialog):
    """Simple dialog to display the LICENSE file and a brief text header in a scrollable window"""
    def __init__(self, text, title, width=0.3, height=0.6):
        wx.Dialog.__init__(self, None, title=title)

        self.size = get_window_size(width, height)

        self.scrolled_window = wx.ScrolledWindow(self, wx.ID_ANY)
        self.text = wx.StaticText(self.scrolled_window, wx.ID_ANY, text)

        self.__set_properties()
        self.__do_layout()

        self.run()

    def __set_properties(self):
        self.scrolled_window.SetScrollRate(20, 20)
        self.SetBackgroundColour(wx.WHITE)

    def __do_layout(self):
        sizer_wrapper = wx.BoxSizer(wx.VERTICAL)
        sizer_text = wx.BoxSizer(wx.VERTICAL)

        sizer_text.Add(self.text, 0, wx.EXPAND | wx.ALL, 5)
        self.scrolled_window.SetSizer(sizer_text)
        sizer_wrapper.Add(self.scrolled_window, 1, wx.EXPAND, 0)

        self.SetSizer(sizer_wrapper)
        self.SetSize(self.size)
        self.Center()

    def run(self):
        self.ShowModal()
        self.Destroy()


class About(TextViewer):
    """Simple dialog to display the LICENSE file and a brief text header in a scrollable window"""
    def __init__(self, version):

        with open(LICENSE_PATH, 'r', encoding="utf8") as license_file:
            license_text = ''.join([line for line in license_file])
        license_text = "DVHA DICOM Editor v%s\nedit.dvhanalytics.com\n\n%s" % (version, license_text)

        TextViewer.__init__(self, license_text, title='About DVHA DICOM Editor')


class DynamicValueHelp(TextViewer):
    def __init__(self):
        TextViewer.__init__(self, HELP_TEXT, title='Dynamic Values', width=0.4)


class ProgressFrame(wx.Dialog):
    """Create a window to display progress and begin provided worker"""
    def __init__(self, obj_list, action, close_msg, action_msg=None, action_gui_phrase='Processing', title='Progress'):
        wx.Dialog.__init__(self, None)

        self.close_msg = close_msg
        self.worker_args = [obj_list, action, action_msg, action_gui_phrase, title]

        self.gauge = wx.Gauge(self, wx.ID_ANY, 100)
        self.label = wx.StaticText(self, wx.ID_ANY, "Progress Label:")

        self.__set_properties()
        self.__do_subscribe()
        self.__do_layout()

        self.run()

    def run(self):
        """Initiate layout in GUI and begin thread"""
        self.Show()
        ProgressFrameWorker(*self.worker_args)

    def __set_properties(self):
        width, _ = get_window_size(0.4, 1)
        self.SetMinSize((width, 100))

    def __do_subscribe(self):
        pub.subscribe(self.update, "progress_update")
        pub.subscribe(self.set_title, "progress_set_title")
        pub.subscribe(self.close, "progress_close")

    @staticmethod
    def __do_unsubscribe():
        pub.unsubAll(topicName="progress_update")
        pub.unsubAll(topicName="progress_set_title")
        pub.unsubAll(topicName="progress_close")

    def __do_layout(self):
        sizer_wrapper = wx.BoxSizer(wx.VERTICAL)
        sizer_objects = wx.BoxSizer(wx.VERTICAL)
        sizer_objects.Add(self.label, 0, 0, 0)
        sizer_objects.Add(self.gauge, 0, wx.EXPAND, 0)
        sizer_wrapper.Add(sizer_objects, 0, wx.ALL | wx.EXPAND, 10)
        self.SetSizer(sizer_wrapper)
        self.Fit()
        self.Layout()
        self.Center()

    def set_title(self, msg):
        wx.CallAfter(self.SetTitle, msg)

    def update(self, msg):
        """
        Update the progress message and gauge
        :param msg: a dictionary with keys of 'label' and 'gauge' text and progress fraction, respectively
        :type msg: dict
        """
        wx.CallAfter(self.label.SetLabelText, msg['label'])
        wx.CallAfter(self.gauge.SetValue, int(100 * msg['gauge']))

    def close(self):
        """Destroy layout in GUI and send message close message for parent"""
        wx.CallAfter(pub.sendMessage, self.close_msg)
        self.__do_unsubscribe()
        wx.CallAfter(self.Destroy)


class ProgressFrameWorker(Thread):
    def __init__(self, obj_list, action, action_msg, action_gui_phrase, title):
        Thread.__init__(self)

        pub.sendMessage("progress_set_title", msg=title)

        self.obj_list = obj_list
        self.obj_count = len(self.obj_list)
        self.action = action
        self.action_msg = action_msg
        self.action_gui_phrase = action_gui_phrase

        self.start()

    def run(self):
        queue = self.get_queue()
        worker = Thread(target=self.target, args=[queue])
        worker.setDaemon(True)
        worker.start()
        queue.join()
        sleep(0.3)  # Allow time for user to see final progress in GUI
        pub.sendMessage('progress_close')

    def get_queue(self):
        queue = Queue()
        for i, obj in enumerate(self.obj_list):
            msg = {'label': '%s %s of %s' % (self.action_gui_phrase, i + 1, self.obj_count),
                   'gauge': i / self.obj_count}
            queue.put((obj, msg))
        return queue

    def target(self, queue):
        while queue.qsize():
            parameters = queue.get()
            self.do_action(*parameters)
            queue.task_done()

        msg = {'label': 'Process Complete: %s file%s' % (self.obj_count, ['', 's'][self.obj_count != 1]),
               'gauge': 1.}
        pub.sendMessage("progress_update", msg=msg)

    def do_action(self, obj, msg):
        pub.sendMessage("progress_update", msg=msg)

        result = self.action(obj)
        if self.action_msg is not None:
            msg = {'obj': obj, 'data': result}
            pub.sendMessage(self.action_msg, msg=msg)


class ParsingProgressFrame(ProgressFrame):
    """Create a window to display parsing progress and begin ParseWorker"""
    def __init__(self, file_paths):
        ProgressFrame.__init__(self, file_paths, DICOMEditor, close_msg='parse_complete',
                               action_msg='add_parsed_data', action_gui_phrase='Parsing File',
                               title='Reading DICOM Headers')


class SavingProgressFrame(ProgressFrame):
    """Create a window to display saving progress and begin SaveWorker"""
    def __init__(self, data_sets):
        ProgressFrame.__init__(self, data_sets, save_dicom, close_msg='save_complete',
                               action_gui_phrase='Saving File',
                               title='Saving DICOM Data')