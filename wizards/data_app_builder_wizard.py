#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Modernized database application wizard that builds on the original AppWizard.

This keeps the proven scaffolding logic from AppWizard, but offers a slightly
cleaner, more guided flow:

- Short, focused introduction
- Optional "project type" selection to clarify intent
- The existing database page (for now) to avoid duplicating logic
- A table selection page with a simple text filter
- The existing output options page, reused but reachable through the new flow
"""

import os

import dabo
from dabo import events
from dabo import ui
from dabo.localization import _
from dabo.ui.dialogs import Wizard

from .app_wizard import (
    AppWizard,
    AppWizardPage,
    PageDatabase,
    PageTableSelection,
    PageOutput,
    PageGo,
)


class PageIntroModern(AppWizardPage):
    """Concise, goal‑oriented introduction page."""

    def __init__(self, parent, Caption=_("Welcome")):
        super().__init__(parent=parent, Caption=Caption)

    def createBody(self):
        txt = _(
            "Welcome to the Dabo Data App Builder.\n\n"
            "This tool will create a working desktop application on top of your "
            "database. You will:\n"
            "  1. Choose what kind of app you want (for example, CRUD admin app).\n"
            "  2. Connect to a database.\n"
            "  3. Pick the tables to include.\n"
            "  4. Choose where to generate the project.\n\n"
            "You can customize everything later in the Dabo IDE."
        )
        lbl = ui.dEditBox(
            self,
            Value=txt,
            ReadOnly=True,
            BorderStyle="None",
            BackColor=self.BackColor,
        )
        self.Sizer.append1x(lbl, border=10)


class PageProjectType(AppWizardPage):
    """
    Lightweight page to capture the user's intent.

    For now this mainly records the choice on the Form as `projectType`,
    which can be used by future enhancements (layout, defaults, etc.).
    """

    def __init__(self, parent, Caption=_("Project Type")):
        super().__init__(parent=parent, Caption=Caption)

    def createBody(self):
        vsz = self.Sizer

        lbl = ui.dLabel(
            self,
            Caption=_(
                "What kind of application do you want to generate?\n\n"
                "This choice does not lock you in, but helps pick sensible defaults."
            ),
        )
        vsz.append(lbl, border=5)

        choices = [
            (_("Full CRUD admin app (recommended)"), "admin"),
            (_("Data exploration / reporting tool"), "reporting"),
            (_("Single‑table editor (simple form)"), "single"),
        ]

        self.choiceMap = dict(choices)

        # Show as a vertical radio list.
        self.radTypes = ui.dRadioList(
            self,
            Choices=[c[0] for c in choices],
            Orientation="v",
        )
        # Default selection to the first choice.
        try:
            self.radTypes.StringValue = choices[0][0]
        except Exception:
            # If something goes wrong, we simply leave the control
            # with its internal default and let the leave-page logic
            # fall back to "admin".
            pass
        vsz.append1x(self.radTypes, border=10, borderSides="all")

    def onLeavePage(self, direction):
        if direction == "forward":
            # Prefer the string caption of the selected radio button.
            caption = self.radTypes.StringValue
            if not caption:
                # Fall back to the first available caption.
                captions = self.radTypes.Choices or []
                caption = captions[0] if captions else None

            # Map caption to internal key; default to "admin".
            project_type_key = self.choiceMap.get(caption, "admin")
            # Store on the wizard instance for possible future use.
            self.Form.projectType = project_type_key
        return True


class FilterableTableSelectionPage(PageTableSelection):
    """
    Extends the original PageTableSelection with a simple filter text box
    so large schemas are easier to work with.
    """

    def createBody(self):
        super().createBody()

        # Insert a filter row above the checklist.
        vsz = self.Sizer

        filterSizer = ui.dSizer("h")
        lbl = ui.dLabel(self, Caption=_("Filter tables:"))
        self.txtFilter = ui.dTextBox(self)
        self.txtFilter.bindEvent(events.ValueChanged, self.onFilterChanged)

        filterSizer.append(lbl)
        filterSizer.appendSpacer(5)
        filterSizer.append1x(self.txtFilter)

        # The base implementation appends:
        #   label (intro text)
        #   checklist
        #   button row
        # We insert the filter directly after the intro label (index 1).
        vsz.insert(1, filterSizer, "x", border=5, borderSides="bottom")

        # Keep a copy of the full list so filtering can be undone easily.
        self._allTables = []

    def onEnterPage(self, direction):
        super().onEnterPage(direction)
        # Capture the full, unfiltered list whenever we (re)enter.
        self._allTables = list(self.clbTableSelection.Choices)
        self.txtFilter.Value = ""

    def onFilterChanged(self, evt):
        if not hasattr(self, "_allTables"):
            return
        txt = (self.txtFilter.Value or "").strip().lower()
        if not txt:
            new_choices = sorted(self._allTables)
        else:
            new_choices = sorted(
                [t for t in self._allTables if txt in t.lower()]
            )

        # Preserve existing selection where possible.
        current_selection = set(self.clbTableSelection.Value or [])
        self.clbTableSelection.Choices = new_choices
        self.clbTableSelection.Value = [
            t for t in new_choices if t in current_selection
        ]


class EnhancedOutputPage(PageOutput):
    """
    Reuses the original PageOutput but makes it easy to extend with
    additional options in the future.

    Currently, it behaves like the base class but could later surface
    extra toggles (e.g. dashboard layout, reports, exports).
    """

    def createBody(self):
        super().createBody()

        # Header to visually separate the standard options from any future ones.
        lbl = ui.dLabel(
            self,
            Caption=_(
                "\nYou can customize the generated application later. "
                "The defaults are suitable for most CRUD admin tools."
            ),
        )
        # Constrain the label width so the caption wraps instead of
        # forcing the scrolled panel to grow horizontally and show a
        # horizontal scrollbar with no obvious content.
        try:
            # Use the page width if available, with some padding.
            width = getattr(self, "Size", (0, 0))[0]
            if not width and getattr(self, "Parent", None) is not None:
                width = getattr(self.Parent, "Size", (0, 0))[0]
            if width:
                lbl.Width = max(320, width - 80)
        except Exception:
            # If anything goes wrong, fall back to a reasonable fixed width.
            lbl.Width = 380
        self.Sizer.append(lbl, border=5, borderSides="top")


class DataAppBuilderWizard(AppWizard):
    """
    A modernized entry point that keeps AppWizard's proven scaffolding logic
    but uses a slightly clearer sequence of pages.
    """

    def __init__(self, parent=None, defaultDirectory=None, *args, **kwargs):
        # Bypass AppWizard.__init__ so we can define our own page flow,
        # but still inherit its createApp() and helper methods.
        Wizard.__init__(self, parent=parent, *args, **kwargs)

        self.Caption = _("Dabo Data App Builder")
        self.Picture = "daboIcon064"
        self.Size = (520, 560)

        if defaultDirectory is None:
            self.wizDir = self.Application.HomeDirectory
        else:
            self.wizDir = defaultDirectory

        # State used by the inherited createApp() implementation.
        self.tableDict = {}
        self.selectedTables = []
        self.outputDirectory = ""
        self.connectInfo = dabo.db.dConnectInfo()
        self.dbType = "MySQL"  # default to MySQL for compatibility
        self._convertTabs = False
        self._spacesPerTab = 4
        self.usePKUI = True
        self.useUnknown = False
        self.sortFieldsAlpha = False

        # Newer, slightly more guided flow.
        pages = [
            PageIntroModern,
            PageProjectType,
            PageDatabase,
            FilterableTableSelectionPage,
            EnhancedOutputPage,
            PageGo,
        ]
        self.append(pages)
        self.layout()
        self.Centered = True
        self.start()


if __name__ == "__main__":
    app = dabo.application.dApp(BasePrefKey="dabo.ide.wizards.DataAppBuilderWizard")
    app.setAppInfo("appName", "Dabo Data App Builder")
    app.setAppInfo("appShortName", "DataAppBuilder")

    app.MainFormClass = None
    app.setup()
    wiz = DataAppBuilderWizard(None)

    # No need to start the app; when the wizard exits, so will the app.

