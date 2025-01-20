# -*- coding: utf-8 -*-
from dabo import events
from dabo import ui
from dabo.localization import _
from dabo.ui import dListControl
from dabo.ui import dPanel
from dabo.ui import dSizer


class MethodSheet(dPanel):
    def afterInit(self):
        self._methodList = dListControl(self, MultipleSelect=False)
        self._methodList.bindEvent(events.Hit, self.onList)
        sz = self.Sizer = dSizer("v")
        sz.append1x(self._methodList)
        self._methodList.addColumn(_("Event/Method"))

    def onList(self, evt):
        self.Application.editCode(self._methodList.StringValue)

    def _getMethodList(self):
        return self._methodList

    MethodList = property(
        _getMethodList,
        None,
        None,
        _("Reference to the method list control  (dListControl)"),
    )
